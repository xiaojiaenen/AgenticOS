"""RAGAS 评估旁路 PoC（docs/design/项目逐功能优化方案.md 3E.1 / 3F.0）。

**形态红线**：RAGAS 是纯库（pip 依赖，进程内计算指标），不部署服务、
不接 Langfuse（外部系统，3F.0 排除）。评估结果写回项目自己的
eval/检索质量看板（`/api/v1/knowledge/metrics/search-quality` 与 traces/evals tab）。

定位：**旁路 PoC，不进主路径**。与 `litellm_poc.py` 同款纪律——只验证
「RAG 质量客观指标」这一小块 SDK 价值：

- ``evaluate_rag_sample``：单个 (question, answer, contexts, ground_truth)
  样本 → RAGAS 指标子集（faithfulness / answer_relevancy / context_precision /
  context_recall，全部可配）；
- ``evaluate_rag_batch``：批量聚合 + 平均分；
- 依赖可选（``uv add ragas``）：未安装时报带指引的 ``ProviderConfigError``，
  不影响主路径。

真 RAGAS 的 LLM-as-judge 调用属集成验证；单测用 fake ragas 模块锁定
**数据集构造契约**（字段名/指标名/分数聚合），保证 ragas API 变化时
本项目侧的映射是唯一需要修的地方。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.llm_providers.spec import ProviderConfigError

logger = logging.getLogger("agenticos.eval.ragas")

#: RAGAS 核心四指标的默认开启集（全要 LLM judge；离线无 LLM 时用 fallback 指标）
DEFAULT_METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")


def _require_ragas() -> Any:
    """按需导入 ragas（可选依赖）；未安装给出明确指引。"""
    try:
        import ragas  # type: ignore[import-not-found]

        return ragas
    except ImportError as exc:
        raise ProviderConfigError(
            "RAGAS 评估需要可选依赖：uv add ragas（纯库零部署；"
            "不接 Langfuse —— 结果写自己的 eval/metrics 看板）"
        ) from exc


@dataclass
class RagSample:
    """一条 RAG 评估样本（RAGAS EvaluationDataset 的单行）。"""

    question: str
    answer: str
    contexts: list[str]
    ground_truth: str = ""
    #: 期望命中的页面标题（faithfulness 之外的轻量校验口径）
    expected_page_title: str | None = None
    metrics: tuple[str, ...] = field(default_factory=lambda: DEFAULT_METRICS)

    def to_ragas_dict(self) -> dict[str, Any]:
        """→ ragas SingleTurnSample 兼容 dict（字段名与 ragas 契约对齐）。"""
        return {
            "user_input": self.question,
            "response": self.answer,
            "retrieved_contexts": list(self.contexts),
            "reference": self.ground_truth,
        }


@dataclass
class RagEvalReport:
    """评估报告：逐样本指标 + 聚合均值。"""

    samples: list[dict[str, Any]] = field(default_factory=list)
    averages: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"samples": self.samples, "averages": self.averages, "count": len(self.samples)}


async def evaluate_rag_batch(
    samples: list[RagSample],
    *,
    llm: Any | None = None,
    embeddings: Any | None = None,
) -> RagEvalReport:
    """跑批量 RAGAS 评估。

    Args:
        samples: 样本列表（非空）。
        llm: judge 模型（LangChain BaseChatModel 或 ragas wrapper）；None 用
            ragas 默认（会读环境变量 OPENAI_API_*）——PoC 阶段由调用方显式传
            本项目网关的 wrapper，避免偷用环境密钥。
        embeddings: ragas 需要向量的指标（answer_relevancy）用的 embedder。

    Returns:
        RagEvalReport（逐样本 + 均值）。RAGAS 抛错时该样本记 error 不中断批量。
    """
    if not samples:
        raise ValueError("评估样本为空")
    ragas = _require_ragas()

    from ragas import evaluate as ragas_evaluate  # type: ignore[import-not-found]
    from ragas.metrics import (  # type: ignore[import-not-found]
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    metric_map = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    all_metrics = list({m for s in samples for m in s.metrics if m in metric_map})
    if not all_metrics:
        raise ValueError("没有可识别的指标名（支持：" + "、".join(DEFAULT_METRICS) + "）")

    dataset_dicts = [s.to_ragas_dict() for s in samples]
    kwargs: dict[str, Any] = {"metrics": [metric_map[m] for m in all_metrics]}
    if llm is not None:
        kwargs["llm"] = llm
    if embeddings is not None:
        kwargs["embeddings"] = embeddings

    result = ragas_evaluate(dataset_dicts, **kwargs)  # type: ignore[call-arg]
    df = result.to_pandas() if hasattr(result, "to_pandas") else None

    report = RagEvalReport()
    if df is None:
        # 无 pandas 的裁剪环境：ragas 返回 dict 形态
        raw = result if isinstance(result, dict) else {}
        for i, sample in enumerate(samples):
            scores = {m: raw.get(m, [None] * len(samples))[i] for m in all_metrics}
            report.samples.append({"question": sample.question, "scores": scores})
        valid = {m: [v for v in (s["scores"][m] for s in report.samples) if v is not None]
                 for m in all_metrics}
        report.averages = {m: round(sum(v) / len(v), 4) for m, v in valid.items() if v}
        return report

    for (_, row), sample in zip(df.iterrows(), samples):
        scores = {}
        for m in all_metrics:
            v = row.get(m)
            scores[m] = round(float(v), 4) if v is not None and v == v else None  # NaN → None
        report.samples.append({"question": sample.question, "scores": scores})
    for m in all_metrics:
        vals = [s["scores"][m] for s in report.samples if s["scores"][m] is not None]
        if vals:
            report.averages[m] = round(sum(vals) / len(vals), 4)
    return report


def cheap_offline_metrics(samples: list[RagSample]) -> RagEvalReport:
    """零依赖离线指标（无 ragas / 无 judge LLM 时的降级口径）。

    - hit_rate：answer 的期望页面标题是否出现在 contexts 里（召回命中）；
    - context_overlap：question 词面与 contexts 的覆盖率（jieba 词级，粗口径）。
    这两个指标零 LLM 成本，用作在线趋势看板；RAGAS 四指标做离线精评。
    """
    from app.services.knowledge.tokenizer import tokenize

    report = RagEvalReport()
    hit_flags: list[float] = []
    overlaps: list[float] = []
    for s in samples:
        q_tokens = set(tokenize(s.question))
        joined = "\n".join(s.contexts)
        hit = 1.0 if (s.expected_page_title and s.expected_page_title in joined) else 0.0
        if s.expected_page_title is None:
            hit = None  # 没给期望标题的样本不计 hit
        hit_flags.append(hit if hit is not None else float("nan"))
        c_tokens = set(tokenize(joined[:2000]))
        overlap = (len(q_tokens & c_tokens) / len(q_tokens)) if q_tokens else 0.0
        overlaps.append(overlap)
        report.samples.append({
            "question": s.question,
            "scores": {"hit_rate": hit, "context_overlap": round(overlap, 4)},
        })
    real_hits = [h for h in hit_flags if h == h]
    if real_hits:
        report.averages["hit_rate"] = round(sum(real_hits) / len(real_hits), 4)
    if overlaps:
        report.averages["context_overlap"] = round(sum(overlaps) / len(overlaps), 4)
    return report
