"""用量记账口径：**算在发起人身上，凭据只做审计标签**。

这组测试守的是三件容易改反的事：

1. ``agent_usage_events.user_id`` 必须是**发起请求的用户**。凭据是系统级共享池
   （一个企业网关账号被多人共用），按凭据归属出来的 token 数对任何个体都不成立。
2. ``model_name`` 必须取网关上**实际发出的模型**，不能用 ``settings.openai_model``
   兜底 —— 否则管理员切换提供商后，历史用量里的模型名会一直是 .env 里的旧值。
3. 审计列（provider / credential / account_label）要随行落库，并且**不参与**
   聚合口径。
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AgentUsageEventModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.agent.orchestrator import StreamOrchestrator
from app.services.llm_providers.route import (
    RouteSnapshot,
    attach_route,
    describe_route,
    resolve_model_name,
)
from app.services.llm_providers.spec import ENV_PROVIDER_SLUG

client = TestClient(app)


# ---------------------------------------------------------------------------
# 纯单元：快照读取
# ---------------------------------------------------------------------------


class _FakeGateway:
    """只承载属性，不发请求。"""

    def __init__(self, adapter_model: str | None = None) -> None:
        if adapter_model is not None:
            self.adapter = SimpleNamespace(model=adapter_model)


class _FakeAgent:
    def __init__(self, gateway: _FakeGateway) -> None:
        self.llm = gateway


def test_describe_route_reads_snapshot_from_gateway_and_agent() -> None:
    gateway = _FakeGateway()
    attach_route(
        gateway,
        provider_id=7,
        provider_slug="gree",
        provider_name="格力百通",
        model="Qwen3.6-35B-A3B",
        credential_id=3,
        account_label="主号",
    )

    for target in (gateway, _FakeAgent(gateway)):
        snapshot = describe_route(target)
        assert snapshot == RouteSnapshot(
            provider_id=7,
            provider_slug="gree",
            provider_name="格力百通",
            model="Qwen3.6-35B-A3B",
            credential_id=3,
            account_label="主号",
        )


def test_describe_route_survives_objects_without_snapshot() -> None:
    # 记账路径上不能因为读不到审计信息就抛异常
    assert describe_route(None) == RouteSnapshot()
    assert describe_route(object()) == RouteSnapshot()
    # 旧埋点只有凭据，也要能读出来
    legacy = _FakeGateway()
    setattr(legacy, "_agenticos_credential_id", 11)
    setattr(legacy, "_agenticos_account_label", "备用")
    snapshot = describe_route(legacy)
    assert snapshot.credential_id == 11
    assert snapshot.account_label == "备用"
    assert snapshot.model is None


def test_resolve_model_name_prefers_snapshot_then_adapter_then_fallback() -> None:
    gateway = _FakeGateway(adapter_model="adapter-model")
    # 没有快照时退到适配器上的模型
    assert resolve_model_name(gateway) == "adapter-model"
    assert resolve_model_name(gateway, fallback="fallback-model") == "adapter-model"

    attach_route(
        gateway,
        provider_id=1,
        provider_slug="gree",
        provider_name="格力百通",
        model="Qwen3.6-35B-A3B",
    )
    # 快照优先于适配器（切换提供商后适配器可能还是旧的）
    assert resolve_model_name(gateway, fallback="fallback-model") == "Qwen3.6-35B-A3B"

    # 两者都没有才用兜底
    assert resolve_model_name(_FakeGateway(), fallback="fallback-model") == "fallback-model"


# ---------------------------------------------------------------------------
# 记账链路
# ---------------------------------------------------------------------------


class _RecordingOrchestrator(StreamOrchestrator):
    """只使用 ``_record_usage_event``，不触碰 mixin 的其他方法。"""

    def __init__(self, storage) -> None:
        self.storage = storage
        self.settings = get_settings()


def _make_orchestrator():
    from app.services.agent.service import AgentService

    service = AgentService(get_settings())
    return _RecordingOrchestrator(service.storage)


def _make_user(prefix: str) -> UserModel:
    email = f"{prefix}-{uuid4().hex[:8]}@usage-audit.test"
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=prefix,
            password_hash=hash_password("password-123"),
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _cleanup_users(*emails: str) -> None:
    with create_db_session() as db:
        user_ids = list(db.scalars(select(UserModel.id).where(UserModel.email.in_(emails))).all())
        if user_ids:
            db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id.in_(user_ids)))
            db.execute(delete(UserModel).where(UserModel.id.in_(user_ids)))
            db.commit()


def _event_data(usage: dict | None = None) -> dict:
    return {
        "usage": usage or {"input_tokens": 40, "output_tokens": 10, "total_tokens": 50},
        "latency_ms": 1200,
        "llm_calls": 2,
    }


def test_usage_event_attributes_to_requesting_user_not_account() -> None:
    """同一个池里的同一个账号，被两个用户先后使用 —— 各自记在各自名下。"""
    import asyncio

    user_a = _make_user("user-a")
    user_b = _make_user("user-b")
    orchestrator = _make_orchestrator()
    session_id = f"usage-audit-{uuid4().hex[:8]}"

    gateway = _FakeGateway()
    attach_route(
        gateway,
        provider_id=1,
        provider_slug="gree",
        provider_name="格力百通",
        model="Qwen3.6-35B-A3B",
        credential_id=42,  # 两人共用同一个账号
        account_label="共享主号",
    )
    agent = _FakeAgent(gateway)

    try:
        for user in (user_a, user_b):
            asyncio.run(
                orchestrator._record_usage_event(
                    session=SimpleNamespace(
                        session_id=session_id,
                        last_usage={},
                        last_latency_ms=0,
                        last_llm_calls=0,
                    ),
                    request=None,
                    user=user,
                    event_data=_event_data(),
                    tool_names=["search"],
                    response_mode="general",
                    agent_profile_id=None,
                    collected_text="hello",
                    agent=agent,
                )
            )

        with create_db_session() as db:
            rows = db.scalars(
                select(AgentUsageEventModel).where(AgentUsageEventModel.session_id == session_id)
            ).all()
            assert len(rows) == 2
            # 归属是发起人，不是凭据
            assert {row.user_id for row in rows} == {user_a.id, user_b.id}
            # 审计列同时记录「走的是同一个共享账号」
            assert {row.credential_id for row in rows} == {42}
            assert {row.account_label for row in rows} == {"共享主号"}
            assert {row.provider_slug for row in rows} == {"gree"}
            assert {row.provider_id for row in rows} == {1}
            assert all(row.total_tokens == 50 for row in rows)
            assert all(row.tokens_estimated is False for row in rows)
    finally:
        _cleanup_users(user_a.email, user_b.email)


def test_usage_event_model_name_comes_from_gateway_not_env() -> None:
    """切换提供商后，落库的模型名必须是实际发出的那个。"""
    import asyncio

    user = _make_user("user-model")
    orchestrator = _make_orchestrator()
    session_id = f"usage-model-{uuid4().hex[:8]}"

    gateway = _FakeGateway()
    attach_route(
        gateway,
        provider_id=2,
        provider_slug="deepseek",
        provider_name="DeepSeek",
        model="deepseek-chat",
    )

    try:
        asyncio.run(
            orchestrator._record_usage_event(
                session=SimpleNamespace(
                    session_id=session_id, last_usage={}, last_latency_ms=0, last_llm_calls=0
                ),
                request=None,
                user=user,
                event_data=_event_data(),
                tool_names=[],
                response_mode="general",
                agent_profile_id=None,
                agent=_FakeAgent(gateway),
            )
        )
        with create_db_session() as db:
            row = db.scalars(
                select(AgentUsageEventModel).where(AgentUsageEventModel.session_id == session_id)
            ).one()
        assert row.model_name == "deepseek-chat"
        assert row.model_name != get_settings().openai_model
        # API Key 型没有账号池，凭据维度必须为空
        assert row.credential_id is None
    finally:
        _cleanup_users(user.email)


def test_usage_event_flags_estimated_tokens() -> None:
    """上游没回流 usage 时，估算值必须打标，不能和实际计费混在一起。"""
    import asyncio

    user = _make_user("user-estimate")
    orchestrator = _make_orchestrator()
    session_id = f"usage-estimate-{uuid4().hex[:8]}"

    try:
        asyncio.run(
            orchestrator._record_usage_event(
                session=SimpleNamespace(
                    session_id=session_id, last_usage={}, last_latency_ms=0, last_llm_calls=0
                ),
                request=None,
                user=user,
                event_data={"usage": {}, "latency_ms": 100, "llm_calls": 1},
                tool_names=[],
                response_mode="general",
                agent_profile_id=None,
                collected_text="一" * 90,
                agent=None,
            )
        )
        with create_db_session() as db:
            row = db.scalars(
                select(AgentUsageEventModel).where(AgentUsageEventModel.session_id == session_id)
            ).one()
        assert row.tokens_estimated is True
        assert row.total_tokens > 0
    finally:
        _cleanup_users(user.email)


# ---------------------------------------------------------------------------
# 端点口径
# ---------------------------------------------------------------------------


def _token_for(user: UserModel) -> str:
    settings = get_settings()
    # 角色可能在被测试里改过（提权成 admin），token 必须反映库里的最新值
    with create_db_session() as db:
        fresh = db.get(UserModel, user.id)
        role = fresh.role if fresh is not None else user.role
    return create_access_token(
        {"sub": str(user.id), "email": user.email, "role": role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


def _insert_usage(**kwargs) -> AgentUsageEventModel:
    with create_db_session() as db:
        row = AgentUsageEventModel(**kwargs)
        db.add(row)
        db.commit()
        db.refresh(row)
        db.expunge(row)
    return row


def test_my_usage_only_counts_caller() -> None:
    user_a = _make_user("my-usage-a")
    user_b = _make_user("my-usage-b")
    session_a = f"sess-a-{uuid4().hex[:6]}"
    session_b = f"sess-b-{uuid4().hex[:6]}"
    try:
        _insert_usage(
            user_id=user_a.id, session_id=session_a, model_name="m-a",
            input_tokens=60, output_tokens=40, total_tokens=100, llm_calls=1,
            provider_slug="gree", credential_id=9, account_label="共享",
            tokens_estimated=False,
        )
        _insert_usage(
            user_id=user_b.id, session_id=session_b, model_name="m-b",
            input_tokens=600, output_tokens=400, total_tokens=1000, llm_calls=1,
            provider_slug="gree", credential_id=9, account_label="共享",
            tokens_estimated=False,
        )

        response = client.get(
            "/api/v1/dashboard/my-usage?days=30",
            headers={"Authorization": f"Bearer {_token_for(user_a)}"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total_tokens"] == 100
        assert payload["runs"] == 1
        # 用户视图不暴露共享账号信息
        assert "providers" not in payload
        assert "accounts" not in payload
        assert {item["name"] for item in payload["models"]} == {"m-a"}
    finally:
        _cleanup_users(user_a.email, user_b.email)


def test_usage_routes_requires_admin() -> None:
    user = _make_user("routes-forbidden")
    try:
        response = client.get(
            "/api/v1/dashboard/usage-routes",
            headers={"Authorization": f"Bearer {_token_for(user)}"},
        )
        assert response.status_code == 403
    finally:
        _cleanup_users(user.email)


def test_usage_routes_aggregates_by_route_and_marks_unattributed() -> None:
    admin = _make_user("routes-admin")
    with create_db_session() as db:
        row = db.get(UserModel, admin.id)
        assert row is not None
        row.role = "admin"
        db.commit()

    session_id = f"routes-{uuid4().hex[:6]}"
    # 这个端点是**全站**聚合（管理员排障用），必须和库里其他测试造的数据区分开：
    # 用唯一的 slug / credential_id 定位自己那几行，断言增量而不是绝对总数。
    slug = f"gree-{uuid4().hex[:6]}"
    credential_id = 900000 + (uuid4().int % 99999)

    def _baseline() -> dict[str, int]:
        with create_db_session() as db:
            return {
                "runs": int(db.scalar(select(func.count()).select_from(AgentUsageEventModel)) or 0),
                "env_fallback": int(
                    db.scalar(
                        select(func.count()).select_from(AgentUsageEventModel).where(
                            AgentUsageEventModel.provider_slug == ENV_PROVIDER_SLUG
                        )
                    )
                    or 0
                ),
                "legacy": int(
                    db.scalar(
                        select(func.count()).select_from(AgentUsageEventModel).where(
                            AgentUsageEventModel.provider_id.is_(None),
                            AgentUsageEventModel.provider_slug.is_(None),
                        )
                    )
                    or 0
                ),
                "estimated": int(
                    db.scalar(
                        select(func.count()).select_from(AgentUsageEventModel).where(
                            AgentUsageEventModel.tokens_estimated.is_(True)
                        )
                    )
                    or 0
                ),
            }

    base = _baseline()
    try:
        # 两条走本次唯一的提供商主号，一条走环境变量兜底，一条是迁移前的历史行
        for tokens, calls in ((120, 2), (80, 1)):
            _insert_usage(
                user_id=admin.id, session_id=session_id, model_name="Qwen3.6-35B-A3B",
                total_tokens=tokens, llm_calls=calls, provider_id=99001, provider_slug=slug,
                provider_name="格力百通", credential_id=credential_id, account_label="主号",
                tokens_estimated=False,
            )
        _insert_usage(
            user_id=admin.id, session_id=session_id, model_name="gpt-4o-mini",
            total_tokens=30, llm_calls=1, provider_id=None, provider_slug=ENV_PROVIDER_SLUG,
            provider_name="环境变量配置", credential_id=None, tokens_estimated=False,
        )
        _insert_usage(
            user_id=admin.id, session_id=session_id, model_name="gpt-4o-mini",
            total_tokens=10, llm_calls=1, provider_id=None, provider_slug=None,
            credential_id=None, tokens_estimated=True,
        )

        response = client.get(
            "/api/v1/dashboard/usage-routes?days=30",
            headers={"Authorization": f"Bearer {_token_for(admin)}"},
        )
        assert response.status_code == 200
        payload = response.json()

        assert payload["totals"]["runs"] - base["runs"] == 4
        assert payload["totals"]["env_fallback_runs"] - base["env_fallback"] == 1
        assert payload["totals"]["legacy_runs"] - base["legacy"] == 1
        assert payload["totals"]["estimated_runs"] - base["estimated"] == 1

        gree = next(item for item in payload["providers"] if item["provider_slug"] == slug)
        assert gree["runs"] == 2
        assert gree["total_tokens"] == 200

        account = next(
            item for item in payload["accounts"] if item["credential_id"] == credential_id
        )
        assert account["runs"] == 2
        assert account["total_tokens"] == 200
        assert account["provider_slug"] == slug
    finally:
        _cleanup_users(admin.email)
