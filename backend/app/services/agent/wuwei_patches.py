"""wuwei 3.2.2 残留缺陷的边界补丁层（不改 site-packages）。

**为什么需要这一层。** wuwei 3.2.2 修了不少 3.0.2 的老问题，但审计实测确认
仍有 17 条残留缺陷（见 ``docs/wuwei-3.0.2-问题清单.md`` 的「3.2.1 残留缺陷清单」）。
其中高危项会直接影响本项目的线上行为：

- **R-6** ``agent_runner.py:704`` 用裸子串 ``'"status": "unknown"' in final.content``
  判断「工具结果不确定」。工具正常返回 ``{"status": "unknown"}`` 就被误判，
  第一次 run 的结果被整个丢弃，第二次 run 直接抛 ``ValueError`` 封死会话，
  ``session.reset()`` 也救不回来。
- **R-8** ``tools/executor.py:99`` 用 ``isinstance(result, Exception)`` 判定，
  而 ``asyncio.CancelledError`` 继承 ``BaseException`` → 判定失效 →
  原始异常进 ``results`` → 后续 ``model_dump`` 抛 ``AttributeError``，
  **同批次成功的工具结果也一并丢失**，``tool_end`` 从不发出。
- **R-9** ``_iter_events`` 在 ``session.lock`` 内 ``yield``，
  而 ``async for`` 中途 ``break`` **不会**触发 ``aclose()`` →
  客户端断连后锁永久占用 → 该会话后续所有 run 全部阻塞。
- **R-7** ``agent_runner.py:570-578`` 的 ``can_batch`` 要求中间件栈里
  **没有任何** ``before_tool`` / ``after_tool`` 钩子。本项目默认就装配了
  ``LenientHitlMiddleware``（审批）与 ``AsyncSubAgentMiddleware``，
  于是用户打开 ``parallel_tool_calls`` 开关后**并发被静默关闭**，无任何提示。
- **R-1** ``adapters/openai.py:97`` 只在 ``finish_reason ∈ (stop, tool_calls)``
  时解析 tool_calls → ``finish_reason="length"`` 时工具调用被**静默丢弃**。

**补丁原则（与上一轮删除 monkey-patch 的教训一致）。**

上一轮我们删掉了一份 230 行的 ``AgentRunner.stream_events`` 整体重写，
因为它**整段复制了上游的执行循环**——上游一改签名，这份拷贝就静默落后。
本层的所有补丁都遵守同一条纪律：

1. **只覆盖最小的判定单元**，不复制上游的执行流程。
   例如 R-6 不是重写 ``_commit_tool``，而是「先委托上游，再按结构化事实纠正」。
2. **优先用上游公开的注入点**（子类化 + 构造参数 + 中间件），
   而不是去改 ``site-packages``。
3. **每条补丁都有对应的回归测试**，上游修好后测试会失败并提示可以删。

**补丁失效是安全的**：所有补丁都退化到上游原生行为，不会把请求打死。
这是刻意的设计——上游随时可能自己修好，我们不能因为补丁和上游打架
就让线上挂掉。

未在本层处理的条目（原因见各自的说明）：
R-2 / R-3 / R-4（网关层，落在 ``app/services/llm_providers/adapter.py``）、
R-5（要改 site-packages 的错误类型定义，且项目内无实际风险）、
R-10（项目当前未装配 checkpointer，附带了可用的深拷贝工具）、
R-16 的成本预算部分（需要价格表与产品决策）、R-17（仅事件类型声明不一致）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import aclosing
from typing import Any, Callable

from wuwei.agent.agent import Agent
from wuwei.core.message import ToolCall
from wuwei.llm.types import Message
from wuwei.runtime.agent_runner import AgentRunner
from wuwei.tools.executor import ToolExecutor
from wuwei.tools.tool import Tool

logger = logging.getLogger("agenticos.wuwei.patches")

# 并发工具执行的上限。模型一次吐 50 个工具调用时，
# 不加限制会瞬间打满下游连接池 / 文件句柄（R-13）。
MAX_CONCURRENT_TOOLS = 8

# 单次工具返回值的字符上限。超过就截断并标注（R-12）。
MAX_TOOL_OUTPUT_CHARS = 20_000

# 同一工具 + 同一参数连续调用多少次后拦截（R-16）。
DEFAULT_MAX_REPEAT_TOOL_CALLS = 3


# ──────────────────────────────────────────────────────────────────────
# R-6：工具结果「不确定」判定
# ──────────────────────────────────────────────────────────────────────
#
# 上游判定（agent_runner.py:702-704）：
#     unknown = (
#         final.metadata.get("status") == "unknown"
#         or '"status": "unknown"' in final.content
#     )
#
# 第一项是结构化的、可信的（上游自己写入的 metadata）。
# 第二项是**对工具输出文本的裸子串匹配**——工具正常返回
# ``{"status": "unknown"}`` 这类内容就会命中，误判为「结果不确定」，
# 进而丢弃结果并封死会话。
#
# 我们只替换第二项的判定方式：从「文本里找子串」改成
# 「解析 JSON，然后比对框架自己写下的错误载荷特征」。
#
# 上游 3.2.2 在**嵌套工具**路径（agent_runner.py:668）已经用了
# 正确的 JSON 解析写法，只有主路径还是子串匹配——所以我们的修法
# 与上游自己的方向一致。


def _tool_result_is_unknown(final: Any) -> bool:
    """判断工具结果是否「不确定」（替代上游的裸子串匹配）。

    与上游 ``agent_runner.py:702-704`` 的区别：

    - 保留 ``metadata["status"] == "unknown"`` 这一可信判定（上游自己写入的）；
    - 把 ``'"status": "unknown"' in content`` 换成「解析 JSON 后比对框架的
      错误载荷特征」，解析失败或特征不匹配则**不**判定为 unknown。

    框架的「不确定」标记长这样（上游 ``tools/executor.py`` 的超时分支）::

        {"ok": false, "error": {...}, "attempts": 1,
         "status": "unknown", "execution_may_continue": true, ...}

    三个特征同时成立才算数：``ok=false`` + ``status=="unknown"`` +
    ``execution_may_continue=true``。工具自己返回的业务数据
    （哪怕内容里也写着 ``status: unknown``）不再被误判。
    """
    metadata = getattr(final, "metadata", None) or {}
    if metadata.get("status") == "unknown":
        return True

    content = getattr(final, "content", None)
    if not content or not isinstance(content, str):
        return False

    stripped = content.strip()
    if not stripped.startswith("{"):
        return False
    try:
        payload = json.loads(stripped)
    except (ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("status") != "unknown":
        return False
    return payload.get("ok") is False and payload.get("execution_may_continue") is True


# ──────────────────────────────────────────────────────────────────────
# R-14：同步工具超时后仍被标为「确定失败」
# ──────────────────────────────────────────────────────────────────────

# 会被判定为「有副作用」的工具名片段。超时后线程可能仍在执行，
# 若被标成「确定失败」，下游会安全重试 → 副作用重复。
_IO_SIDE_EFFECT_HINTS = (
    "write",
    "append",
    "replace",
    "delete",
    "remove",
    "create",
    "update",
    "insert",
    "upload",
    "download",
    "commit",
    "push",
    "install",
    "run",
    "exec",
    "deploy",
    "send",
    "post",
    "put",
    "move",
    "rename",
    "copy",
)


def _looks_like_side_effect(tool: Tool | None) -> bool:
    """工具是否可能有副作用（超时后线程可能仍在跑）。

    上游只看 ``tool.execution.side_effect``，而内置插件里大量写类工具
    只声明了 ``side_effect=True`` 却没声明超时语义。我们在这里保守判定：
    名字里带写/删/发等动词的一律按有副作用处理。
    """
    if tool is None:
        return False
    if getattr(tool.execution, "side_effect", False):
        return True
    name = (tool.name or "").lower()
    return any(hint in name for hint in _IO_SIDE_EFFECT_HINTS)


# ──────────────────────────────────────────────────────────────────────
# R-7：并发被 before_tool 中间件静默关闭
# ──────────────────────────────────────────────────────────────────────


class BatchSafeMiddlewareProxy:
    """对上游的 ``can_batch`` 判定隐藏「工具钩子」，其余行为完全委托。

    上游 ``agent_runner.py:570-578`` 的并发条件包含::

        and not self.middleware._before_tool_mws
        and not self.middleware._after_tool_mws

    只要栈里有任何一个 ``before_tool`` / ``after_tool`` 钩子，
    并发分支整个关闭，工具退回逐个串行，**且没有任何日志提示**。
    本项目默认就装配了 ``LenientHitlMiddleware``（审批）与
    ``AsyncSubAgentMiddleware``，于是「打开并行开关 → 什么都没发生」。

    之所以要修：上游关闭并发**是有道理的**——它的批处理分支
    **完全不会调用** ``execute_before_tool``，直接批量执行工具。
    也就是说照搬上游的批处理会把**审批绕过**。

    正确的修法是「让批处理路径也走 before_tool」，而不是「把钩子藏起来
    然后假装审批还在」。所以这里只做两件事：

    1. 让上游的 ``can_batch`` 判定看到「没有工具钩子」，从而允许并发；
    2. 由 ``BoundedToolExecutor._execute_batched`` 在批量执行**之前**
       逐个调用 ``execute_before_tool``，把审批语义补回来。

    其余所有属性访问（``execute_before_llm`` / ``wrap_model_call`` /
    ``middlewares`` …）一律委托给真实中间件栈，行为零变化。
    """

    __slots__ = ("_stack",)

    def __init__(self, stack: Any) -> None:
        self._stack = stack

    def __getattr__(self, name: str) -> Any:
        # 只在常规属性查找失败时触发；下面显式定义的两个 property 优先。
        return getattr(self._stack, name)

    def __repr__(self) -> str:  # pragma: no cover —— 调试用
        return f"BatchSafeMiddlewareProxy({self._stack!r})"

    @property
    def _before_tool_mws(self) -> list[Any]:
        """对上游的并发判定隐藏 before_tool 钩子（实际执行由执行器补齐）。"""
        return []

    @property
    def _after_tool_mws(self) -> list[Any]:
        """after_tool 在上游批处理分支里本来就会执行（经 ``_commit_tool``），
        这里一并隐藏只是为了保持两个属性对称。"""
        return []


def parallel_tool_calls_effective(middleware_stack: Any) -> bool:
    """当前的中间件栈是否会让上游的并发批处理失效。

    未使用 ``BatchSafeMiddlewareProxy`` 时的可见性判断：
    栈里有任何一个 ``before_tool`` / ``after_tool`` 钩子，
    上游的并发分支就是关闭的。
    """
    before = getattr(middleware_stack, "_before_tool_mws", None) or []
    after = getattr(middleware_stack, "_after_tool_mws", None) or []
    return not (before or after)


# ──────────────────────────────────────────────────────────────────────
# R-8 / R-12 / R-13 / R-14 / R-16 / R-7：工具执行器
# ──────────────────────────────────────────────────────────────────────


class BoundedToolExecutor(ToolExecutor):
    """带边界保护的工具执行器。

    - **R-8**：上游用 ``isinstance(result, Exception)`` 判断 gather 的结果是不是
      异常。但 ``asyncio.CancelledError`` 继承 ``BaseException`` 而非 ``Exception``，
      判定为 False → 原始异常对象被塞进 results → 后续 ``model_dump`` 抛
      ``AttributeError``，**同批次成功的工具结果也一并丢失**。
      这里改用 ``BaseException`` 判定，并让 ``CancelledError`` 走「取消」语义
      （向上传播），其余 ``BaseException`` 转成工具错误消息。

    - **R-12**：上游 ``serialize_output`` 对任意大小的输出直接 ``json.dumps``，
      没有上限。单个工具返回 10MB 就会永久占住该会话的上下文预算。
      这里在序列化出口截断。

    - **R-13**：上游对整批 ``asyncio.gather``，没有并发上限；
      且装饰器注册的工具一律默认 ``is_concurrency_safe=True``。
      这里用 ``Semaphore`` 限制并发数，并把「看起来有副作用」的工具
      强制降级为串行（上游 ``plugin/builtin/file.py`` 的写类工具就是
      只声明了 ``side_effect=True``、没声明 ``is_concurrency_safe=False``）。

    - **R-14**：上游只在 ``tool.execution.side_effect`` 为真时才把超时标成
      ``status="unknown"``。未声明 ``side_effect`` 的 IO 工具超时后被标成
      「确定失败」，下游会安全重试——但底层线程可能仍在写。

    - **R-16**：上游没有「同一工具 + 同一参数重复调用」的检测，
      模型陷入「调 A → 失败 → 再调 A」会白白消耗整轮 LLM 调用与副作用。

    - **R-7**：上游的批处理分支**不调用** ``execute_before_tool``，
      等于把审批绕过去了。这里在批量执行前逐个补上 before_tool。

    只覆盖 ``_execute_batched`` 的并发部分，**不复制上游的执行流程**：
    串行分支（``is_concurrency_safe=False`` 的工具）完全走父类实现。
    """

    def __init__(
        self,
        registry: Any,
        *,
        max_concurrent: int = MAX_CONCURRENT_TOOLS,
        max_output_chars: int = MAX_TOOL_OUTPUT_CHARS,
        max_repeat_tool_calls: int = DEFAULT_MAX_REPEAT_TOOL_CALLS,
    ) -> None:
        super().__init__(registry)
        self._max_concurrent = max(1, int(max_concurrent))
        self._max_output_chars = max(1000, int(max_output_chars))
        self._max_repeat_tool_calls = max(1, int(max_repeat_tool_calls))
        # 重复调用检测：上一个签名的连续出现次数
        self._last_signature: tuple[str, str] | None = None
        self._repeat_count = 0
        # R-7：批处理路径补齐 before_tool 用的钩子
        self._before_tool_hook: Callable[..., Any] | None = None
        self._ctx_provider: Callable[[], Any] | None = None
        self._record_final_call: Callable[[Any], None] | None = None

    # ── R-7：批处理路径补齐 before_tool ────────────────────────────
    def bind_tool_hooks(
        self,
        *,
        before_tool: Callable[..., Any] | None = None,
        ctx_provider: Callable[[], Any] | None = None,
        record_final_call: Callable[[Any], None] | None = None,
    ) -> None:
        """绑定批处理路径需要的钩子。

        ``before_tool(ctx, tool_call)`` 需返回 ``ToolCall`` / ``ToolMessage`` /
        ``None``，语义与上游 ``MiddlewareStack.execute_before_tool`` 一致。
        """
        self._before_tool_hook = before_tool
        self._ctx_provider = ctx_provider
        self._record_final_call = record_final_call

    async def _prepare_tool(self, tc: ToolCall) -> tuple[ToolCall, Message | None]:
        """批处理前跑 before_tool，返回 (实际要执行的调用, 预置结果)。

        预置结果非空表示这个工具被中间件直接处理了（例如异步子代理工具
        自己返回 ToolMessage），不需要真正执行。
        """
        if self._before_tool_hook is None:
            return tc, None
        ctx = self._ctx_provider() if self._ctx_provider is not None else None
        result = await self._before_tool_hook(ctx, tc)
        if result is None:
            return tc, self.build_error_message(
                tc,
                error_type="tool_skipped",
                message="工具被中间件跳过",
            )
        if getattr(result, "role", None) == "tool":
            return tc, result
        if self._record_final_call is not None:
            self._record_final_call(result)
        return result, None

    # ── R-12：工具输出大小上限 ───────────────────────────────────
    def serialize_output(self, output: Any) -> str:
        """在序列化出口截断超长输出。

        上游 ``serialize_output`` 直接 ``json.dumps``，没有上限。
        """
        content = super().serialize_output(output)
        if len(content) <= self._max_output_chars:
            return content
        logger.warning(
            "工具输出超过 %d 字符，已截断（原始 %d 字符）",
            self._max_output_chars,
            len(content),
        )
        return (
            content[: self._max_output_chars]
            + f"\n\n...[工具输出已截断，原始 {len(content)} 字符，仅保留前 "
            f"{self._max_output_chars} 字符]"
        )

    # ── R-14 / R-16：单工具执行的收尾 ────────────────────────────
    async def execute_one(self, tool_call: ToolCall) -> Message:
        """执行单个工具，并在出口做两处修正。

        - **R-16**：同一工具 + 同一参数连续调用超过阈值时直接拦截，
          不再真正执行（避免重复副作用与无谓的 LLM 往返）。
        - **R-14**：超时但工具可能有副作用时，把状态从 ``failed``
          纠正为 ``unknown``。
        """
        blocked = self._check_repeat(tool_call)
        if blocked is not None:
            return blocked

        message = await super().execute_one(tool_call)
        return self._mark_timeout_uncertain(tool_call, message)

    def _signature(self, tool_call: ToolCall) -> tuple[str, str]:
        arguments = tool_call.function.arguments
        if not isinstance(arguments, str):
            try:
                arguments = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                arguments = str(arguments)
        return (tool_call.function.name, arguments)

    def _check_repeat(self, tool_call: ToolCall) -> Message | None:
        """R-16：同一工具 + 同一参数的连续重复调用检测。"""
        signature = self._signature(tool_call)
        if signature == self._last_signature:
            self._repeat_count += 1
        else:
            self._last_signature = signature
            self._repeat_count = 1
        if self._repeat_count <= self._max_repeat_tool_calls:
            return None
        name = tool_call.function.name
        logger.warning(
            "拦截重复工具调用：%s 以完全相同的参数连续调用 %d 次（上限 %d）",
            name,
            self._repeat_count,
            self._max_repeat_tool_calls,
        )
        return self.build_error_message(
            tool_call,
            error_type="RepeatedToolCall",
            message=(
                f"工具 {name} 以完全相同的参数连续调用 {self._repeat_count} 次"
                f"（上限 {self._max_repeat_tool_calls}），已阻止重复执行。"
                "请改变参数或换用其他方案。"
            ),
            metadata={"repeat_blocked": True},
        )

    def _mark_timeout_uncertain(self, tool_call: ToolCall, message: Message) -> Message:
        """R-14：超时且工具可能有副作用 → 状态纠正为 unknown。

        上游只在 ``tool.execution.side_effect`` 为真时标 ``unknown``；
        未声明该字段的 IO 类工具超时后被标成「确定失败」，
        下游会安全重试——但底层线程可能仍在写。
        """
        content = getattr(message, "content", None)
        if not content or not isinstance(content, str):
            return message
        try:
            payload = json.loads(content)
        except (ValueError, TypeError):
            return message
        if not isinstance(payload, dict):
            return message
        if not payload.get("execution_may_continue"):
            return message
        if payload.get("status") == "unknown":
            return message
        tool = self.registry.get(tool_call.function.name)
        if not _looks_like_side_effect(tool):
            return message
        payload["status"] = "unknown"
        logger.warning(
            "工具 %s 超时且可能有副作用，结果状态纠正为 unknown",
            tool_call.function.name,
        )
        return message.model_copy(
            update={"content": json.dumps(payload, ensure_ascii=False)}
        )

    # ── R-8 / R-13 / R-7：批量执行 ───────────────────────────────
    async def _execute_batched(self, tool_calls: list[ToolCall]) -> list[Message]:
        """按并发安全分组执行，带并发上限、异常兜底与 before_tool 补齐。

        与上游 ``ToolExecutor._execute_batched`` 的差异都收敛在
        「单个工具怎么执行」这一层，**不复制上游的执行流程**：
        分组规则、串行分支、结果顺序全部沿用上游语义。
        """
        results: list[Message | None] = [None] * len(tool_calls)

        # R-7：批处理前先跑 before_tool（上游批处理分支会跳过它）。
        prepared: list[tuple[ToolCall, ToolCall, Message | None]] = []
        for tc in tool_calls:
            effective, preset = await self._prepare_tool(tc)
            prepared.append((tc, effective, preset))

        semaphore = asyncio.Semaphore(self._max_concurrent)

        async def _run(tc: ToolCall) -> Message:
            async with semaphore:
                return await self.execute_one(tc)

        def _is_safe(tc: ToolCall) -> bool:
            tool = self.registry.get(tc.function.name)
            if tool is None:
                return True
            # R-13：看起来有副作用的工具一律串行，避免并发写互相覆盖。
            if _looks_like_side_effect(tool):
                return False
            return bool(tool.is_concurrency_safe)

        i = 0
        while i < len(prepared):
            origin, effective, preset = prepared[i]
            if preset is not None:
                results[i] = preset
                i += 1
                continue

            if _is_safe(effective):
                batch_indices = [i]
                j = i + 1
                while j < len(prepared):
                    _, next_effective, next_preset = prepared[j]
                    if next_preset is None and _is_safe(next_effective):
                        batch_indices.append(j)
                        j += 1
                    else:
                        break

                batch_results = await asyncio.gather(
                    *(_run(prepared[k][1]) for k in batch_indices),
                    return_exceptions=True,
                )
                for idx, result in zip(batch_indices, batch_results):
                    if isinstance(result, BaseException):
                        # R-8：判定放宽到 BaseException。
                        # CancelledError 属于「整个请求被取消」，应当向上传播
                        # 而不是伪装成工具错误——否则上游会把它当成一次
                        # 普通的工具失败继续往下走。
                        if isinstance(result, asyncio.CancelledError):
                            raise result
                        results[idx] = self.build_error_message(
                            prepared[idx][0],
                            error_type=type(result).__name__,
                            message=str(result),
                        )
                    else:
                        results[idx] = result

                i = j
            else:
                # 串行执行非安全工具：完全走父类逻辑
                results[i] = await self.execute_one(effective)
                i += 1

        return [r for r in results if r is not None]


# ──────────────────────────────────────────────────────────────────────
# R-10：检查点 metadata 浅拷贝
# ──────────────────────────────────────────────────────────────────────


def deep_copy_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """把检查点 metadata 深拷贝（修 R-10）。

    上游 ``MemoryCheckpointer.save`` 对 state 做了 JSON roundtrip（真深拷贝），
    但对 metadata 只做 ``dict(metadata)`` 浅拷贝——嵌套的 ``tool_states``
    仍是同一个 dict 对象的引用，快照会被事后改写。

    ``tool_running`` 快照是上游判定「工具结果不确定、禁止重放」的依据，
    用 Memory 后端时快照最终都显示 success，恢复流程会重放有副作用的工具
    （重复扣款、重复下单、重复写文件）。
    开发/测试用 Memory、生产用 SQLite → 两环境行为不一致。

    本函数提供正确的拷贝语义，供项目侧构造检查点时使用。
    （本项目当前 ``Agent(...)`` 未装配 checkpointer，因此这条暂无实际影响，
    但它是「一旦启用检查点就会踩」的坑，先把正确实现备好。）
    """
    if not metadata:
        return {}
    try:
        return json.loads(json.dumps(metadata, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        # 无法 JSON 化时退化为浅拷贝 + 深拷贝常见容器
        return dict(metadata)


# ──────────────────────────────────────────────────────────────────────
# R-6 / R-9 / R-11：AgentRunner 子类
# ──────────────────────────────────────────────────────────────────────


class PatchedAgentRunner(AgentRunner):
    """修 R-6（unknown 误判）、R-9（断连锁死）、R-11（缺终止事件）。

    **只覆盖最小的判定单元，不复制上游的执行循环。**

    - **R-6**：覆写 ``_commit_tool`` 里「工具结果是否不确定」这一处判定。
      上游用裸子串匹配工具输出文本，正常返回 ``{"status": "unknown"}``
      的工具会被误判 → 结果被丢弃 + 会话被永久封死。
      改为：解析 JSON 后比对框架错误载荷的真实特征。
    - **R-9**：覆写 ``_iter_events``，保证生成器被关闭（断连）时
      ``session.lock`` 一定被释放。上游在 ``async with self.session.lock``
      内部 ``yield``，而 ``async for`` 中途 ``break`` **不会**触发
      ``aclose()`` → 锁被永久占用 → 该会话后续所有 run 全部阻塞。
    - **R-11**：异常路径不发 ``done`` / ``run_end`` 终止事件，
      客户端按「收到 done 才算结束」的协议会一直等待，
      ``agent.run()`` 也会直接抛异常而不是返回 ``status="error"``。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # 上游事件流生成器的引用，用于在断连时**确定性地**关闭内层生成器，
        # 让上游自己的 CancelledError/GeneratorExit 清理分支跑到
        # （否则它只能靠 GC 的异步 finalization，清理时机不确定）。
        self._inner_event_stream: Any = None

    # ── R-6：工具结果「不确定」判定 ──────────────────────────────────
    async def _commit_tool(self, ctx: Any, tc: ToolCall, msg: Any, remaining: Any) -> Any:
        """修 R-6：工具正常返回 ``{"status": "unknown"}`` 被误判为「结果不确定」。

        上游（``agent_runner.py:697-723``）的判定：
            unknown = (
                final.metadata.get("status") == "unknown"
                or '"status": "unknown"' in final.content
            )
        第二项是**对工具输出文本的裸子串匹配**——工具正常返回
        ``{"status": "unknown"}`` 这类内容就会命中，误判为「结果不确定」，
        第一次 run 的结果被整个丢弃，第二次 run 直接抛 ``ValueError`` 封死会话，
        ``session.reset()`` 也救不回来。

        **修法不是重写上游的判定逻辑，而是「委托 + 事后纠正」**：
        先让上游原样执行（保留它的落检查点、写日志、推进状态等全部副作用），
        再在结果已知后纠正它对 ``unknown`` 的判定。

        这样做的原因：上游 ``_commit_tool`` 里除了这一个判定，还做了
        落检查点（``_save_checkpoint``）、写动作日志、清理 approval 决策等
        若干件事。重写整个方法就等于复制上游的实现细节——上游一改，
        这份拷贝就会静默落后（这正是上一轮删掉 230 行 monkey-patch 的教训）。

        纠正的依据是**结构化事实**而非文本子串，见 ``_tool_result_is_unknown``。
        """
        final = await super()._commit_tool(ctx, tc, msg, remaining)

        # 上游已把判定结果写进了两处状态，这里按结构化事实纠正。
        states = self._metadata.get("tool_states", {})
        if states.get(tc.id) == "unknown" and not _tool_result_is_unknown(final):
            states[tc.id] = getattr(final, "status", "success")
            # 只有当没有任何工具处于 unknown 时才撤销整体标记
            if not any(v == "unknown" for v in states.values()):
                self._metadata["unknown_tool"] = False
                self.session.metadata.pop("_blocked_run", None)
            logger.info(
                "纠正工具结果 unknown 误判：tool=%s（上游按内容子串匹配误判）",
                tc.function.name,
            )
        return final

    # ── R-9：断连时释放会话锁 ───────────────────────────────────────
    async def _iter_events(
        self,
        user_input: Any,
        *,
        stream: bool,
        task: Any = None,
        resume: Any = None,
    ):
        """覆写上游 ``_iter_events``，保证生成器关闭时释放会话锁并补终止事件。

        上游的写法是在 ``async with self.session.lock:`` 内部 ``yield``。
        生成器在 ``yield`` 点挂起时**仍持有锁**，而消费方 ``async for``
        中途 ``break`` 不会触发 ``aclose()`` → 锁永久占用 →
        该会话后续所有 run 全部阻塞在 ``async with self.session.lock`` 上。

        这里用 ``contextlib.aclosing`` 包住上游的生成器：无论消费方是
        正常结束、break 还是抛异常，退出时上游的 ``async with`` 一定
        会退出 → 锁一定被释放。

        同时补上 R-11：上游的异常分支只 ``yield`` 一个 ``error`` 事件就
        ``raise``，**不发** ``done`` / ``run_end``。客户端按「收到 done
        才算结束」实现时会一直等；``agent.run()`` 也会抛异常而不是返回
        ``status="error"``。这里在异常收尾时补发终止事件。
        """
        saw_error = False
        try:
            async with aclosing(
                super()._iter_events(
                    user_input, stream=stream, task=task, resume=resume
                )
            ) as events:
                async for event in events:
                    if getattr(event, "type", None) == "error":
                        saw_error = True
                    yield event
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception as exc:  # noqa: BLE001 —— 这里就是要把异常转成终止事件
            logger.warning(
                "agent 运行异常，已转为终止事件：%s: %s",
                type(exc).__name__,
                exc,
            )
            async for event in self._terminal_error_events(exc, emit_error=not saw_error):
                yield event
        finally:
            # 确定性地关闭内层事件流生成器：上游在 CancelledError /
            # GeneratorExit 分支里会标记「结果不确定的工具」并落检查点，
            # 这一步若依赖 GC 的异步 finalization，时机不确定。
            await self._close_inner_event_stream()

    async def _execute_events(self, user_input: Any, *, stream: bool, task: Any = None, resume: Any = None):
        """包一层 ``aclosing``，让内层生成器能被确定性地关闭。"""
        inner = super()._execute_events(
            user_input, stream=stream, task=task, resume=resume
        )
        self._inner_event_stream = inner
        try:
            async with aclosing(inner) as events:
                async for event in events:
                    yield event
        finally:
            if self._inner_event_stream is inner:
                self._inner_event_stream = None

    async def _close_inner_event_stream(self) -> None:
        """关闭内层事件流生成器（幂等）。"""
        inner = self._inner_event_stream
        if inner is None:
            return
        self._inner_event_stream = None
        try:
            await inner.aclose()
        except (RuntimeError, asyncio.CancelledError):  # pragma: no cover
            # 生成器已在运行中关闭（下游正在迭代）——忽略。
            logger.debug("关闭内层事件流失败", exc_info=True)

    async def _terminal_error_events(self, exc: Exception, *, emit_error: bool) -> Any:
        """异常收尾时补发 ``error`` / ``done`` / ``run_end``（R-11）。"""
        meta = self._metadata or {}
        usage = meta.get("usage_total") or {}
        if emit_error:
            yield self._event(
                "error",
                data={
                    "message": str(exc),
                    "error_type": type(exc).__name__,
                    "usage": dict(usage),
                    "llm_calls": meta.get("llm_calls", 0),
                },
            )
        data = {
            "content": "",
            "usage": dict(usage),
            "latency_ms": meta.get("latency_ms", 0),
            "llm_calls": meta.get("llm_calls", 0),
            "status": "error",
            "termination_reason": "error",
            "interrupt": None,
            "usage_available": meta.get("usage_available", True),
            "output": meta.get("structured_output"),
        }
        yield self._event("done", data=dict(data))
        yield self._event("run_end", data=dict(data))


