"""HITL 阶段 3 验收测试（docs/design/wuwei迁移LangChain方案.md 阶段 3）。

验收口径：审批全链路（发起 → 预览/改参/代答 → 批准/拒绝 → 工具执行/跳过 →
结果回灌）+ 并发审批 + 过期审批安全 + 跨 worker 决策 + 声明式 interrupt_on
（DeepAgents InterruptOnConfig 形状）。

引擎侧策略 ``EngineApprovalPolicy`` 复用同一个 ApprovalManager（Redis
pub/sub + DB 审计 + SSE 泵不变），决策词汇表对齐 DeepAgents 四决策：
approved（含改参 = edit）/ rejected / respond（人工代答）。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.agent.langgraph_engine.tools_adapter import (
    EngineApprovalPolicy,
    InterruptOnConfig,
    RESPOND_OUTPUT_KEY,
    registry_to_langchain_tools,
)
from app.services.approval_types import ApprovalDecision
from app.services.agent.native.tool_registry import ToolRegistry


# ── 工具与假件 ────────────────────────────────────────────────────────


def _make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    executed: list[dict] = []

    @registry.tool(name="send_email", display_name="发送邮件", description="发送邮件（写操作）")
    async def send_email(to: str = "", body: str = "") -> dict:
        executed.append({"to": to, "body": body})
        return {"ok": True, "sent": True}

    registry._executed = executed  # type: ignore[attr-defined]
    return registry


def _tool_of(registry: ToolRegistry, name: str):
    return registry.get(name)


class FakeManager:
    """request_approval 形态的审批假件（返回脚本化决策）。"""

    def __init__(self, decision: ApprovalDecision | None):
        self.decision = decision
        self.requests: list = []

    async def request_approval(self, request):
        self.requests.append(request)
        return self.decision


# ── 声明式 interrupt_on（DeepAgents InterruptOnConfig 形状）──────────


@pytest.mark.asyncio
async def test_interrupt_on_declarative_config():
    """{tool: True} / {tool: InterruptOnConfig} / {tool: False} 三种声明。"""
    registry = _make_registry()
    send_email = _tool_of(registry, "send_email")

    # True → 默认决策集
    policy = EngineApprovalPolicy(approval_manager=FakeManager(None), interrupt_on={"send_email": True})
    assert policy.allowed_decisions_for("send_email") == ("approved", "rejected", "respond")

    # InterruptOnConfig → 限定决策集
    policy = EngineApprovalPolicy(
        approval_manager=FakeManager(None),
        interrupt_on={"send_email": InterruptOnConfig(allowed_decisions=("approved", "rejected"))},
    )
    assert policy.allowed_decisions_for("send_email") == ("approved", "rejected")

    # False → 显式放行（即使 manager 在）
    policy = EngineApprovalPolicy(
        approval_manager=FakeManager(ApprovalDecision(status="rejected")),
        interrupt_on={"send_email": False},
    )
    outcome = await policy.before_execute(send_email, {"to": "a@b.c"})
    assert outcome.rejected is False and outcome.responded is False


@pytest.mark.asyncio
async def test_interrupt_on_payload_carries_allowed_decisions():
    """审批请求 payload 携带声明式决策集（前端据此渲染可选项）。"""
    registry = _make_registry()
    send_email = _tool_of(registry, "send_email")
    manager = FakeManager(ApprovalDecision(status="approved"))
    policy = EngineApprovalPolicy(
        approval_manager=manager,
        interrupt_on={"send_email": InterruptOnConfig(allowed_decisions=("approved", "rejected"))},
    )
    await policy.before_execute(send_email, {"to": "a@b.c"})
    assert manager.requests[0].payload["allowed_decisions"] == ["approved", "rejected"]


# ── respond（人工代答）────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_respond_decision_skips_execution_and_returns_answer():
    """respond 决策：工具不执行，用户答案作为工具结果回灌（DeepAgents 四决策）。"""
    registry = _make_registry()
    send_email = _tool_of(registry, "send_email")
    manager = FakeManager(ApprovalDecision(status="respond", response="不必发了，我已经邮件通知过了"))
    policy = EngineApprovalPolicy(
        approval_manager=manager,
        interrupt_on={"send_email": InterruptOnConfig()},
        approval_mode="ask",
    )
    outcome = await policy.before_execute(send_email, {"to": "a@b.c"})
    assert outcome.responded is True
    assert "邮件通知" in outcome.response
    assert registry._executed == []  # type: ignore[attr-defined] —— 工具确实没执行

    # 走 StructuredTool 全链：结果形态回灌
    lc_tools = registry_to_langchain_tools(registry, policy)
    lc = next(t for t in lc_tools if t.name == "send_email")
    output = json.loads(await lc.coroutine(to="a@b.c", body="x"))
    assert output[RESPOND_OUTPUT_KEY] == "不必发了，我已经邮件通知过了"
    assert output["tool"] == "send_email"


@pytest.mark.asyncio
async def test_respond_empty_answer_falls_back_to_placeholder():
    manager = FakeManager(ApprovalDecision(status="respond", response="   "))
    policy = EngineApprovalPolicy(approval_manager=manager, interrupt_on={"t": InterruptOnConfig()})
    outcome = await policy.before_execute(SimpleNamespace(name="t"), {})
    assert outcome.responded is True
    assert outcome.response == "（用户未提供答案）"


# ── 过期审批（超时安全）───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_expiry_is_treated_as_rejection():
    """审批等待超时 → 按拒绝处理（R-15 语义），绝不把会话永久卡住。"""

    class SlowManager:
        async def request_approval(self, request):
            await asyncio.sleep(5)  # 比策略超时更长
            return ApprovalDecision(status="approved")

    registry = _make_registry()
    policy = EngineApprovalPolicy(
        approval_manager=SlowManager(),
        interrupt_on={"send_email": InterruptOnConfig()},
        approval_timeout=0.2,
        approval_mode="ask",
    )
    outcome = await policy.before_execute(_tool_of(registry, "send_email"), {"to": "x"})
    assert outcome.rejected is True
    assert "超时" in outcome.reject_reason
    assert registry._executed == []  # type: ignore[attr-defined]


# ── 并发审批（两个工具调用互不串单）───────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_approvals_do_not_cross():
    """两个并发审批各自等待各自的决策，先到者不阻塞/不误配后到者。"""

    class QueueManager:
        """手动放行式假件：决策按 approval_id 精确投递。"""

        def __init__(self):
            self.pending: dict[str, asyncio.Queue] = {}
            self.requests: list = []

        async def request_approval(self, request):
            self.requests.append(request)
            q: asyncio.Queue = asyncio.Queue()
            self.pending[request.id] = q
            decision = await q.get()
            return decision

        def resolve(self, request_index: int, decision: ApprovalDecision):
            req = self.requests[request_index]
            self.pending[req.id].put_nowait(decision)

    registry = _make_registry()
    manager = QueueManager()
    policy = EngineApprovalPolicy(
        approval_manager=manager,
        interrupt_on={"send_email": InterruptOnConfig()},
        approval_mode="ask",
    )
    send_email = _tool_of(registry, "send_email")

    async def run_call(args: dict) -> dict:
        outcome = await policy.before_execute(send_email, args)
        if outcome.responded:
            return {"responded": True, "answer": outcome.response}
        if outcome.rejected:
            return {"rejected": True, "reason": outcome.reject_reason}
        return {"executed": True, "args": outcome.arguments}

    task_a = asyncio.create_task(run_call({"to": "a@x"}))
    task_b = asyncio.create_task(run_call({"to": "b@x"}))
    await asyncio.sleep(0.05)
    assert len(manager.requests) == 2

    # 先决策 B（拒绝），再决策 A（批准带改参）——乱序完成互不串单
    manager.resolve(1, ApprovalDecision(status="rejected"))
    manager.resolve(0, ApprovalDecision(status="approved", modified_arguments={"to": "c@x", "body": "改"}))
    result_b, result_a = await asyncio.gather(task_b, task_a)
    assert result_b == {"rejected": True, "reason": "用户拒绝了此工具的执行"}
    assert result_a == {"executed": True, "args": {"to": "c@x", "body": "改"}}
    # 工具执行发生在 StructuredTool._arun 层（策略层只产出决策结果）；
    # 改参执行的全链验证见 test_langgraph_engine::test_approved_with_modified_arguments


# ── 跨 worker 决策（Redis pub/sub 转发）──────────────────────────────


@pytest.mark.asyncio
async def test_cross_worker_decision_via_redis_pubsub(monkeypatch):
    """worker A 等待审批，worker B 决策 —— 经 Redis decision 频道转发。"""
    import fakeredis

    server = fakeredis.FakeServer()
    def shared():
        return fakeredis.FakeAsyncRedis(server=server, decode_responses=True)

    import app.services.approval_manager as am

    monkeypatch.setattr(am, "get_redis", shared)
    monkeypatch.setattr(am, "is_redis_memory", lambda: False)

    manager_a = am.ApprovalManager(timeout_seconds=5)
    manager_b = am.ApprovalManager(timeout_seconds=5)

    from app.services.approval_types import ApprovalRequest

    request = ApprovalRequest(
        id="cross-worker-001",
        session_id="sess-lg",
        action_type="tool_call",
        payload={"tool_name": "send_email", "arguments": {"to": "a@b.c"}},
    )

    wait_task = asyncio.create_task(manager_a.request_approval(request))
    await asyncio.sleep(0.3)  # 让 A 的 decision-channel listener 挂上

    # worker B：决策 respond（人工代答）→ 经 pub/sub 转发回 A
    await manager_b.decide("cross-worker-001", status="respond", response="直接回复：已线下处理")
    decision = await asyncio.wait_for(wait_task, timeout=5)
    assert decision.status == "respond"
    assert decision.response == "直接回复：已线下处理"
