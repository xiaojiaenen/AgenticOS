"""预算断路器（自 wuwei/middleware/budget.py 移植，wuwei 退役 A5-5）。

Cost Governor —— 直击"token 成本超预估 10-20 倍、无法按任务归因"：
- 每次 run 设定 Budget（token / 估算成本 / 步数上限）
- 软阈值（默认 80%）警告；硬阈值按策略 abort（断路）/ warn（仅记录）
- 成本按模型价格表估算（$/Mtok）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("agenticos.budget")


class BudgetExhausted(Exception):
    """预算耗尽，运行被断路。"""


# 常见模型价格（美元 / 百万 token）: (input, output)。未知模型用 DEFAULT。
DEFAULT_PRICE: tuple[float, float] = (0.5, 1.5)
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "deepseek-chat": (0.27, 1.1),
    "deepseek-flash": (0.27, 1.1),
    "deepseek-reasoner": (0.55, 2.19),
    "claude-sonnet-4-6": (3.0, 15.0),
    "glm-4": (0.1, 0.1),
    "glm-4-flash": (0.01, 0.01),
    "qwen-max": (1.6, 6.4),
}


def estimate_cost(
    usage: dict[str, int] | None,
    model: str,
    prices: dict[str, tuple[float, float]] | None = None,
) -> float:
    """按 usage 与模型价格表估算美元成本。"""
    if not usage:
        return 0.0
    table = prices or MODEL_PRICES
    price_in, price_out = DEFAULT_PRICE
    for key, value in sorted(table.items(), key=lambda item: len(item[0]), reverse=True):
        if model and model.startswith(key):
            price_in, price_out = value
            break
    # 兼容两套 usage 键名：网关原生 prompt_tokens/completion_tokens 与
    # LangChain / DeepAgents 的 input_tokens/output_tokens（_UsageTracker.snapshot）。
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0)) / 1_000_000
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0)) / 1_000_000
    return prompt * price_in + completion * price_out


@dataclass
class Budget:
    """一次 run 的预算约束（None 表示不限）。"""

    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_steps: int | None = None
    on_exhausted: str = "abort"  # abort | warn
    soft_ratio: float = 0.8
    prices: dict[str, tuple[float, float]] | None = None

    def __post_init__(self):
        if self.on_exhausted not in ("abort", "warn"):
            raise ValueError("on_exhausted 只支持 abort/warn")
        for value in (self.max_tokens, self.max_cost_usd, self.max_steps):
            if value is not None and value < 0:
                raise ValueError("Budget limits must be nonnegative")
        if not 0 < self.soft_ratio <= 1:
            raise ValueError("soft_ratio must be in (0,1]")


@dataclass
class RunSpend:
    """单个 run 的累计消耗。"""

    model: str
    warned: bool = False
    cost_usd: float = 0.0


def check_budget(
    budget: Budget,
    usage: dict[str, int],
    steps: int,
    spend: RunSpend,
    *,
    usage_available: bool = True,
) -> None:
    """预算检查：硬阈值断路（abort 抛 BudgetExhausted / warn 记录）、软阈值警告。

    运行异常（限流等）不得绕过预算：模型不回传 usage 时（usage_available=False）
    直接断路，防止无限烧钱。
    """
    if not usage_available and (budget.max_tokens is not None or budget.max_cost_usd is not None):
        raise BudgetExhausted("模型未提供完整usage，无法可靠执行token/成本预算，已停止后续动作")
    exhausted: list[str] = []
    if budget.max_tokens is not None and usage.get("total_tokens", 0) >= budget.max_tokens:
        exhausted.append(f"tokens {usage.get('total_tokens', 0)} >= {budget.max_tokens}")
    if budget.max_cost_usd is not None and spend.cost_usd >= budget.max_cost_usd:
        exhausted.append(f"cost ${spend.cost_usd:.4f} >= ${budget.max_cost_usd}")
    if budget.max_steps is not None and steps >= budget.max_steps:
        exhausted.append(f"steps {steps} >= {budget.max_steps}")

    if exhausted:
        msg = "预算耗尽: " + "; ".join(exhausted)
        if budget.on_exhausted == "abort":
            raise BudgetExhausted(msg)
        logger.warning("[budget] %s（warn 模式继续执行）", msg)
        return

    if not spend.warned:
        soft_hit = False
        if (
            budget.max_tokens is not None
            and usage.get("total_tokens", 0) >= budget.max_tokens * budget.soft_ratio
        ):
            soft_hit = True
        if budget.max_cost_usd is not None and spend.cost_usd >= budget.max_cost_usd * budget.soft_ratio:
            soft_hit = True
        if budget.max_steps is not None and steps >= budget.max_steps * budget.soft_ratio:
            soft_hit = True
        if soft_hit:
            spend.warned = True
            logger.warning(
                "[budget] 接近预算上限（%.0f%%）：tokens=%s cost=$%.4f steps=%s",
                budget.soft_ratio * 100,
                usage.get("total_tokens", 0),
                spend.cost_usd,
                steps,
            )
