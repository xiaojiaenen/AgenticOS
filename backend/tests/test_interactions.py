"""统一交互协调器（InteractionBroker）的直接单测。

覆盖：请求/解决往返、超时语义、cancel_session（流结束清理）、
按会话 resolve（旧 session-keyed 端点契约）、归属登记、未知 kind 拒绝。
工具审批（ApprovalManager）不经此模块，另有 test_approval_manager / 端点级测试覆盖。
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.interactions import (
    InteractionBroker,
    InteractionKind,
    InteractionTimeout,
    KIND_EVENTS,
)


@pytest.fixture()
def broker():
    return InteractionBroker(default_timeout_seconds=300)


def _wait_for_registered(broker: InteractionBroker, session_id: str, count: int = 1):
    async def _poll():
        for _ in range(200):
            if broker.pending_count(session_id) >= count:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"interaction for {session_id} never registered")

    return _poll


class TestRequestResolveRoundtrip:
    @pytest.mark.anyio
    async def test_user_input_roundtrip(self, broker):
        queue = broker.subscribe("s-1")
        task = asyncio.create_task(
            broker.request("s-1", InteractionKind.USER_INPUT, {"fields": ["a"]})
        )
        await _wait_for_registered(broker, "s-1")()
        event = await asyncio.wait_for(queue.get(), timeout=2)
        # tagged event：kind + interaction_id 注入，原有 payload 保留
        assert event["kind"] == InteractionKind.USER_INPUT
        assert event["interaction_id"]
        assert event["fields"] == ["a"]
        assert await broker.resolve(event["interaction_id"], {"a": "1"}) is True
        assert await asyncio.wait_for(task, timeout=2) == {"a": "1"}
        assert broker.pending_count("s-1") == 0

    @pytest.mark.anyio
    async def test_api_approval_decision_shape(self, broker):
        broker.subscribe("s-2")
        task = asyncio.create_task(
            broker.request(
                "s-2", InteractionKind.API_APPROVAL, {"system_name": "Sys", "method": "GET"}
            )
        )
        await _wait_for_registered(broker, "s-2")()
        interaction_id = next(iter(broker._pending))
        assert await broker.resolve(interaction_id, {"approved": True, "allow_all": True}) is True
        assert await asyncio.wait_for(task, timeout=2) == {"approved": True, "allow_all": True}

    @pytest.mark.anyio
    async def test_kind_maps_to_sse_event_name(self):
        assert KIND_EVENTS[InteractionKind.USER_INPUT] == "user_input_required"
        assert KIND_EVENTS[InteractionKind.API_APPROVAL] == "api_approval_required"
        assert KIND_EVENTS[InteractionKind.DECISION] == "user_decision"


class TestTimeout:
    @pytest.mark.anyio
    async def test_request_raises_interaction_timeout(self):
        broker = InteractionBroker(default_timeout_seconds=0.05)
        broker.subscribe("s-t1")
        with pytest.raises(InteractionTimeout):
            await broker.request("s-t1", InteractionKind.DECISION, {"question": "q"})
        # 超时后登记已清
        assert broker.pending_count("s-t1") == 0

    @pytest.mark.anyio
    async def test_cancel_session_unblocks_waiter_with_timeout_semantics(self, broker):
        broker.subscribe("s-t2")
        task = asyncio.create_task(
            broker.request("s-t2", InteractionKind.USER_INPUT, {"fields": []})
        )
        await _wait_for_registered(broker, "s-t2")()
        broker.cancel_session("s-t2")
        with pytest.raises(InteractionTimeout):
            await asyncio.wait_for(task, timeout=2)


class TestResolveBySession:
    @pytest.mark.anyio
    async def test_resolve_by_session_hits_earliest_pending(self, broker):
        """旧 session-keyed 端点契约：resolve 会话上最早挂起的同类交互。"""
        broker.subscribe("s-3")
        first = asyncio.create_task(
            broker.request("s-3", InteractionKind.API_APPROVAL, {"system_name": "A"})
        )
        second = asyncio.create_task(
            broker.request("s-3", InteractionKind.API_APPROVAL, {"system_name": "B"})
        )
        await _wait_for_registered(broker, "s-3", count=2)()
        assert broker.pending_count("s-3") == 2

        assert await broker.resolve_by_session("s-3", InteractionKind.API_APPROVAL, {"approved": True}) is True
        assert await asyncio.wait_for(first, timeout=2) == {"approved": True}
        assert broker.pending_count("s-3") == 1

        assert await broker.resolve_by_session("s-3", InteractionKind.API_APPROVAL, {"approved": False}) is True
        assert await asyncio.wait_for(second, timeout=2) == {"approved": False}

    @pytest.mark.anyio
    async def test_resolve_by_session_kind_scoped(self, broker):
        """不同 kind 互不影响：user_input 的 resolve 不会命中 api_approval。"""
        broker.subscribe("s-4")
        approval = asyncio.create_task(
            broker.request("s-4", InteractionKind.API_APPROVAL, {"system_name": "A"})
        )
        await _wait_for_registered(broker, "s-4")()
        assert (
            await broker.resolve_by_session("s-4", InteractionKind.USER_INPUT, {"a": 1})
            is False
        )
        # 挂起交互未被误伤
        assert broker.pending_count("s-4") == 1
        interaction_id = next(iter(broker._pending))
        await broker.resolve(interaction_id, {"approved": True})
        assert await asyncio.wait_for(approval, timeout=2) == {"approved": True}

    @pytest.mark.anyio
    async def test_resolve_by_session_without_pending_is_false(self, broker):
        assert (
            await broker.resolve_by_session("s-none", InteractionKind.USER_INPUT, {"a": 1})
            is False
        )


class TestOwnership:
    @pytest.mark.anyio
    async def test_pending_session_peek(self, broker):
        broker.subscribe("s-5")
        task = asyncio.create_task(
            broker.request("s-5", InteractionKind.DECISION, {"question": "q"})
        )
        await _wait_for_registered(broker, "s-5")()
        interaction_id = next(iter(broker._pending))
        assert broker.pending_session(interaction_id) == "s-5"
        assert broker.pending_session("unknown") is None
        await broker.resolve(interaction_id, {"answer": "x"})
        await asyncio.wait_for(task, timeout=2)
        # resolve 后归属清空
        assert broker.pending_session(interaction_id) is None


class TestUnknownKind:
    @pytest.mark.anyio
    async def test_request_rejects_unknown_kind(self, broker):
        with pytest.raises(ValueError, match="unknown interaction kind"):
            await broker.request("s-6", "tool_approval", {})  # 工具审批不走 broker


class TestSubscribeIdempotent:
    @pytest.mark.anyio
    async def test_repeated_subscribe_returns_same_queue(self, broker):
        """多个入口对同一会话订阅必须拿到同一队列（事件不得因覆盖而丢失）。"""
        q1 = broker.subscribe("s-7")
        q2 = broker.subscribe("s-7")
        assert q1 is q2

    @pytest.mark.anyio
    async def test_unsubscribe_then_subscribe_gets_fresh_queue(self, broker):
        q1 = broker.subscribe("s-8")
        broker.unsubscribe("s-8")
        q2 = broker.subscribe("s-8")
        assert q1 is not q2
