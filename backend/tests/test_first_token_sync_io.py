"""首 token 前的同步 IO 移出 asyncio 事件循环的回归测试。

每项改动都验证：同步函数确实在**工作线程**里被调用（且不是事件循环线程），
事件循环本身不被读盘 / 读 Redis / 配额查询这类同步 IO 阻塞。
"""

from __future__ import annotations

import asyncio
import threading
import types

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.api.v1.endpoints.agent import stream_agent
from app.core.config import get_settings
from app.main import app
from app.schemas.agent import AgentStreamRequest
from app.services.agent.orchestrator import StreamOrchestrator
from app.services.agent_service import get_agent_service
from app.services.llm_gate import LLMConcurrencyGate


def _run(coro):
    """在独立事件循环里跑协程（避免依赖 pytest-asyncio 的 asyncio_mode）。"""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. orchestrator.stream_chat: check_daily_quota + _get_agent 走 to_thread
# ---------------------------------------------------------------------------


def test_stream_chat_runs_quota_and_agent_build_in_worker_thread(monkeypatch):
    from app.services import quota_service

    loop_thread = threading.get_ident()
    quota_threads: list[int] = []
    agent_threads: list[int] = []

    def fake_quota(user_id, *, role="user"):
        quota_threads.append(threading.get_ident())
        return {"allowed": True}

    monkeypatch.setattr(quota_service, "check_daily_quota", fake_quota)

    # 用 __new__ 造最小桩，把 stream_chat 前段（到 agent 构建为止）跑完即抛哨兵，
    # 避免真的进入 LLM 流。缺什么属性就补什么 —— 只关心配额 / agent 两步的调用线程。
    class _Sentinel(Exception):
        pass

    orch = StreamOrchestrator.__new__(StreamOrchestrator)
    orch.storage = types.SimpleNamespace(describe=lambda _sid: None)

    async def fake_resolve(request, user):
        return types.SimpleNamespace(
            profile_id=1, slug="test", response_mode="general", system_prompt="",
            skills=(), builtin_tools=(), approval_tools=frozenset(), signature=(),
        )

    orch._resolve_runtime_profile = fake_resolve

    def fake_get_agent(profile):
        agent_threads.append(threading.get_ident())
        raise _Sentinel()

    # _get_agent 定义在 AgentFactory mixin 上，__new__ 出来的对象没有实例属性，
    # 用 raising=False 在实例上挂桩。
    monkeypatch.setattr(orch, "_get_agent", fake_get_agent, raising=False)

    async def scenario():
        try:
            async for _ in orch.stream_chat(
                AgentStreamRequest(message="hi", response_mode="general"),
                types.SimpleNamespace(id=42, role="user"),
            ):
                pass
        except _Sentinel:
            pass

    _run(scenario())

    assert quota_threads and agent_threads
    assert all(t != loop_thread for t in quota_threads), "check_daily_quota 不应在事件循环线程执行"
    assert all(t != loop_thread for t in agent_threads), "_get_agent 不应在事件循环线程执行"


# ---------------------------------------------------------------------------
# 2. /agent/stream 端点: check_window_quota 走 to_thread
# ---------------------------------------------------------------------------


def test_stream_endpoint_runs_window_quota_in_worker_thread(monkeypatch):
    from app.api.v1.endpoints import agent as endpoint_mod

    loop_thread = threading.get_ident()
    quota_threads: list[int] = []

    def fake_window_quota(*args, **kwargs):
        quota_threads.append(threading.get_ident())
        return True, 0

    monkeypatch.setattr(endpoint_mod, "check_window_quota", fake_window_quota)

    class _Settings:
        agent_stream_rate_limit = 10
        agent_stream_rate_window_seconds = 60

    monkeypatch.setattr(endpoint_mod, "get_settings", lambda: _Settings())

    user = types.SimpleNamespace(id=7, role="user")

    class _FakeService:
        def ensure_ready(self):
            pass

        async def ensure_session_access(self, request, current_user):
            pass

        async def stream_chat(self, request, current_user):
            if False:
                yield  # pragma: no cover - 保持异步生成器

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_agent_service] = lambda: _FakeService()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agent/stream",
                json={"message": "hi"},
            )
        assert response.status_code == 200
        assert quota_threads, "check_window_quota 应被调用"
        assert all(t != loop_thread for t in quota_threads), (
            "check_window_quota 不应在事件循环线程执行"
        )
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 3. _build_user_input: 图片读盘 + base64 走 to_thread
# ---------------------------------------------------------------------------


