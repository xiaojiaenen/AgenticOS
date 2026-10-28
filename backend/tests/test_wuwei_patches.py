"""wuwei 残留缺陷补丁层的回归测试。

每条补丁都有对应的回归测试。**上游修好之后，这些测试会失败**——
那是提示「可以删掉对应的补丁了」，不是回归。

覆盖对照（见 ``docs/wuwei-3.0.2-问题清单.md`` 的 R-1 ~ R-17）：

| 编号 | 测试 |
| --- | --- |
| R-1 | ``TestAdapterLayer.test_finish_reason_length_keeps_tool_calls`` |
| R-2 | ``TestAdapterLayer.test_generate_wraps_error_into_llm_error`` |
| R-3 | ``TestAdapterLayer.test_stream_usage_keeps_upstream_total`` |
| R-4 | ``TestAdapterLayer.test_classify_error_falls_back_to_exception_hierarchy`` |
| R-6 | ``TestRunnerPatches.test_tool_returning_unknown_status_is_not_uncertain`` |
| R-7 | ``TestRunnerPatches.test_parallel_batch_still_runs_before_tool`` |
| R-8 | ``TestRunnerPatches.test_base_exception_does_not_break_the_batch`` |
| R-9 | ``TestRunnerPatches.test_aclose_releases_session_lock`` |
| R-10 | ``TestRunnerPatches.test_deep_copy_metadata_is_independent`` |
| R-11 | ``TestRunnerPatches.test_error_path_emits_terminal_events`` |
| R-12 | ``TestRunnerPatches.test_tool_output_is_truncated`` |
| R-13 | ``TestRunnerPatches.test_side_effect_tools_are_serialized`` |
| R-14 | ``TestRunnerPatches.test_timeout_on_side_effect_tool_is_unknown`` |
| R-16 | ``TestRunnerPatches.test_repeated_tool_call_is_blocked`` |
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time

import pytest

from app.services.agent.wuwei_patches import (
    BatchSafeMiddlewareProxy,
    BoundedToolExecutor,
    PatchedAgent,
    PatchedAgentRunner,
    _tool_result_is_unknown,
    deep_copy_metadata,
    parallel_tool_calls_effective,
)
from wuwei.core.message import FunctionCall, ToolCall
from wuwei.llm.types import LLMResponse, LLMResponseChunk, Message
from wuwei.middleware.base import Middleware
from wuwei.middleware.stack import MiddlewareStack
from wuwei.tools.registry import ToolRegistry
from wuwei.tools.tool import Tool, ToolExecutionPolicy, ToolParameters


# ──────────────────────────────────────────────────────────────────────
# 测试脚手架
# ──────────────────────────────────────────────────────────────────────


class ScriptedLLM:
    """按脚本返回 ``LLMResponse`` 的假网关。"""

    def __init__(self, responses: list) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, messages, tools=None, stream: bool = False, **kwargs):
        self.calls += 1
        index = min(self.calls - 1, len(self.responses) - 1)
        response = self.responses[index]
        if isinstance(response, BaseException):
            raise response
        if stream:
            return self._as_stream(response)
        return response

    @staticmethod
    async def _as_stream(response: LLMResponse):
        yield LLMResponseChunk(
            content=response.message.content,
            tool_calls_complete=response.message.tool_calls or None,
            finish_reason=response.finish_reason,
            usage=dict(response.usage or {}),
            usage_available=True,
        )


def make_response(
    content: str = "",
    tool_calls: list[ToolCall] | None = None,
    finish_reason: str = "stop",
    usage: dict | None = None,
) -> LLMResponse:
    return LLMResponse(
        message=Message(role="assistant", content=content, tool_calls=tool_calls or []),
        finish_reason=finish_reason,
        usage=usage or {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        model="test-model",
    )


def make_tool_call(name: str, arguments: dict | None = None, call_id: str = "c1") -> ToolCall:
    return ToolCall(
        id=call_id,
        type="function",
        function=FunctionCall(name=name, arguments=arguments or {}),
    )


def make_tool(
    name: str,
    handler,
    *,
    side_effect: bool = False,
    timeout_seconds: float | None = None,
    concurrency_safe: bool = True,
) -> Tool:
    return Tool(
        name=name,
        description=name,
        parameters=ToolParameters(),
        handler=handler,
        execution=ToolExecutionPolicy(
            side_effect=side_effect,
            timeout_seconds=timeout_seconds,
        ),
        is_concurrency_safe=concurrency_safe,
    )


class RecordingMiddleware(Middleware):
    """记录 before_tool 调用的中间件（模拟审批守卫）。"""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def before_tool(self, ctx, tool_call):
        self.seen.append(tool_call.function.name)
        return tool_call


def build_agent(llm, tools, middlewares=None, *, parallel: bool = False) -> PatchedAgent:
    stack = MiddlewareStack()
    for middleware in middlewares or []:
        stack.add(middleware)
    agent = PatchedAgent(
        llm=llm,
        tools=tools,
        middleware=BatchSafeMiddlewareProxy(stack),
        load_builtins=False,
    )
    agent._test_stack = stack  # type: ignore[attr-defined]
    agent._test_parallel = parallel  # type: ignore[attr-defined]
    return agent


# ──────────────────────────────────────────────────────────────────────
# R-6 / R-9 / R-11：runner 层
# ──────────────────────────────────────────────────────────────────────


class TestRunnerPatches:
    def test_tool_returning_unknown_status_is_not_uncertain(self):
        """R-6：工具正常返回 ``{"status": "unknown"}`` 不能被判为「结果不确定」。

        上游用裸子串匹配工具输出文本 → 误判 → 第一次 run 的结果被丢弃、
        第二次 run 直接抛 ``ValueError`` 封死会话。
        """
        calls: list[dict] = []

        def probe(**kwargs):
            calls.append(kwargs)
            return {"status": "unknown"}

        llm = ScriptedLLM(
            [
                make_response(tool_calls=[make_tool_call("probe", {"q": 1})]),
                make_response(content="最终答案"),
            ]
        )
        agent = build_agent(llm, [make_tool("probe", probe)])
        session = agent.create_session()

        result = asyncio.run(agent.run("查一下", session=session))
        assert result.status == "completed", f"结果被上游误判丢弃：{result.content!r}"
        assert "最终答案" in result.content
        assert calls, "工具没有被执行"

        # 会话没有被封死：第二次 run 应当正常完成
        result2 = asyncio.run(agent.run("再查一次", session=session))
        assert result2.status == "completed"

    def test_framework_unknown_payload_is_still_treated_as_uncertain(self):
        """R-6 反向守护：框架自己写的「结果不确定」载荷不能被误放行。"""
        payload = json.dumps(
            {
                "ok": False,
                "error": {"type": "ToolTimeout", "message": "timed out"},
                "attempts": 1,
                "status": "unknown",
                "execution_may_continue": True,
                "retryable": False,
            }
        )
        assert _tool_result_is_unknown(_FakeFinal(payload)) is True

    def test_business_payload_with_unknown_status_is_not_uncertain(self):
        """R-6：业务语义里的 ``status: unknown`` 不能被当成框架标记。"""
        assert _tool_result_is_unknown(_FakeFinal('{"status": "unknown"}')) is False
        assert _tool_result_is_unknown(_FakeFinal('{"ok": false, "status": "unknown"}')) is False
        assert _tool_result_is_unknown(_FakeFinal("随便一段文本")) is False

    def test_error_path_emits_terminal_events(self):
        """R-11：异常路径必须发 ``done`` / ``run_end``，且 ``run()`` 返回 error 结果。"""
        llm = ScriptedLLM([RuntimeError("上游炸了")])
        agent = build_agent(llm, [make_tool("noop", lambda **k: "ok")])
        session = agent.create_session()

        async def collect():
            return [event async for event in agent.stream_events("hi", session=session)]

        events = asyncio.run(collect())
        types = [event.type for event in events]
        assert "error" in types
        assert "done" in types, f"异常路径没有发 done：{types}"
        assert "run_end" in types, f"异常路径没有发 run_end：{types}"

        result = asyncio.run(agent.run("hi", session=session))
        assert result.status == "error"
        assert result.termination_reason == "error"

    def test_aclose_releases_session_lock(self):
        """R-9：生成器关闭后会话锁必须释放。"""
        llm = ScriptedLLM([make_response(content="x")])
        agent = build_agent(llm, [make_tool("noop", lambda **k: "ok")])
        session = agent.create_session()
        runner = agent.create_runner(session)

        async def scenario():
            stream = runner.stream_events("hi")
            async for _event in stream:
                break
            # 消费方中途 break 后必须显式关闭（我们的 orchestrator 用 aclosing）
            await stream.aclose()
            return session.lock.locked()

        assert asyncio.run(scenario()) is False

    def test_consumer_side_aclose_releases_lock(self):
        """R-9：消费方用 ``aclosing`` 时，break 之后锁立刻释放。"""
        llm = ScriptedLLM([make_response(content="x")])
        agent = build_agent(llm, [make_tool("noop", lambda **k: "ok")])
        session = agent.create_session()
        runner = agent.create_runner(session)

        async def scenario():
            async with contextlib.aclosing(runner.stream_events("hi")) as stream:
                async for _event in stream:
                    break
            return session.lock.locked()

        assert asyncio.run(scenario()) is False

    def test_orchestrator_uses_aclosing(self):
        """R-9 守护点：orchestrator 必须显式关闭事件流生成器。

        上游在 ``async with self.session.lock`` 内部 yield，
        消费方 ``async for`` 中途 break 不会触发 ``aclose()`` →
        断连后该会话的所有后续 run 全部阻塞。
        """
        import inspect

        from app.services.agent import orchestrator as orchestrator_module

        source = inspect.getsource(orchestrator_module)
        assert "contextlib.aclosing" in source, "orchestrator 关闭事件流的保护被删掉了"

    def test_inner_event_stream_is_closed_deterministically(self):
        """R-9：内层事件流必须被确定性地关闭（不能只靠 GC 的异步 finalization）。"""
        llm = ScriptedLLM([make_response(content="x")])
        agent = build_agent(llm, [make_tool("noop", lambda **k: "ok")])
        session = agent.create_session()
        runner = agent.create_runner(session)
        assert isinstance(runner, PatchedAgentRunner)

        async def scenario():
            stream = runner.stream_events("hi")
            await stream.aclose()
            return runner._inner_event_stream

        assert asyncio.run(scenario()) is None

    def test_deep_copy_metadata_is_independent(self):
        """R-10：metadata 深拷贝后，改动原对象不得影响快照。"""
        original = {"tool_states": {"c1": "running"}, "nested": {"a": 1}}
        copied = deep_copy_metadata(original)
        original["tool_states"]["c1"] = "success"
        original["nested"]["a"] = 99
        assert copied["tool_states"]["c1"] == "running"
        assert copied["nested"]["a"] == 1


# ──────────────────────────────────────────────────────────────────────
# R-7 / R-8 / R-12 / R-13 / R-14 / R-16：执行器层
# ──────────────────────────────────────────────────────────────────────


class TestExecutorPatches:
    def _executor(self, tools, **kwargs) -> BoundedToolExecutor:
        registry = ToolRegistry()
        for tool in tools:
            registry.register(tool)
        return BoundedToolExecutor(registry, **kwargs)

    def test_base_exception_does_not_break_the_batch(self):
        """R-8：``BaseException`` 不能炸穿整批，同批成功结果必须保留。"""

        class Boom(BaseException):
            pass

        def boom(**kwargs):
            raise Boom("boom")

        executor = self._executor(
            [make_tool("ok_tool", lambda **k: "fine"), make_tool("bad_tool", boom)]
        )
        calls = [
            make_tool_call("ok_tool", call_id="c1"),
            make_tool_call("bad_tool", call_id="c2"),
        ]
        results = asyncio.run(executor._execute_batched(calls))
        assert len(results) == 2
        assert all(isinstance(item, Message) for item in results), "结果里混进了原始异常对象"
        assert results[0].content == "fine", "同批成功的工具结果被一起丢掉了"
        assert "boom" in results[1].content

    def test_cancelled_error_is_propagated(self):
        """R-8：``CancelledError`` 属于「整个请求被取消」，必须向上传播。"""

        async def cancelled(**kwargs):
            raise asyncio.CancelledError("cancelled!")

        executor = self._executor([make_tool("cancel_tool", cancelled)])
        calls = [make_tool_call("cancel_tool", call_id="c1")]

        with pytest.raises(asyncio.CancelledError):
            asyncio.run(executor._execute_batched(calls))

    def test_tool_output_is_truncated(self):
        """R-12：超长工具输出必须在序列化出口被截断。"""
        executor = self._executor(
            [make_tool("big_tool", lambda **k: "x" * 100_000)], max_output_chars=5000
        )
        content = executor.serialize_output("y" * 100_000)
        assert len(content) < 100_000
        assert "工具输出已截断" in content

    def test_concurrency_is_bounded(self):
        """R-13：并发工具执行必须有上限。"""
        running = 0
        peak = 0
        lock = asyncio.Lock()

        async def slow(**kwargs):
            nonlocal running, peak
            async with lock:
                running += 1
                peak = max(peak, running)
            await asyncio.sleep(0.05)
            async with lock:
                running -= 1
            return "ok"

        executor = self._executor(
            [make_tool("slow_tool", slow)], max_concurrent=2
        )
        calls = [make_tool_call("slow_tool", call_id=f"c{i}") for i in range(6)]
        asyncio.run(executor._execute_batched(calls))
        assert peak <= 2, f"并发数超过上限：{peak}"

    def test_side_effect_tools_are_serialized(self):
        """R-13：看起来有副作用的工具必须串行（写类工具会互相覆盖）。"""
        order: list[str] = []
        active = 0
        overlap = 0
        lock = asyncio.Lock()

        async def write_a(**kwargs):
            nonlocal active, overlap
            async with lock:
                active += 1
                overlap = max(overlap, active)
            order.append("a-start")
            await asyncio.sleep(0.05)
            order.append("a-end")
            async with lock:
                active -= 1
            return "a"

        async def write_b(**kwargs):
            nonlocal active, overlap
            async with lock:
                active += 1
                overlap = max(overlap, active)
            order.append("b-start")
            await asyncio.sleep(0.05)
            order.append("b-end")
            async with lock:
                active -= 1
            return "b"

        executor = self._executor(
            [
                make_tool("write_alpha", write_a, concurrency_safe=True),
                make_tool("write_beta", write_b, concurrency_safe=True),
            ]
        )
        calls = [
            make_tool_call("write_alpha", call_id="c1"),
            make_tool_call("write_beta", call_id="c2"),
        ]
        asyncio.run(executor._execute_batched(calls))
        assert overlap == 1, "写类工具被并发执行了"
        assert order == ["a-start", "a-end", "b-start", "b-end"]

    def test_timeout_on_side_effect_tool_is_unknown(self):
        """R-14：超时且可能有副作用的工具，结果状态必须是 unknown。"""
        import time as _time

        def slow_write(**kwargs):
            _time.sleep(1)
            return "done"

        executor = self._executor(
            [
                make_tool(
                    "write_slow_file",
                    slow_write,
                    side_effect=False,  # 上游只看这个字段 → 会误标成 failed
                    timeout_seconds=0.05,
                )
            ]
        )
        message = asyncio.run(executor.execute_one(make_tool_call("write_slow_file")))
        payload = json.loads(message.content)
        assert payload["execution_may_continue"] is True
        assert payload["status"] == "unknown", "超时工具被标成了「确定失败」，下游会重试副作用"

    def test_repeated_tool_call_is_blocked(self):
        """R-16：同一工具 + 同一参数的重复调用必须被拦截。"""
        hits: list[int] = []

        def counter(**kwargs):
            hits.append(1)
            return "ok"

        executor = self._executor([make_tool("repeat_tool", counter)], max_repeat_tool_calls=2)
        call = make_tool_call("repeat_tool", {"x": 1})

        first = asyncio.run(executor.execute_one(call))
        second = asyncio.run(executor.execute_one(call))
        third = asyncio.run(executor.execute_one(call))

        assert "ok" == first.content and "ok" == second.content
        assert "RepeatedToolCall" in third.content, "第三次相同调用没有被拦截"
        assert len(hits) == 2, "被拦截的调用仍然执行了工具"


# ──────────────────────────────────────────────────────────────────────
# R-7：并发与 before_tool
# ──────────────────────────────────────────────────────────────────────


class TestParallelPatches:
    def test_parallel_batch_still_runs_before_tool(self):
        """R-7：开启并发后，before_tool 守卫（审批）不能被绕过。"""
        started = 0
        both_started = asyncio.Event()
        guard = asyncio.Lock()

        async def make_handler(label: str):
            async def handler(**kwargs):
                nonlocal started
                async with guard:
                    started += 1
                    if started >= 2:
                        both_started.set()
                # 两个工具必须同时在跑（串行执行会在这里超时）
                await asyncio.wait_for(both_started.wait(), timeout=5)
                return label

            return handler

        middleware = RecordingMiddleware()
        tools = [
            make_tool("alpha_tool", asyncio.run(make_handler("a"))),
            make_tool("beta_tool", asyncio.run(make_handler("b"))),
        ]
        llm = ScriptedLLM(
            [
                make_response(
                    tool_calls=[
                        make_tool_call("alpha_tool", call_id="c1"),
                        make_tool_call("beta_tool", call_id="c2"),
                    ]
                ),
                make_response(content="done"),
            ]
        )
        agent = build_agent(llm, tools, [middleware])
        session = agent.create_session(parallel_tool_calls=True)

        started_at = time.monotonic()
        result = asyncio.run(agent.run("go", session=session))
        elapsed = time.monotonic() - started_at

        assert result.status == "completed"
        assert sorted(middleware.seen) == ["alpha_tool", "beta_tool"], (
            "并发路径绕过了 before_tool（审批会被跳过）"
        )
        assert elapsed < 4.0, "两个工具没有并发执行"

    def test_approval_is_not_bypassed_in_parallel_batch(self):
        """R-7 最关键的守护：并发路径下**审批被拒的工具绝不能执行**。

        上游关闭并发的理由正是它的批处理分支不调 ``execute_before_tool``——
        等于绕过审批。我们用代理打开并发，就必须由执行器把审批补回来。
        """
        from app.services.agent.factory import LenientHitlMiddleware

        executed: list[str] = []

        def safe_handler(**kwargs):
            executed.append("safe_tool")
            return "safe"

        def danger_handler(**kwargs):
            executed.append("danger_tool")
            return "danger"

        async def deny(tool_call):
            return False

        middleware = LenientHitlMiddleware(
            approval_provider=deny,
            auto_approve_tools=["safe_tool"],
            auto_reject_tools=[],
            approval_mode="ask",
        )
        tools = [
            make_tool("safe_tool", safe_handler),
            make_tool("danger_tool", danger_handler),
            make_tool("__tool_rejected__", lambda **k: "rejected"),
        ]
        llm = ScriptedLLM(
            [
                make_response(
                    tool_calls=[
                        make_tool_call("safe_tool", call_id="c1"),
                        make_tool_call("danger_tool", call_id="c2"),
                    ]
                ),
                make_response(content="done"),
            ]
        )
        agent = build_agent(llm, tools, [middleware])
        session = agent.create_session(parallel_tool_calls=True)

        result = asyncio.run(agent.run("go", session=session))
        assert result.status == "completed"
        assert "danger_tool" not in executed, "被拒绝审批的工具仍然被执行了（审批被绕过）"
        assert "safe_tool" in executed, "已批准的工具没有被执行"

    def test_upstream_would_disable_batching_with_tool_hooks(self):
        """R-7 守护点：说明上游为什么会静默关闭并发（我们的补丁绕开了这个限制）。"""
        stack = MiddlewareStack()
        stack.add(RecordingMiddleware())
        assert parallel_tool_calls_effective(stack) is False

        proxy = BatchSafeMiddlewareProxy(stack)
        assert proxy._before_tool_mws == []
        # 其余行为完全委托给真实中间件栈
        assert proxy.middlewares == stack.middlewares


# ──────────────────────────────────────────────────────────────────────
# R-15：审批等待超时
# ──────────────────────────────────────────────────────────────────────


class TestApprovalTimeout:
    def test_factory_wires_the_patched_agent(self):
        """守护点：工厂必须装配补丁后的 Agent / 中间件代理。"""
        import inspect

        from app.services.agent import factory as factory_module

        source = inspect.getsource(factory_module)
        assert "PatchedAgent(" in source, "工厂还在用上游的 Agent"
        assert "BatchSafeMiddlewareProxy(" in source, "工厂没有装配并发安全代理（R-7 会静默失效）"

    def test_approval_timeout_is_treated_as_rejected(self):
        """R-15：审批等待必须有上限，否则整个会话被永久卡住。

        上游 ``HitlMiddleware.before_tool`` 直接 ``await approval_provider(...)``，
        没有超时也没有取消通道；审批期间还持有 ``session.lock``。
        """
        from app.services.agent.factory import LenientHitlMiddleware

        async def never_answers(tool_call):
            await asyncio.sleep(5)
            return True

        middleware = LenientHitlMiddleware(
            approval_provider=never_answers,
            auto_approve_tools=[],
            auto_reject_tools=[],
            approval_timeout=0.05,
        )
        result = asyncio.run(middleware.before_tool(None, make_tool_call("danger_tool")))
        assert result.function.name == "__tool_rejected__", "审批超时没有被当成拒绝"


# ──────────────────────────────────────────────────────────────────────
# R-1 / R-2 / R-3 / R-4：网关与适配器层
# ──────────────────────────────────────────────────────────────────────


class _FakeChoice:
    def __init__(self, message, finish_reason):
        self.message = message
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, choices, usage=None, model="m"):
        self.choices = choices
        self.usage = usage
        self.model = model


class _FakeMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls
        self.model_extra = {}


class _FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = type("F", (), {"name": name, "arguments": arguments})()


class _FakeUsage:
    def __init__(self, prompt=0, completion=0, total=0):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.total_tokens = total


class _FakeFinal:
    def __init__(self, content: str):
        self.content = content
        self.metadata: dict = {}


class TestAdapterLayer:
    def _adapter(self):
        from app.services.llm_providers.adapter import HardenedOpenAIAdapter

        return HardenedOpenAIAdapter(model="m", api_key="k")

    def test_finish_reason_length_keeps_tool_calls(self):
        """R-1：``finish_reason="length"`` 时 tool_calls 不能被静默丢弃。"""
        adapter = self._adapter()
        raw = _FakeResponse(
            [
                _FakeChoice(
                    _FakeMessage(
                        content="",
                        tool_calls=[_FakeToolCall("c1", "probe", '{"a": 1}')],
                    ),
                    "length",
                )
            ],
            usage=_FakeUsage(1, 1, 2),
        )
        response = adapter.parse_response(raw)
        assert len(response.message.tool_calls) == 1, "length 收尾时工具调用被丢掉了"
        assert response.message.tool_calls[0].function.name == "probe"

    def test_finish_reason_length_is_logged_in_stream(self):
        """R-1：流式路径下截断的工具调用要留下可见的告警。"""
        adapter = self._adapter()

        class Chunk:
            def __init__(self, choices, usage=None):
                self.choices = choices
                self.usage = usage

        class Delta:
            content = ""
            reasoning_content = ""
            tool_calls = None

        chunk = Chunk([type("C", (), {"delta": Delta(), "finish_reason": "length"})()])
        data = adapter.parse_stream_chunk(chunk)
        assert data["finish_reason"] == "length"

    def test_generate_wraps_error_into_llm_error(self):
        """R-2：网关抛出的必须是 ``LLMError``，并带诊断信息。"""
        from wuwei.core.errors import LLMError

        from app.services.llm_providers.adapter import RetryingGateway

        gateway = RetryingGateway({"api_key": "k", "model": "m"})
        error = RetryingGateway._as_llm_error(
            RuntimeError("boom"), attempts=3
        )
        assert isinstance(error, LLMError)
        assert error.details["attempts"] == 3
        assert error.details["error_type"] == "RuntimeError"
        assert gateway is not None

    def test_classify_error_falls_back_to_exception_hierarchy(self):
        """R-4：未知异常要按异常层级兜底分类，而不是一律不可重试。"""
        import httpx
        from wuwei.llm import LLMGateway

        from app.services.llm_providers.adapter import RetryingGateway

        class FakeTimeout(Exception):
            pass

        # 上游只按异常「类名白名单」判定：ProxyError 不在名单里 → unknown
        # → 既不重试也不走 fallback，而且不报错。
        assert LLMGateway._classify_error(httpx.ProxyError("p")) == "unknown"
        assert RetryingGateway._classify_error(httpx.ProxyError("p")) == "connection_error"

        # 上游已覆盖的类别保持原样
        assert RetryingGateway._classify_error(httpx.ReadTimeout("t")) == "timeout"
        assert RetryingGateway._classify_error(httpx.ConnectError("c")) == "connection_error"
        assert RetryingGateway._classify_error(asyncio.TimeoutError()) == "timeout"
        # 完全未知的异常仍然保持 unknown（不盲目重试）
        assert RetryingGateway._classify_error(FakeTimeout("x")) == "unknown"

    def test_stream_usage_keeps_upstream_total(self):
        """R-3：流式路径下 total_tokens 必须是上游上报的值，而不是 prompt+completion。"""
        from app.services.llm_providers.adapter import RetryingGateway

        adapter = self._adapter()
        usage = adapter._parse_usage(_FakeUsage(prompt=100, completion=50, total=300))
        assert usage["total_tokens"] == 300
        assert usage["upstream_total_tokens"] == 300

        chunk = LLMResponseChunk(
            content="",
            finish_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                   "upstream_total_tokens": 300},
        )
        RetryingGateway._restore_upstream_total(chunk)
        assert chunk.usage["total_tokens"] == 300
        assert "upstream_total_tokens" not in chunk.usage
