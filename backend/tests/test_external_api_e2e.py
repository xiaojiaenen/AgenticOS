"""对外网关端点的端到端行为：共享池标记 + 直通用量落库。

这些用例打真实的 HTTP（起一个 uvicorn 实例），验证的是「请求真的经过了
对外端点」这一层 —— 单元测试里的 contextvar 断言覆盖不到端点是否真的
设置了标记。

上游 LLM 被 mock 掉（真实上游不可重复），但端点的鉴权、取号、记账
都是真实代码。
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
        user = db.execute(
            select(UserModel).order_by(UserModel.id).limit(1)
        ).scalar_one_or_none()
        if user is None:
            user = UserModel(
                email="ext-e2e@example.test",
                name="Ext E2E",
                password_hash=hash_password("ExtE2E!2026"),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        uid = user.id

    result = create_api_key(uid, name=f"ext-e2e-{int(time.time())}")
    key = result["key"] if isinstance(result, dict) else getattr(result, "key", None)
    if not key:
        pytest.skip("无法创建 API Key")
    return key, uid


@pytest.fixture()
def mock_direct(monkeypatch):
    """把 ``direct.complete`` 换掉，返回带 usage 的假响应。

    mock 的只有上游调用；端点的鉴权、取号、记账都是真实代码。
    """
    from app.services.llm_providers import direct
    from app.services.llm_providers.route import attach_route

    class _Resp:
        def __init__(self) -> None:
            self.usage = {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}
            self.choices = [{"finish_reason": "stop"}]

        def model_dump(self) -> dict:
            return {"usage": self.usage, "choices": self.choices}

    class _Gateway:
        pass

    gateway = _Gateway()
    attach_route(
        gateway,
        provider_id=1,
        provider_slug="mock",
        provider_name="Mock",
        model="mock-model",
        credential_id=4242,
        account_label="mock-shared",
    )

    async def _fake_complete(db, **kwargs):
        return gateway, "mock-model", _Resp()

    monkeypatch.setattr(direct, "complete", _fake_complete)
    return gateway


def _post(base: str, key: str, path: str, body: dict, timeout: int = 60):
    req = urllib.request.Request(
        base + path, method="POST", data=json.dumps(body).encode()
    )
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.code, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw.decode("utf-8", "replace")}


def test_chat_completions_records_usage_with_api_key_owner(
    live_server, api_key, mock_direct
) -> None:
    """直通调用后用量表里有一行，user_id 是 API Key 所属用户。"""
    from sqlalchemy import select

    from app.db.models import AgentUsageEventModel
    from app.db.session import create_db_session

    key, uid = api_key

    with create_db_session() as db:
        before = len(db.scalars(select(AgentUsageEventModel.id)).all())

    status, _body = _post(
        live_server, key, "/v1/chat/completions",
        {"model": "llm:mock-model", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert status == 200, _body

    with create_db_session() as db:
        rows = db.scalars(
            select(AgentUsageEventModel)
            .where(AgentUsageEventModel.user_id == uid)
            .order_by(AgentUsageEventModel.id.desc())
        ).all()
        assert len(db.scalars(select(AgentUsageEventModel.id)).all()) == before + 1, \
            "直通调用必须落一行用量"
        assert rows, "找不到该用户的用量记录"
        row = rows[0]
        assert row.total_tokens == 18
        assert row.credential_id == 4242, "审计列应记实际借出的账号"
        assert row.model_name == "mock-model"


def test_messages_endpoint_records_usage(live_server, api_key, mock_direct) -> None:
    """/v1/messages（Anthropic 协议）同样要记账。"""
    from sqlalchemy import select

    from app.db.models import AgentUsageEventModel
    from app.db.session import create_db_session

    key, uid = api_key

    with create_db_session() as db:
        before = len(db.scalars(select(AgentUsageEventModel.id)).all())

    status, _body = _post(
        live_server, key, "/v1/messages",
        {"model": "mock-model", "max_tokens": 64,
         "messages": [{"role": "user", "content": "hi"}]},
    )
    assert status == 200, _body

    with create_db_session() as db:
        after = len(db.scalars(select(AgentUsageEventModel.id)).all())
    assert after == before + 1, "/v1/messages 必须记账"


def test_responses_endpoint_records_usage(live_server, api_key, mock_direct) -> None:
    """/v1/responses（OpenAI Responses 协议）同样要记账。"""
    from sqlalchemy import select

    from app.db.models import AgentUsageEventModel
    from app.db.session import create_db_session

    key, uid = api_key

    with create_db_session() as db:
        before = len(db.scalars(select(AgentUsageEventModel.id)).all())

    status, _body = _post(
        live_server, key, "/v1/responses",
        {"model": "mock-model", "input": "hi"},
    )
    assert status == 200, _body

    with create_db_session() as db:
        after = len(db.scalars(select(AgentUsageEventModel.id)).all())
    assert after == before + 1, "/v1/responses 必须记账"