def test_build_user_input_reads_image_in_worker_thread(monkeypatch, tmp_path):
    import base64

    from app.schemas.agent import FileAttachment
    from app.services.agent import orchestrator as orch_mod

    png = tmp_path / "a.png"
    png.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
        "h6FO1AAAAABJRU5ErkJggg=="
    ))
    req = AgentStreamRequest(
        message="看图",
        response_mode="general",
        files=[FileAttachment(filename="a.png", file_path=str(png))],
    )
    orch = StreamOrchestrator.__new__(StreamOrchestrator)
    loop_thread = threading.get_ident()

    _orig = orch_mod._read_image_data_url
    threads: list[int] = []

    def recording(path, ext):
        threads.append(threading.get_ident())
        return _orig(path, ext)

    monkeypatch.setattr(orch_mod, "_read_image_data_url", recording)

    async def scenario():
        return await orch._build_user_input("看图", req)

    msg = _run(scenario())

    assert threads, "图片应被读取"
    assert all(t != loop_thread for t in threads), "图片读盘/编码不应在事件循环线程执行"
    assert msg.content_parts and msg.content_parts[0].url.startswith("data:image/png;base64,")


# ---------------------------------------------------------------------------
# 4. llm_gate._release_global: Redis eval 走 to_thread
# ---------------------------------------------------------------------------


def test_llm_gate_release_eval_runs_in_worker_thread(monkeypatch):
    from app.services import llm_gate as gate_mod

    loop_thread = threading.get_ident()
    eval_threads: list[int] = []

    class _Client:
        def eval(self, script, numkeys, *keys):
            eval_threads.append(threading.get_ident())
            return 1

    monkeypatch.setattr(gate_mod, "is_redis_memory", lambda: False)
    monkeypatch.setattr(gate_mod, "get_redis_sync", lambda: _Client())

    gate = LLMConcurrencyGate()

    async def scenario():
        await gate._release_global("tok")

    _run(scenario())

    assert eval_threads, "client.eval 应被调用"
    assert all(t != loop_thread for t in eval_threads), "Redis eval 不应在事件循环线程执行"


def test_llm_gate_slot_finally_releases_via_thread(monkeypatch):
    """slot() 正常退出与取消场景都应通过 to_thread 释放全局槽位。"""
    from app.services import llm_gate as gate_mod

    loop_thread = threading.get_ident()
    eval_threads: list[int] = []

    class _Client:
        def incr(self, key):
            return 1

        def expire(self, key, seconds):
            return True

        def set(self, key, value, ex=None):
            return True

        def decr(self, key):
            return 0

        def eval(self, script, numkeys, *keys):
            eval_threads.append(threading.get_ident())
            return 1

    monkeypatch.setattr(gate_mod, "is_redis_memory", lambda: False)
    monkeypatch.setattr(gate_mod, "get_redis_sync", lambda: _Client())

    class _Settings:
        llm_gate_enabled = True
        llm_gate_max_concurrency = 2
        llm_gate_lease_seconds = 60
        llm_gate_wait_seconds = 1.0

    gate = LLMConcurrencyGate(_Settings())

    async def scenario():
        gate.configure()
        async with gate.slot():
            pass
        assert eval_threads, "slot 退出时应释放全局槽位"
        assert all(t != loop_thread for t in eval_threads)

    _run(scenario())
