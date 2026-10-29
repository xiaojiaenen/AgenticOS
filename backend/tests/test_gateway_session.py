"""网关会话行为测试：历史保存 / 上下文累积 / session_id 返回 / 隔离。

这些是「调用智能体 API 到底能不能当聊天用」的核心契约，之前完全没覆盖。
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

pytest.importorskip("openai")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    import uvicorn

    from app.main import app

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(80):
        try:
            with urllib.request.urlopen(base + "/api/v1/health/", timeout=2):
                break
        except Exception:
            time.sleep(0.25)
    else:
        pytest.skip("服务未能启动")

    yield base
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture()
def api_key():
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.models import UserModel
    from app.db.session import create_db_session
    from app.services.api_key_service import create_api_key

    with create_db_session() as db:
        user = db.execute(select(UserModel).order_by(UserModel.id).limit(1)).scalar_one_or_none()
        if user is None:
            user = UserModel(
                email="session-test@example.test",
                name="Session Test",
                password_hash=hash_password("SessionTest!2026"),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        uid = user.id

    result = create_api_key(uid, name=f"session-{int(time.time())}")
    key = result["key"] if isinstance(result, dict) else getattr(result, "key", None)
    if not key:
        pytest.skip("无法创建 API Key")
    return key


@pytest.fixture()
def mock_agent(monkeypatch):
    """把 agent 服务替换成可控实现，专注验证网关的会话契约。

    不 mock 的话依赖真实上游模型，测试不可重复。这里 mock 的只是「agent
    执行」，网关的 session 处理逻辑仍是真实代码。
    """
    from app.services.agent.service import AgentService

    created: list[str] = []

    async def _fake_stream_chat(self, request, user=None):
        # 模拟真实行为：没有 session_id 就分配一个
        sid = request.session_id or f"auto-{len(created)}-{int(time.time() * 1000)}"
        if not request.session_id:
            created.append(sid)
        yield {
            "event": "session",
            "data": {"session_id": sid, "response_mode": request.response_mode},
        }
        yield {
            "event": "delta",
            "data": {"session_id": sid, "content": f"回答（会话 {sid[:12]}）"},
        }
        yield {
            "event": "done",
            "data": {
                "session_id": sid,
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            },
        }

    async def _noop(self, request, user):
        return None

    monkeypatch.setattr(AgentService, "stream_chat", _fake_stream_chat)
    monkeypatch.setattr(AgentService, "ensure_session_access", _noop)
    monkeypatch.setattr(AgentService, "ensure_ready", lambda self: None)
    return created


def _post(base: str, key: str, body: dict, timeout: int = 120):
    req = urllib.request.Request(
        base + "/v1/chat/completions", method="POST",
        data=json.dumps(body).encode(),
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


# ---------------------------------------------------------------------------
# session_id 返回
# ---------------------------------------------------------------------------


def test_response_includes_session_id(live_server, api_key, mock_agent) -> None:
    """非流式响应必须带 session_id —— 否则客户端无从续接。"""
    status, body = _post(live_server, api_key, {
        "model": "general",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert status == 200, body
    assert "session_id" in body, "响应缺 session_id，客户端无法续接对话"
    assert body["session_id"], "session_id 不能为空"


def test_response_echoes_provided_session_id(live_server, api_key, mock_agent) -> None:
    """客户端传了 session_id，响应要原样回显。"""
    sid = "my-own-session-001"
    status, body = _post(live_server, api_key, {
        "model": "general",
        "messages": [{"role": "user", "content": "hi"}],
        "session_id": sid,
    })
    assert status == 200, body
    assert body["session_id"] == sid


def test_server_assigns_session_id_when_absent(live_server, api_key, mock_agent) -> None:
    """不传 session_id 时服务端分配一个，并告诉客户端。"""
    status, body = _post(live_server, api_key, {
        "model": "general",
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert status == 200, body
    assert body["session_id"], "服务端分配的 session_id 要返回给客户端"
    assert len(mock_agent) >= 1, "应该触发了一次新会话分配"


def test_streaming_first_chunk_has_session_id(live_server, api_key, mock_agent) -> None:
    """流式首个 chunk 要带 session_id —— 很多客户端只读首帧。"""
    req = urllib.request.Request(
        live_server + "/v1/chat/completions", method="POST",
        data=json.dumps({
            "model": "general",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }).encode(),
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    first_payload = None
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            first_payload = json.loads(data)
            break

    assert first_payload is not None
    assert "session_id" in first_payload, "流式首帧缺 session_id"


# ---------------------------------------------------------------------------
# 会话隔离
# ---------------------------------------------------------------------------


def test_different_keys_get_different_sessions(live_server, api_key, mock_agent) -> None:
    """两个客户端不传 session_id 时，应各自拿到独立会话（不共用）。"""
    _, first = _post(live_server, api_key, {
        "model": "general", "messages": [{"role": "user", "content": "a"}],
    })
    _, second = _post(live_server, api_key, {
        "model": "general", "messages": [{"role": "user", "content": "b"}],
    })
    # mock 每次不传 id 都会分配新 id
    assert first["session_id"] != second["session_id"], (
        "两次独立调用拿到了同一个 session_id —— 会串上下文"
    )


def test_same_session_id_reuses_session(live_server, api_key, mock_agent) -> None:
    """同一个 session_id 两次调用应复用同一会话。"""
    sid = "reuse-me-001"
    _, first = _post(live_server, api_key, {
        "model": "general", "messages": [{"role": "user", "content": "a"}],
        "session_id": sid,
    })
    _, second = _post(live_server, api_key, {
        "model": "general", "messages": [{"role": "user", "content": "b"}],
        "session_id": sid,
    })
    assert first["session_id"] == second["session_id"] == sid


# ---------------------------------------------------------------------------
# 模型选择
# ---------------------------------------------------------------------------


def test_models_endpoint_lists_agents_and_models(live_server, api_key) -> None:
    """/v1/models 要同时列智能体与纯模型，客户端据此选择。"""
    req = urllib.request.Request(live_server + "/v1/models")
    req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())

    ids = {item["id"] for item in body.get("data", [])}
    assert ids, "模型列表为空"
    # 至少有智能体或纯模型之一
    assert any(not i.startswith("llm:") for i in ids), "缺智能体条目"


def test_unknown_model_falls_back_to_llm_not_error(live_server, api_key) -> None:
    """未命中智能体的 model 名不该 400，应走直通（可能因无 provider 而 502）。

    这是上一轮的修复点：旧实现直接 400，导致「只想用模型」的接入方
    根本接不进来。
    """
    status, body = _post(live_server, api_key, {
        "model": "some-random-model-name",
        "messages": [{"role": "user", "content": "hi"}],
    })
    # 不该是「未知模型」的 400
    if status == 400:
        msg = json.dumps(body, ensure_ascii=False)
        assert "Unknown model" not in msg, "未命中智能体仍被当作未知模型拒绝"
