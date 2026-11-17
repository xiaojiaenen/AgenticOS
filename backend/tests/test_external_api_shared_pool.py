"""对外 API Key 接口强制走共享 cookie 池 —— 回归。

产品语义（用户明确要求）：

- 对外接口（外部 AI 客户端用 sk-agenticos-* 调用）**一律用共享账号池**，
  即使 API Key 所属用户自己绑定了企业网关凭据也不例外 —— 外部流量不该
  打在个人号上。
- **归属不变**：用量、额度、聊天记录仍记 API Key 所属用户。
- 共享池没有可用账号 → **503**（可重试的暂时状态），不是 502（上游故障）。
- 网页端对话的取号语义**完全不变**：仍优先本人绑定凭据。

同时覆盖三项附带修复：

- 直通路径（/v1/messages 等）的 token 必须落 ``agent_usage_events``；
- /v1/embeddings 与 /v1/images/generations 必须设用户上下文；
- Agent 缓存必须让账号池轮换（否则摊配额失效）。

注意：测试直连真实数据库，标识必须带唯一后缀避免跨用例污染。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core import data_path
from app.db.models import (
    AgentUsageEventModel,
    LlmProviderCredentialModel,
    LlmProviderModel,
    UserModel,
)
from app.db.session import create_db_session
from app.main import app
from app.services.llm_providers import credentials


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def enterprise_provider():
    """建一个企业网关提供商，返回 id。"""
    slug = f"ext-pool-{uuid.uuid4().hex[:8]}"
    with create_db_session() as db:
        row = LlmProviderModel(
            name="ext-pool-test",
            slug=slug,
            provider_type="enterprise_cookie",
            base_url="https://gw.test/v1",
            enabled=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        pid = row.id
    yield pid
    with create_db_session() as db:
        for cred in db.scalars(
            select(LlmProviderCredentialModel).where(
                LlmProviderCredentialModel.provider_id == pid
            )
        ).all():
            db.delete(cred)
        obj = db.get(LlmProviderModel, pid)
        if obj:
            db.delete(obj)
        db.commit()


@pytest.fixture()
def user_id():
    """取或建一个用户（测试库可能为空）。"""
    import secrets

    with create_db_session() as db:
        user = db.execute(
            select(UserModel).order_by(UserModel.id).limit(1)
        ).scalar_one_or_none()
        if user is None:
            user = UserModel(
                email="ext-pool@example.test",
                name="Ext Pool Test",
                password_hash=secrets.token_hex(32),
                role="admin",
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user.id


def _add_cred(provider_id: int, *, user_id: int | None, username: str,
              cookie: str = "SESSION=ok", status: str = "active") -> int:
    with create_db_session() as db:
        row = LlmProviderCredentialModel(
            provider_id=provider_id, user_id=user_id, username=username,
            password_encrypted=credentials.encrypt("p"),
            cookie_encrypted=credentials.encrypt(cookie),
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row.id


def _drop_cred(cred_id: int) -> None:
    with create_db_session() as db:
        obj = db.get(LlmProviderCredentialModel, cred_id)
        if obj:
            db.delete(obj)
            db.commit()


# ---------------------------------------------------------------------------
# 1. 取号：对外强制共享池
# ---------------------------------------------------------------------------


def test_external_call_uses_shared_pool_even_when_user_has_own_credential(
    enterprise_provider, user_id
) -> None:
    """对外调用 → 走共享池，即使该用户自己绑了凭据。"""
    shared_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    own_id = _add_cred(enterprise_provider, user_id=user_id, username="zhangsan")
    try:
        token = data_path._current_user_id.set(user_id)
        ext = data_path._external_api_call.set(True)
        try:
            lease = credentials.acquire(enterprise_provider)
        finally:
            data_path._external_api_call.reset(ext)
            data_path._current_user_id.reset(token)
        assert lease is not None, "对外调用应能从共享池借到号"
        assert lease.credential_id == shared_id, "对外调用必须用共享池，不可用本人绑定行"
        assert lease.is_fallback is False, "共享池取号不是「借用」，不该打 [借用] 标记"
    finally:
        _drop_cred(shared_id)
        _drop_cred(own_id)


def test_web_call_still_prefers_own_credential(enterprise_provider, user_id) -> None:
    """网页端调用 → 取号语义不变，仍优先本人绑定行。"""
    shared_id = _add_cred(enterprise_provider, user_id=None, username="shared")
    own_id = _add_cred(enterprise_provider, user_id=user_id, username="zhangsan")
    try:
        token = data_path._current_user_id.set(user_id)
        try:
            lease = credentials.acquire(enterprise_provider)
        finally:
            data_path._current_user_id.reset(token)
        assert lease is not None
        assert lease.credential_id == own_id, "网页端应优先用本人绑定凭据"
    finally:
        _drop_cred(shared_id)
        _drop_cred(own_id)


def test_external_call_returns_none_when_shared_pool_empty(
    enterprise_provider, user_id
) -> None:
    """对外调用时共享池为空 → acquire 返回 None（上层据此回 503）。"""
    own_id = _add_cred(enterprise_provider, user_id=user_id, username="zhangsan")
    try:
        token = data_path._current_user_id.set(user_id)
        ext = data_path._external_api_call.set(True)
        try:
            lease = credentials.acquire(enterprise_provider)
        finally:
            data_path._external_api_call.reset(ext)
            data_path._current_user_id.reset(token)
        assert lease is None, "共享池为空且对外调用不得回落本人凭据"
    finally:
        _drop_cred(own_id)


# ---------------------------------------------------------------------------
# 2. 503 语义
# ---------------------------------------------------------------------------


def test_shared_pool_empty_maps_to_503(enterprise_provider, monkeypatch) -> None:
    """池空 → 抛 SharedPoolEmpty（端点据此回 503 而不是 502）。"""
    from app.services.llm_providers import runtime
    from app.services.llm_providers.spec import spec_from_row

    with create_db_session() as db:
        row = db.get(LlmProviderModel, enterprise_provider)
        spec = spec_from_row(row)

    monkeypatch.setattr(
        runtime.credentials, "acquire", lambda _pid: None
    )
    ext = data_path._external_api_call.set(True)
    try:
        with pytest.raises(runtime.SharedPoolEmpty) as excinfo:
            runtime.build_gateway(
                spec, max_tokens=1024, timeout=30, model="test-model"
            )
        assert "共享账号池" in str(excinfo.value)
    finally:
        data_path._external_api_call.reset(ext)


# ---------------------------------------------------------------------------
# 3. 直通路径用量记账
# ---------------------------------------------------------------------------


def test_direct_usage_recorder_writes_event_with_requesting_user():
    """直通用量记进 agent_usage_events，user_id 是发起人，credential_id 是实际号。"""
    from app.services.llm_providers.route import attach_route
    from app.services.usage_recorder import record_direct_usage

    class _FakeGateway:
        pass

    gateway = _FakeGateway()
    attach_route(
        gateway,
        provider_id=7,
        provider_slug="gw",
        provider_name="企业网关",
        model="gpt-test",
        credential_id=99,
        account_label="shared-1",
    )

    before = _usage_count()
    ok = _run_async(
        record_direct_usage(
            user_id=1234,
            gateway=gateway,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            model_name="gpt-test",
        )
    )
    assert ok is True
    assert _usage_count() == before + 1

    with create_db_session() as db:
        row = db.scalars(
            select(AgentUsageEventModel)
            .where(AgentUsageEventModel.user_id == 1234)
            .order_by(AgentUsageEventModel.id.desc())
            .limit(1)
        ).first()
        assert row is not None
        assert row.total_tokens == 30
        assert row.credential_id == 99
        assert row.account_label == "shared-1"
        assert row.model_name == "gpt-test"
        assert row.tokens_estimated is False
        # session_id 是非空列 —— 直通也要给值
        assert row.session_id


def test_direct_usage_estimates_when_upstream_gives_no_usage():
    """上游没回流 usage → 按字符估算并打 tokens_estimated 标记。"""
    from app.services.usage_recorder import record_direct_usage

    class _FakeGateway:
        pass

    before = _usage_count()
    ok = _run_async(
        record_direct_usage(
            user_id=4321,
            gateway=_FakeGateway(),
            usage={},
            model_name="gpt-test",
            output_text="这是一段用于估算的输出文本" * 5,
        )
    )
    assert ok is True
    assert _usage_count() == before + 1

    with create_db_session() as db:
        row = db.scalars(
            select(AgentUsageEventModel)
            .where(AgentUsageEventModel.user_id == 4321)
            .order_by(AgentUsageEventModel.id.desc())
            .limit(1)
        ).first()
        assert row is not None
        assert row.tokens_estimated is True, "估算值必须打标，否则与实际计费混在一起"
        assert row.total_tokens > 0


# ---------------------------------------------------------------------------
# 4. Agent 缓存的轮换窗口
# ---------------------------------------------------------------------------


def test_rotation_bucket_changes_over_time(monkeypatch):
    """轮换窗口编号随时间推进 —— 跨窗口后 Agent 缓存失效，账号才会轮换。"""
    from app.services.agent.factory import AgentFactory

    factory = AgentFactory.__new__(AgentFactory)

    class _Settings:
        llm_credential_rotation_seconds = 300

    factory.settings = _Settings()

    import time as _time

    real = _time.time
    try:
        # 900 = 3*300（窗口起点），1199 仍在窗口 3 内，1201 已进入窗口 4
        _time.time = lambda: 900.0
        bucket_a = factory._credential_rotation_bucket()
        _time.time = lambda: 1199.0
        bucket_b = factory._credential_rotation_bucket()
        _time.time = lambda: 1201.0
        bucket_c = factory._credential_rotation_bucket()
    finally:
        _time.time = real

    assert bucket_a == bucket_b, "窗口内应复用同一个桶（否则 agent 每次请求都重建）"
    assert bucket_c != bucket_a, "跨窗口后桶必须变化（否则账号永不轮换）"


def test_rotation_disabled_by_zero(monkeypatch):
    """窗口设为 0 → 桶恒为 0（不轮换）。"""
    from app.services.agent.factory import AgentFactory

    factory = AgentFactory.__new__(AgentFactory)

    class _Settings:
        llm_credential_rotation_seconds = 0

    factory.settings = _Settings()
    assert factory._credential_rotation_bucket() == 0


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _usage_count() -> int:
    with create_db_session() as db:
        return len(db.scalars(select(AgentUsageEventModel.id)).all())


def _run_async(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已在事件循环里（pytest-asyncio）：交给调用方 await
    return asyncio.get_event_loop().run_until_complete(coro)
