"""给压缩中间件补可观测性：摘要失败不再静默。

上游 ContextCompressionMiddleware 的行为是：_generate_structured_summary
里任何异常都被 except 吞掉、记进 state["last_failure_time"]，然后整个
600s 冷却期内**一声不吭**。排查「为什么没压缩」的人只能看到 summary=None，
完全不知道是配额限流、网关超时还是 prompt 被拒 —— 我们为此花了十几轮
跨进程打点才定位到（前面还得出过「before_llm 从未调用」的错误结论）。

这里用最小侵入的方式把失败原因暴露到日志：
- 摘要失败 → WARNING（含异常类型与消息，同一异常 10 分钟内只报一次防刷屏）
- 真正压缩成功 → INFO（压缩前后条数与估算 token）

不改上游行为本身：冷却、阈值、切分逻辑全部保留。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from wuwei.middleware import ContextCompressionMiddleware

logger = logging.getLogger("agenticos.context_compression")

# 同类异常的日志节流：限流往往连续命中，每条都打会淹没日志
_FAIL_LOG_INTERVAL_S = 600.0


class ObservableCompressionMiddleware(ContextCompressionMiddleware):
    """带日志的压缩中间件（行为与上游一致，只加可观测性）。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._last_fail_log_ts = 0.0
        self._last_fail_kind = ""

    async def _generate_structured_summary(self, messages, existing_summary=None, *, ctx=None):
        try:
            summary = await super()._generate_structured_summary(
                messages, existing_summary, ctx=ctx
            )
        except Exception as exc:  # noqa: BLE001 —— 原样抛出，只为记日志
            now = time.monotonic()
            kind = type(exc).__name__
            # BudgetExhausted 等异常上游会继续抛，这里仍要留痕
            if now - self._last_fail_log_ts > _FAIL_LOG_INTERVAL_S or kind != self._last_fail_kind:
                logger.warning(
                    "上下文摘要生成失败（%s: %s）。该提供商可能限流/超时；"
                    "上游将进入 %ds 冷却，期间不会重试压缩。",
                    kind,
                    str(exc)[:200],
                    int(self.failure_cooldown_s),
                )
                self._last_fail_log_ts = now
                self._last_fail_kind = kind
            raise
        if not summary:
            # 上游在 model_call 缺失或响应无正文时返回 None —— 同样是静默黑洞。
            # 更常见的是上游自己 except 掉了异常再返回 None（限流/超时都走这里），
            # 所以这条日志是生产环境唯一的线索，措辞要能直接指路。
            now = time.monotonic()
            if now - self._last_fail_log_ts > _FAIL_LOG_INTERVAL_S:
                has_model_call = bool(ctx and "model_call" in (getattr(ctx, "config", None) or {}))
                logger.warning(
                    "上下文摘要为空（上游未抛异常，多为内部吞掉的限流/超时）。"
                    "has_model_call=%s；接下来 %ds 冷却期内不会再尝试压缩。"
                    "请检查提供商配额与 /chat/completions 响应结构。",
                    has_model_call,
                    int(self.failure_cooldown_s),
                )
                self._last_fail_log_ts = now
                self._last_fail_kind = "empty"
        return summary

    async def before_llm(self, ctx):
        before_msgs = list(getattr(ctx.state, "messages", []) or [])
        result = await super().before_llm(ctx)
        after_msgs = list(getattr(result.state, "messages", []) or [])
        if len(after_msgs) < len(before_msgs):
            logger.info(
                "上下文已压缩：%d → %d 条（估算 %d → %d tokens，trigger=%d）",
                len(before_msgs),
                len(after_msgs),
                self._estimate_tokens(before_msgs),
                self._estimate_tokens(after_msgs),
                min(self.trigger_tokens, int(self.max_tokens * self.trigger_ratio)),
            )
        return result
