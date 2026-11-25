"""LangGraph 新引擎契约测试（docs/design/wuwei迁移LangChain方案.md 阶段 1-2 验收）。

绞杀者模式的验收口径：新引擎吐出的 AgentEvent 流必须能被现有 orchestrator
的 SSE mapper **零改动**消费，且会话上下文同步（持久化契约）不回归。

- 直答场景：run_start → text_delta… → done（usage/latency/llm_calls 契约）；
- 工具场景：tool_start（display_name/requires_approval 元数据）→ tool_end
  → text_delta → done，会话上下文出现 AIMessage(tool_calls) + ToolMessage；
- 审批场景：非只读工具 + 空放行名单 → EngineApprovalPolicy 走
  ApprovalManager；拒绝 → __tool_rejected__ 输出（LLM 可见拒绝消息）；
- SSE 兼容：全部事件过 StreamOrchestrator._map_agent_event（真实 mapper）。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from app.services.agent.native.types import LLMResponseChunk
from app.services.agent.native.tool_registry import ToolRegistry

from app.services.agent.langgraph_engine import LangGraphAgent
from app.services.agent.langgraph_engine.tools_adapter import EngineApprovalPolicy, registry_to_langchain_tools


# ── 测试替身 ──────────────────────────────────────────────────────────


def _chunk(content="", reasoning=None, tool_calls_delta=None, tool_calls_complete=None, finish_reason=None, usage=None):
    return LLMResponseChunk(
        content=content,
        reasoning_content=reasoning,
        tool_calls_delta=tool_calls_delta or [],
        tool_calls_complete=tool_calls_complete or [],
        finish_reason=finish_reason,
        raw_finish_reason=finish_reason,
        usage=usage,
    )


class FakeGateway:
    """脚本化的 LLMGateway 替身：generate(messages, tools, stream) 同形。"""

    def __init__(self, script: list[list[Any]]):
        self.script = script
        self.calls: list[dict[str, Any]] = []

    async def generate(self, messages, tools=None, stream=False, **kwargs):
        self.calls.append({"messages": list(messages), "tools": tools})
        chunks = self.script.pop(0) if self.script else [_chunk("done", finish_reason="stop")]

        async def _stream():
            for chunk in chunks:
                await asyncio.sleep(0)
                yield chunk

        if stream:
            return _stream()

        # 非流式：聚合成单个响应对象（LangGraph 模型节点不走这条路）
        content = "".join(c.content for c in chunks if c.content)
        tool_calls_complete = []
        for c in chunks:
            tool_calls_complete.extend(c.tool_calls_complete)
        return SimpleNamespace(content=content, tool_calls=tool_calls_complete, usage=None, finish_reason="stop")


def _make_registry() -> ToolRegistry:
    registry = ToolRegistry()

    @registry.tool(name="calculate", display_name="数学计算", description="安全计算数学表达式")
    def calculate(expression: str) -> dict:
        return {"ok": True, "expression": expression, "result": 4}

    @registry.tool(name="time", display_name="时间", description="获取当前时间")
    def time_now() -> dict:
        return {"ok": True, "now": "2026-01-01"}

    @registry.tool(name="send_email", display_name="发送邮件", description="发送邮件（写操作）")
    async def send_email(to: str = "", body: str = "") -> dict:
        return {"ok": True, "sent": True}

    return registry


def _make_agent(script, *, auto_approve=None, approval_mode="auto", approval_manager=None) -> LangGraphAgent:
    registry = _make_registry()
    policy = EngineApprovalPolicy(
        approval_manager=approval_manager,
        auto_approve_tools=auto_approve if auto_approve is not None else {"calculate", "send_email"},
        approval_mode=approval_mode,
        approval_timeout=2.0,
    )
    return LangGraphAgent(
        llm=FakeGateway(script),
        tools=registry,
        default_system_prompt="你是测试助手",
        default_max_steps=10,
        approval_policy=policy,
        model_name="test-model",
    )


async def _collect(agent: LangGraphAgent, message: str):
    session = agent.create_session(system_prompt="你是测试助手")
    events = []
    async for event in agent.stream_events(message, session=session):
        events.append(event)
    return session, events


def _by_type(events, event_type):
    return [e for e in events if e.type == event_type]


# ── 场景 1：直答 ──────────────────────────────────────────────────────


def test_direct_reply_stream_contract():
    script = [
        [
            _chunk("你好", finish_reason=None),
            _chunk("，我是", finish_reason=None),
            _chunk("新引擎", finish_reason="stop", usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}),
        ]
    ]
    agent = _make_agent(script)
    session, events = asyncio.run(_collect(agent, "打个招呼"))

    assert events[0].type == "run_start"
    deltas = _by_type(events, "text_delta")
    assert "".join(d.data["content"] for d in deltas) == "你好，我是新引擎"
    assert all(e.session_id == session.session_id for e in events)
    done = _by_type(events, "done")
    assert len(done) == 1
    assert done[0].data["reason"] == "stop"
    assert done[0].data["usage"]["total_tokens"] == 15
    assert done[0].data["llm_calls"] >= 1
    assert "latency_ms" in done[0].data
    # 会话上下文同步（持久化契约）：[system, user, assistant]
    messages = session.context._messages
    assert messages[0].role == "system"  # wuwei 会话上下文首条是 system
    assert messages[1].role == "user"    # wuwei HumanMessage 的 role 词表
    assert messages[-1].role == "assistant"
    assert messages[-1].content == "你好，我是新引擎"
    # 用量写回会话（orchestrator session_payload 契约）
    assert session.last_usage["total_tokens"] == 15


def test_system_prompt_passed_to_gateway():
    script = [[_chunk("ok", finish_reason="stop")]]
    agent = _make_agent(script)
    asyncio.run(_collect(agent, "hi"))
    gateway = agent.llm
    first_call_messages = gateway.calls[0]["messages"]
    assert first_call_messages[0].role == "system"
    assert first_call_messages[0].content == "你是测试助手"


# ── 场景 2：工具调用 ──────────────────────────────────────────────────


def _delta(call_id="call-1", name="calculate", args=None):
    """ToolCallDelta 的约定 dict 形态（gateway 真实输出）。"""
    payload = {"expression": "2+2"} if args is None else args
    return {"index": 0, "id": call_id, "name": name, "arguments": json.dumps(payload)}


def _wuwei_tool_call(call_id="call-1", name="calculate", args=None):
    from app.services.agent.native.types import ToolCall, FunctionCall

    return ToolCall(
        id=call_id,
        function=FunctionCall(name=name, arguments={"expression": "2+2"} if args is None else args),
    )


def test_tool_call_roundtrip():
    script = [
        [
            _chunk(tool_calls_delta=[_delta()], finish_reason="tool_calls"),
            _chunk(tool_calls_complete=[_wuwei_tool_call()], finish_reason="tool_calls"),
        ],
        [_chunk("计算结果是 4", finish_reason="stop")],
    ]
    agent = _make_agent(script)
    session, events = asyncio.run(_collect(agent, "帮我算 2+2"))

    starts = _by_type(events, "tool_start")
    assert len(starts) == 1
    assert starts[0].data["tool_name"] == "calculate"
    assert starts[0].data["tool_call_id"] == "call-1"
    assert starts[0].data["display_name"] == "数学计算"
    assert starts[0].data["args"] == {"expression": "2+2"}

    ends = _by_type(events, "tool_end")
    assert len(ends) == 1
    assert ends[0].data["tool_call_id"] == "call-1"
    payload = json.loads(ends[0].data["output"])
    assert payload["ok"] is True and payload["result"] == 4

    # 第二轮模型调用拿到了工具结果
    second_call = agent.llm.calls[1]["messages"]
    assert any(getattr(m, "role", "") == "tool" for m in second_call)

    # 会话上下文：system + user + assistant(tool_calls) + tool + assistant(text)
    roles = [m.role for m in session.context._messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
    assert session.context._messages[2].tool_calls[0].function.name == "calculate"


def test_tool_error_reported_via_tool_error_event():
    registry = ToolRegistry()

    @registry.tool(name="boom", display_name="爆炸工具", description="总是失败")
    def boom() -> dict:
        return {"ok": False, "error": {"type": "runtime", "message": "炸了"}}

    policy = EngineApprovalPolicy(auto_approve_tools={"boom"}, approval_mode="auto")
    script = [
        [
            _chunk(tool_calls_delta=[_delta(name="boom", args={})], finish_reason="tool_calls"),
            _chunk(tool_calls_complete=[_wuwei_tool_call(name="boom", args={})], finish_reason="tool_calls"),
        ],
        [_chunk("知道了", finish_reason="stop")],
    ]
    agent = LangGraphAgent(
        llm=FakeGateway(script), tools=registry, default_system_prompt="t", default_max_steps=5, approval_policy=policy
    )
    _, events = asyncio.run(_collect(agent, "boom"))
    errors = _by_type(events, "tool_error")
    assert len(errors) == 1
    assert "炸了" in errors[0].data["message"]


# ── 场景 3：审批（LenientHitl 语义移植）───────────────────────────────


def _rejecting_approval_manager(decision_status="rejected", modified=None, response=None):
    """阶段 3 形态的审批假件：实现 ``request_approval(ApprovalRequest)``，
    并记录请求以校验 allowed_decisions 随事件下发。"""
    from app.services.approval_types import ApprovalDecision

    class FakeManager:
        def __init__(self):
            self.requests = []

        async def request_approval(self, request):
            self.requests.append(request)
            return ApprovalDecision(
                status=decision_status, modified_arguments=modified, response=response
            )

    return FakeManager()


def test_rejected_tool_becomes_rejection_message():
    """拒绝 → __tool_rejected__ 输出，LLM 能看到拒绝原因（宽松 HITL 语义）。"""
    manager = _rejecting_approval_manager("rejected")
    script = [
        [
            _chunk(tool_calls_delta=[_delta(name="send_email", args={"to": "x"})], finish_reason="tool_calls"),
            _chunk(tool_calls_complete=[_wuwei_tool_call(name="send_email", args={"to": "x"})], finish_reason="tool_calls"),
        ],
        [_chunk("好的，不发了", finish_reason="stop")],
    ]
    # send_email 不在放行名单 → 走审批；auto 档下它不是只读工具，必拦
    agent = _make_agent(script, auto_approve={"calculate"}, approval_manager=manager)
    _, events = asyncio.run(_collect(agent, "发邮件"))

    assert len(manager.requests) == 1
    assert manager.requests[0].payload["tool_name"] == "send_email"
    ends = _by_type(events, "tool_end")
    payload = json.loads(ends[0].data["output"])
    assert payload["rejected"] is True
    assert payload["original_tool"] == "send_email"


def test_approved_with_modified_arguments():
    """批准带改参 → 用改后参数执行（邮件预览改正文场景）。"""
    manager = _rejecting_approval_manager("approved", modified={"to": "y@z.com", "body": "改过"})
    captured = {}

    registry = ToolRegistry()

    @registry.tool(name="send_email", display_name="发送邮件", description="发送邮件")
    async def send_email(to: str = "", body: str = "") -> dict:
        captured.update({"to": to, "body": body})
        return {"ok": True}

    script = [
        [
            _chunk(tool_calls_delta=[_delta(name="send_email", args={"to": "x"})], finish_reason="tool_calls"),
            _chunk(tool_calls_complete=[_wuwei_tool_call(name="send_email", args={"to": "x"})], finish_reason="tool_calls"),
        ],
        [_chunk("已发送", finish_reason="stop")],
    ]
    agent = LangGraphAgent(
        llm=FakeGateway(script),
        tools=registry,
        default_system_prompt="t",
        default_max_steps=5,
        approval_policy=EngineApprovalPolicy(approval_manager=manager, auto_approve_tools=set(), approval_mode="ask"),
    )
    _, events = asyncio.run(_collect(agent, "发邮件"))
    assert captured == {"to": "y@z.com", "body": "改过"}


def test_read_only_tool_auto_approved_in_auto_mode():
    """auto 档：只读工具不进审批（与 LenientHitlMiddleware 行为一致）。"""
    manager = _rejecting_approval_manager("rejected")
    script = [[_chunk(tool_calls_delta=[_delta(name="time", args={})], finish_reason="tool_calls"),
               _chunk(tool_calls_complete=[_wuwei_tool_call(name="time", args={})], finish_reason="tool_calls")],
              [_chunk("done", finish_reason="stop")]]
    agent = _make_agent(script, auto_approve=set(), approval_mode="auto", approval_manager=manager)
    _, events = asyncio.run(_collect(agent, "现在几点"))
    assert manager.requests == []  # time 在只读白名单，auto 档直接放行
    assert len(_by_type(events, "tool_end")) == 1


# ── SSE mapper 兼容（真实 orchestrator mapper 消费新引擎事件）─────────


def test_events_pass_through_real_sse_mapper():
    script = [
        [
            _chunk(tool_calls_delta=[_delta()], finish_reason="tool_calls"),
            _chunk(tool_calls_complete=[_wuwei_tool_call()], finish_reason="tool_calls"),
        ],
        [_chunk("结果是 4", finish_reason="stop", usage={"input_tokens": 8, "output_tokens": 3, "total_tokens": 11})],
    ]
    agent = _make_agent(script)
    session, events = asyncio.run(_collect(agent, "算 2+2"))

    from app.services.agent.orchestrator import StreamOrchestrator

    orchestrator = StreamOrchestrator.__new__(StreamOrchestrator)
    orchestrator.settings = SimpleNamespace(agent_max_steps=10)
    # display_name 映射依赖 TOOL_CATALOG；契约测试只关心兜底链路
    orchestrator._display_name_map_cache = {}
    orchestrator._get_display_name_map = lambda: {}
    mapped = []
    for event in events:
        payload = orchestrator._map_agent_event(event, session)
        if payload is not None:
            mapped.append(payload)

    names = [p["event"] for p in mapped]
    assert "tool_calls" in names
    assert "tool_results" in names
    assert "done" in names
    tool_calls_payload = next(p for p in mapped if p["event"] == "tool_calls")
    assert tool_calls_payload["data"]["tool_calls"][0]["function"]["name"] == "数学计算"


def test_tool_metadata_alignment():
    """阶段 1 验收：工具元数据 100% 对齐（display_name/side_effect/审批位）。"""
    registry = _make_registry()
    lc_tools = registry_to_langchain_tools(registry, None)
    by_name = {t.name: t for t in lc_tools}
    assert {"calculate", "send_email", "time"} <= set(by_name)
    assert by_name["calculate"].metadata["display_name"] == "数学计算"
    # bind_tools 反向引用：gateway 收到 wuwei Tool（走原生请求构造）
    assert by_name["calculate"].metadata["wuwei_tool"].parameters.to_schema()["type"] == "object"


# ── 回归：流式累积 delta → LangChain 增量合并 ─────────────────────────


def test_streaming_cumulative_tool_deltas_merge_into_tool_calls():
    """真实 gateway 的 tool_calls_delta 是**累积快照**（每帧带全量 arguments、
    name/id 每帧重复）。LangChain 的 AIMessageChunk 合并是字符串拼接语义，
    只接受**增量**（name/id 只出现一次）。回归点：GatewayChatModel._astream
    必须做累积→增量换算，否则合并后的 AIMessage.tool_calls 为空（工具
    静默丢失，模型永远收不到工具结果）。"""

    from langchain_core.messages import AIMessageChunk, HumanMessage

    from app.services.agent.langgraph_engine.chat_model import GatewayChatModel

    # 模拟真实 gateway：4 帧，args 逐帧累积、name/id 重复
    growing = '{"expression": "999*888"}'
    frames = [growing[: i * 7] for i in range(1, 5)]
    script = [
        _chunk(tool_calls_delta=[
            {"index": 0, "id": "call-9", "name": "calculate", "arguments": frame}
        ])
        for frame in frames
    ] + [_chunk(tool_calls_complete=[_wuwei_tool_call(call_id="call-9")], finish_reason="tool_calls")]

    class _SnapGateway(FakeGateway):
        async def generate(self, messages, tools=None, stream=False, **kwargs):
            async def _stream():
                for chunk in script:
                    yield chunk
            if stream:
                return _stream()
            return SimpleNamespace(content="", tool_calls=[], usage=None, finish_reason="tool_calls")

    registry = _make_registry()
    model = GatewayChatModel(gateway=_SnapGateway(None), model_name="t")
    bound = model.bind_tools(registry_to_langchain_tools(registry, None))

    async def _run():
        acc = AIMessageChunk(content="")
        async for chunk in bound.astream([HumanMessage(content="算一下")]):
            acc = acc + chunk
        return acc

    acc = asyncio.run(_run())
    assert acc.tool_calls, "合并后的 AIMessageChunk 必须解析出 tool_calls（回归：累积 delta 拼接成垃圾 JSON 导致静默丢失）"
    call = acc.tool_calls[0]
    assert call["name"] == "calculate"
    assert call["args"] == {"expression": "999*888"}
    assert call["id"] == "call-9"
    # name 不应被逐帧拼接
    assert "calculatecalculate" not in str(acc.tool_call_chunks)