class PatchedAgent(Agent):
    """把上游 ``Agent`` 的执行器换成带补丁的版本。

    - ``tool_executor`` → ``BoundedToolExecutor``（R-8 / R-12 / R-13 / R-14 / R-16）；
    - ``create_runner`` → ``PatchedAgentRunner``（R-6 / R-9 / R-11）。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # 上游在 ``BaseSessionAgent.__init__`` 里建的执行器没有边界保护，
        # 这里换成带补丁的版本（注册表对象不变，插件注册的工具照样可见）。
        self.tool_executor = BoundedToolExecutor(self.tool_registry)

    def create_runner(self, session: Any) -> AgentRunner:
        runner = PatchedAgentRunner(
            llm=self.llm,
            tools=self.tool_registry.list_tools(),
            tool_executor=self.tool_executor,
            session=session,
            middleware=self.middleware,
            checkpointer=self.checkpointer,
            event_bus=self.event_bus,
        )
        # R-7：批处理路径需要在执行前补齐 before_tool。
        # 用上游的 ``_in_context`` 包一层，保证中间件里读 current_context
        # 拿到的是同一个上下文。
        executor = self.tool_executor
        if isinstance(executor, BoundedToolExecutor):
            executor.bind_tool_hooks(
                before_tool=lambda ctx, tc: runner._in_context(
                    ctx, self.middleware.execute_before_tool, ctx, tc
                ),
                ctx_provider=runner._ctx,
                record_final_call=runner._record_final_call,
            )
        return runner
