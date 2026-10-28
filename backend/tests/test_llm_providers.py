"""AI 提供商层测试。

覆盖四类风险，每一类都对应一个真实会出问题的地方：

1. **解析优先级**：DB 默认 > DB 首个启用 > 环境变量兜底。顺序错了会出现
   「配了新提供商但还在用旧地址」这种最难排查的症状。
2. **密钥不进响应**：``to_public_dict`` / 凭据状态一旦泄露密文或尾部片段，
   一个只读管理员就能把全站凭据捞走。
3. **Cookie 认证构建**：企业网关必须构造出带 ``Cookie`` 头的适配器，且
   登录态失效时**不能**静默用一个空 Key 去打上游。
4. **过期判定不信 status**：``status=active`` + 已过期 = 不可用。只查 status
   是旧实现的 bug，会让每次请求都撞一次 401 再触发重登。
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.core.timezone import app_now
from app.db.models import LlmProviderCredentialModel, LlmProviderModel, UserModel
from app.db.session import create_db_session
from app.main import app

client = TestClient(app)

ADMIN_EMAIL = "llm-provider-admin@agenticos.dev"

# token 的 ``sub`` 是用户 id 的字符串形式（见 deps.get_current_user），
# 不能塞 email —— 那样会直接 401「登录凭证无效」。
_ADMIN_ID: dict[str, int] = {}


@pytest.fixture(scope="module", autouse=True)
def _admin_user():
    """建一个管理员；endpoint 全部走 require_admin。"""
    from tests.conftest import safe_delete_users

    safe_delete_users(ADMIN_EMAIL)
    with create_db_session() as db:
        user = UserModel(
            email=ADMIN_EMAIL,
            name="Provider Admin",
            password_hash="x",
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _ADMIN_ID["id"] = user.id
    yield
    safe_delete_users(ADMIN_EMAIL)


@pytest.fixture(autouse=True)
def _clean_providers():
    """每个用例从空表开始：提供商是全局单例，残留会污染解析断言。"""

    def _wipe() -> None:
        with create_db_session() as db:
            db.execute(delete(LlmProviderCredentialModel))
            db.execute(delete(LlmProviderModel))
            db.commit()
        from app.services.llm_providers.spec import invalidate_cache

        invalidate_cache()

    _wipe()
    yield
    _wipe()


def _auth_headers() -> dict[str, str]:
    from app.core.config import get_settings

    settings = get_settings()
    token = create_access_token(
        {"sub": str(_ADMIN_ID["id"])},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. 解析优先级
# ---------------------------------------------------------------------------


def test_falls_back_to_env_when_no_provider():
    """一个提供商都没建时，必须回落环境变量 —— 存量部署不能因为加表就开不了机。"""
    from app.services.llm_providers.spec import ENV_PROVIDER_SLUG, resolve_active_provider

    spec = resolve_active_provider()
    assert spec.slug == ENV_PROVIDER_SLUG
    assert spec.source == "env"


def test_default_provider_wins_over_first_enabled():
    from app.services.llm_providers.spec import (
        create_provider,
        resolve_active_provider,
    )

    with create_db_session() as db:
        create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m-a", api_key="key-a",
            is_default=True,
        )
        create_provider(
            db, name="B", slug="b", provider_type="openai_compatible",
            base_url="https://b.example.com", model="m-b", api_key="key-b",
            is_default=False,
        )
        db.commit()

    assert resolve_active_provider().slug == "a"


def test_disabled_default_provider_is_skipped():
    """默认提供商被停用后，不能继续拿它当生效项。"""
    from app.services.llm_providers.spec import (
        create_provider,
        resolve_active_provider,
        set_default_provider,
        update_provider,
    )

    with create_db_session() as db:
        first = create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m-a", api_key="key-a",
            is_default=True,
        )
        second = create_provider(
            db, name="B", slug="b", provider_type="openai_compatible",
            base_url="https://b.example.com", model="m-b", api_key="key-b",
        )
        db.commit()
        # 先把默认让给 B，再把 B 停用：此时既没有启用的默认，也不该回到 A？
        # 期望：B 停了就落到「第一个启用的」= A。这比「无提供商可用」合理。
        set_default_provider(db, second.id)
        update_provider(db, second, fields={"enabled": False})
        db.commit()
        assert first.id != second.id

    assert resolve_active_provider().slug == "a"


def test_first_provider_auto_becomes_default():
    """建了第一个提供商但没勾默认时自动接管，避免「建了却没人用」。"""
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="只有这一个", slug="only", provider_type="openai_compatible",
            base_url="https://only.example.com", model="m", api_key="k",
        )
        db.commit()
        assert row.is_default is True


def test_default_is_globally_unique():
    from app.services.llm_providers.spec import (
        create_provider,
        set_default_provider,
    )

    with create_db_session() as db:
        a = create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m", api_key="k", is_default=True,
        )
        b = create_provider(
            db, name="B", slug="b", provider_type="openai_compatible",
            base_url="https://b.example.com", model="m", api_key="k",
        )
        db.commit()
        set_default_provider(db, b.id)
        db.commit()
        db.refresh(a)
        assert a.is_default is False
        assert b.is_default is True


def test_cannot_set_disabled_provider_as_default():
    from app.services.llm_providers.spec import (
        ProviderConfigError,
        create_provider,
        set_default_provider,
    )

    with create_db_session() as db:
        row = create_provider(
            db, name="停用的", slug="off", provider_type="openai_compatible",
            base_url="https://off.example.com", model="m", api_key="k", enabled=False,
        )
        db.commit()
        with pytest.raises(ProviderConfigError, match="停用"):
            set_default_provider(db, row.id)


# ---------------------------------------------------------------------------
# 2. 密钥不外泄
# ---------------------------------------------------------------------------


def test_public_dict_never_exposes_secrets():
    from app.services.llm_providers.spec import create_provider, to_public_dict

    secret = "sk-super-secret-value-123456"
    with create_db_session() as db:
        row = create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m", api_key=secret,
        )
        db.commit()
        payload = to_public_dict(row)

    blob = str(payload)
    assert secret not in blob
    # 连尾部片段都不能有：尾部 4 位足够做撞库验证
    assert secret[-4:] not in blob
    assert payload["has_api_key"] is True


def test_api_key_is_encrypted_at_rest():
    from app.services.llm_providers.spec import create_provider

    secret = "sk-plaintext-should-not-appear"
    with create_db_session() as db:
        row = create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m", api_key=secret,
        )
        db.commit()
        db.refresh(row)
        assert row.api_key_encrypted != secret
        assert secret not in (row.api_key_encrypted or "")


def test_credential_status_never_exposes_password_or_cookie():
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import (
        create_provider,
        credential_status_dict,
    )

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        credentials.save_credentials(
            db, row.id, username="zhangsan", password="P@ssw0rd-should-not-leak",
            login_url="https://gw.example.com/login",
        )
        db.commit()
        status = credential_status_dict(credentials.get_credential(db, row.id))

    blob = str(status)
    assert "P@ssw0rd-should-not-leak" not in blob
    assert status["username"] == "zhangsan"
    assert status["has_password"] is True


def test_update_with_empty_api_key_clears_it():
    """前端不回显 Key，如果「空 = 不变」，泄露的 Key 就永远删不掉。"""
    from app.services.llm_providers.spec import create_provider, update_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m", api_key="sk-original",
        )
        db.commit()
        assert row.api_key_encrypted

        update_provider(db, row, fields={"api_key": ""})
        db.commit()
        assert not row.api_key_encrypted


def test_update_without_api_key_field_keeps_it():
    from app.services.llm_providers.spec import create_provider, update_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="A", slug="a", provider_type="openai_compatible",
            base_url="https://a.example.com", model="m", api_key="sk-original",
        )
        db.commit()
        before = row.api_key_encrypted
        update_provider(db, row, fields={"name": "改了名字"})
        db.commit()
        assert row.api_key_encrypted == before


# ---------------------------------------------------------------------------
# 3. 构建与登录态
# ---------------------------------------------------------------------------


def test_build_gateway_for_api_key_provider():
    from app.services.llm_providers.runtime import build_gateway
    from app.services.llm_providers.spec import ProviderSpec

    spec = ProviderSpec(
        name="A", slug="a", provider_type="openai_compatible",
        base_url="https://a.example.com", model="model-a", api_key="sk-x",
    )
    gateway = build_gateway(spec, max_tokens=256, timeout=30)
    assert gateway.adapter.model == "model-a"
    assert "a.example.com" in str(gateway.adapter.client.base_url)


def test_build_gateway_injects_cookie_header():
    from app.services.llm_providers import credentials
    from app.services.llm_providers.runtime import build_gateway
    from app.services.llm_providers.spec import create_provider, spec_from_row

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com", model="gw-model",
        )
        db.commit()
        credentials.save_manual_cookie(db, row.id, cookie="session=abc; token=xyz")
        db.commit()
        spec = spec_from_row(row)

    gateway = build_gateway(spec, max_tokens=256, timeout=30)
    headers = gateway.adapter.client.default_headers
    assert headers.get("Cookie") == "session=abc; token=xyz"


def test_build_gateway_refuses_enterprise_without_cookie():
    """Cookie 缺失时必须抛错，不能拿空 Key 去打上游后静默失败。"""
    from app.services.llm_providers.runtime import ProviderUnavailable, build_gateway
    from app.services.llm_providers.spec import create_provider, spec_from_row

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        spec = spec_from_row(row)

    with pytest.raises(ProviderUnavailable, match="登录态不可用"):
        build_gateway(spec, max_tokens=256, timeout=30)


def test_build_gateway_refuses_api_key_provider_without_key():
    from app.services.llm_providers.runtime import ProviderUnavailable, build_gateway
    from app.services.llm_providers.spec import ProviderSpec

    spec = ProviderSpec(
        name="A", slug="a", provider_type="openai_compatible",
        base_url="https://a.example.com", model="m", api_key=None,
    )
    with pytest.raises(ProviderUnavailable, match="API Key"):
        build_gateway(spec, max_tokens=256, timeout=30)


def test_expired_cookie_is_treated_as_unusable():
    """``status=active`` 但已过期 = 不可用。只看 status 是旧实现的 bug。"""
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        credentials.save_manual_cookie(
            db, row.id, cookie="session=old",
            expire_at=app_now() - timedelta(minutes=1),
        )
        db.commit()
        provider_id = row.id

    assert credentials.get_active_cookie(provider_id) is None


def test_status_dict_reports_expired_even_if_status_is_active():
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import (
        create_provider,
        credential_status_dict,
    )

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        credential = credentials.save_manual_cookie(
            db, row.id, cookie="session=old",
            expire_at=app_now() - timedelta(minutes=1),
        )
        db.commit()
        status = credential_status_dict(credential)

    assert status["status"] == "expired"


def test_needs_refresh_true_when_password_set_but_cookie_missing():
    """有账号密码但没有 Cookie（或从未登录成功）时必须续期。

    注意「连凭据行都没有」是另一回事：没有账号密码就没有登录的原料，
    定时任务应当跳过而不是每 20 分钟失败一次。
    """
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        credentials.save_credentials(
            db, row.id, username="u", password="p",
            login_url="https://gw.example.com/login",
        )
        db.commit()
        provider_id = row.id

    assert credentials.needs_refresh(provider_id) is True


def test_needs_refresh_false_when_no_credential_at_all():
    """没有凭据行 = 没有登录原料，cron 不该反复失败。"""
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        provider_id = row.id

    assert credentials.needs_refresh(provider_id) is False


def test_disabled_first_provider_does_not_break_creation():
    """先建一个「暂不启用」的提供商不能抛错，也不能抢走默认位。"""
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="备用", slug="standby", provider_type="openai_compatible",
            base_url="https://standby.example.com", model="m", api_key="k",
            enabled=False,
        )
        db.commit()
        assert row.is_default is False


def test_needs_refresh_false_when_fresh_and_auto_refresh_off():
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        credentials.save_credentials(
            db, row.id, username="u", password="p",
            login_url="https://gw.example.com/login", auto_refresh=False,
        )
        credentials.save_manual_cookie(db, row.id, cookie="session=fresh")
        db.commit()
        provider_id = row.id

    # auto_refresh=False 时定时任务不应碰它
    assert credentials.needs_refresh(provider_id) is False


def test_passing_new_password_invalidates_old_cookie():
    """换密码后旧 Cookie 承载的是旧身份，必须作废。"""
    from app.services.llm_providers import credentials
    from app.services.llm_providers.spec import create_provider

    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com",
        )
        db.commit()
        credentials.save_credentials(db, row.id, username="u", password="old")
        credentials.save_manual_cookie(db, row.id, cookie="session=stale")
        db.commit()
        assert credentials.get_active_cookie(row.id) is not None

        credentials.save_credentials(db, row.id, username="u", password="new")
        db.commit()
        assert credentials.get_active_cookie(row.id) is None


# ---------------------------------------------------------------------------
# 4. 端点
# ---------------------------------------------------------------------------


def test_provider_crud_endpoints():
    headers = _auth_headers()

    created = client.post(
        "/api/v1/settings/llm-providers",
        json={
            "name": "DeepSeek",
            "slug": "deepseek",
            "provider_type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "api_key": "sk-endpoint-secret",
            "is_default": True,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert "sk-endpoint-secret" not in created.text
    assert payload["has_api_key"] is True
    provider_id = payload["id"]

    listed = client.get("/api/v1/settings/llm-providers", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["items"]) == 1
    assert body["active"]["slug"] == "deepseek"
    assert "sk-endpoint-secret" not in listed.text

    patched = client.patch(
        f"/api/v1/settings/llm-providers/{provider_id}",
        json={"model": "deepseek-reasoner"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert patched.json()["model"] == "deepseek-reasoner"

    removed = client.delete(
        f"/api/v1/settings/llm-providers/{provider_id}", headers=headers
    )
    assert removed.status_code == 204


def test_duplicate_slug_is_rejected():
    headers = _auth_headers()
    body = {
        "name": "A", "slug": "same", "provider_type": "openai_compatible",
        "base_url": "https://a.example.com", "model": "m", "api_key": "k",
    }
    assert client.post(
        "/api/v1/settings/llm-providers", json=body, headers=headers
    ).status_code == 201
    second = client.post(
        "/api/v1/settings/llm-providers", json=body, headers=headers
    )
    assert second.status_code == 400
    assert "slug" in second.json()["detail"]


def test_non_admin_cannot_manage_providers():
    from tests.conftest import safe_delete_users

    email = "llm-provider-plain@agenticos.dev"
    safe_delete_users(email)
    with create_db_session() as db:
        user = UserModel(
            email=email, name="Plain", password_hash="x",
            role="user", is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        plain_id = user.id
    try:
        from app.core.config import get_settings

        settings = get_settings()
        token = create_access_token(
            {"sub": str(plain_id)},
            secret=settings.auth_secret_key,
            expires_in_seconds=settings.auth_token_expire_minutes * 60,
        )
        resp = client.get(
            "/api/v1/settings/llm-providers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
    finally:
        safe_delete_users(email)


def test_enterprise_only_credential_endpoint():
    """给 API Key 类型提供商配登录凭据应被拒绝，而不是静默写入无用行。"""
    headers = _auth_headers()
    created = client.post(
        "/api/v1/settings/llm-providers",
        json={
            "name": "API", "slug": "api-only", "provider_type": "openai_compatible",
            "base_url": "https://a.example.com", "model": "m", "api_key": "k",
        },
        headers=headers,
    )
    provider_id = created.json()["id"]
    resp = client.put(
        f"/api/v1/settings/llm-providers/{provider_id}/credential",
        json={"username": "u", "password": "p"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "企业网关" in resp.json()["detail"]


def test_manual_cookie_endpoint_rejects_malformed_cookie():
    headers = _auth_headers()
    created = client.post(
        "/api/v1/settings/llm-providers",
        json={
            "name": "网关", "slug": "gw", "provider_type": "enterprise_cookie",
            "base_url": "https://gw.example.com",
        },
        headers=headers,
    )
    provider_id = created.json()["id"]
    resp = client.put(
        f"/api/v1/settings/llm-providers/{provider_id}/credential/cookie",
        json={"cookie": "这不是cookie"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "格式" in resp.json()["detail"]


def test_manual_cookie_endpoint_accepts_valid_cookie():
    headers = _auth_headers()
    created = client.post(
        "/api/v1/settings/llm-providers",
        json={
            "name": "网关", "slug": "gw", "provider_type": "enterprise_cookie",
            "base_url": "https://gw.example.com",
        },
        headers=headers,
    )
    provider_id = created.json()["id"]
    resp = client.put(
        f"/api/v1/settings/llm-providers/{provider_id}/credential/cookie",
        json={"cookie": "session=abc; token=xyz"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_cookie"] is True
    assert body["status"] == "active"
    # 响应里不能出现 Cookie 内容
    assert "session=abc" not in resp.text


def test_import_env_endpoint_creates_provider():
    headers = _auth_headers()
    resp = client.post(
        "/api/v1/settings/llm-providers/import-env", headers=headers
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "env-import"
    # 环境变量里的 dummy key 不该明文出现
    assert "test-dummy-key" not in resp.text


def test_provider_operations_are_audited():
    """提供商配置等于「全站用哪个模型 + 凭据是什么」，必须可追溯。"""
    from app.db.models import AuditLogModel

    headers = _auth_headers()
    created = client.post(
        "/api/v1/settings/llm-providers",
        json={
            "name": "审计", "slug": "audit-check",
            "provider_type": "openai_compatible",
            "base_url": "https://a.example.com", "model": "m", "api_key": "sk-secret",
        },
        headers=headers,
    )
    assert created.status_code == 201
    provider_id = created.json()["id"]

    with create_db_session() as db:
        actions = set(
            db.scalars(
                select(AuditLogModel.action).where(
                    AuditLogModel.resource_type == "llm_provider",
                    AuditLogModel.resource_id == provider_id,
                )
            ).all()
        )
        details = [
            row.detail_json
            for row in db.scalars(
                select(AuditLogModel).where(
                    AuditLogModel.resource_type == "llm_provider",
                    AuditLogModel.resource_id == provider_id,
                )
            ).all()
        ]

    assert "llm_provider.create" in actions
    # 审计只记「有没有配 Key」，不记 Key 本身
    assert all("sk-secret" not in (d or "") for d in details)


# ---------------------------------------------------------------------------
# 5. 账号池 / 模型目录 / 用途绑定（端点）
# ---------------------------------------------------------------------------


def _create_cookie_provider(preset: str | None = None, slug: str = "gw") -> int:
    body = {
        "name": "网关", "slug": slug, "provider_type": "enterprise_cookie",
        "base_url": "https://gw.example.com",
    }
    if preset:
        body = {"name": "百通", "slug": "bt", "provider_type": "", "base_url": "", "preset": preset}
    resp = client.post("/api/v1/settings/llm-providers", json=body, headers=_auth_headers())
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_create_provider_from_preset_endpoint():
    """只选一个预设，地址/类型/登录动作就都齐了 —— 不用照文档抄路径。"""
    resp = client.post(
        "/api/v1/settings/llm-providers",
        json={"name": "百通", "slug": "bt", "preset": "gree_baitong"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["provider_type"] == "enterprise_cookie"
    assert body["base_url"].endswith("/agents/baitong")
    assert body["needs_cookie"] is True
    assert body["preset"] == "gree_baitong"
    assert body["extra"]["login"]["submit_text"] == "授权并登录"
    assert body["roles"]["chat"] == "Qwen3.6-35B-A3B"


def test_preset_list_is_exposed_in_listing():
    body = client.get("/api/v1/settings/llm-providers", headers=_auth_headers()).json()
    slugs = {item["slug"] for item in body["presets"]}
    assert "gree_baitong" in slugs
    assert {item["value"] for item in body["model_roles"]} >= {"chat", "fast", "vision"}


def test_account_pool_crud_endpoints():
    provider_id = _create_cookie_provider()
    base = f"/api/v1/settings/llm-providers/{provider_id}/accounts"

    first = client.post(
        base,
        json={"label": "主力", "username": "u1", "password": "p1", "priority": 10},
        headers=_auth_headers(),
    )
    assert first.status_code == 201, first.text
    # 响应里不能出现密码
    assert "p1" not in first.text
    account_id = first.json()["id"]

    second = client.post(
        base, json={"label": "备用", "username": "u2", "password": "p2"}, headers=_auth_headers()
    )
    assert second.status_code == 201

    listed = client.get(base, headers=_auth_headers()).json()
    assert listed["total"] == 2
    assert listed["active"] == 0  # 都还没登录过
    assert "rotation_policy" in listed

    # 重复用户名应被拒绝（服务层去重，DB 不再有唯一约束兜底）
    dup = client.post(base, json={"username": "u1", "password": "x"}, headers=_auth_headers())
    assert dup.status_code == 400

    patched = client.patch(
        f"{base}/{account_id}", json={"disabled": True, "priority": 5}, headers=_auth_headers()
    )
    assert patched.status_code == 200
    assert patched.json()["disabled"] is True
    assert patched.json()["status"] == "disabled"

    removed = client.delete(f"{base}/{second.json()['id']}", headers=_auth_headers())
    assert removed.status_code == 204
    assert client.get(base, headers=_auth_headers()).json()["total"] == 1


def test_account_cookie_endpoint_targets_specific_account():
    provider_id = _create_cookie_provider()
    base = f"/api/v1/settings/llm-providers/{provider_id}/accounts"
    account_id = client.post(
        base, json={"username": "u1", "password": "p1"}, headers=_auth_headers()
    ).json()["id"]

    resp = client.put(
        f"{base}/{account_id}/cookie",
        json={"cookie": "SESSION=abc; cookie=def"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "active"
    assert resp.json()["has_cookie"] is True
    # Cookie 内容不能回显
    assert "SESSION=abc" not in resp.text

    # 账号不属于这个提供商时按不存在处理，避免跨提供商串改
    other_id = _create_cookie_provider(slug="gw-other")
    bad = client.put(
        f"/api/v1/settings/llm-providers/{other_id}/accounts/{account_id}/cookie",
        json={"cookie": "SESSION=x"},
        headers=_auth_headers(),
    )
    assert bad.status_code == 404


def test_model_discovery_endpoint_persists_and_is_idempotent(monkeypatch):
    from app.services.llm_providers import discovery, runtime

    provider_id = _create_cookie_provider()
    with create_db_session() as db:
        from app.services.llm_providers import credentials

        credentials.add_account(db, provider_id, username="u1", password="p1")
        account = credentials.get_credential(db, provider_id)
        credentials.save_manual_cookie(db, provider_id, cookie="SESSION=abc", credential_id=account.id)
        db.commit()

    async def fake_fetch(**kwargs):
        return (
            [
                {"model_key": "qwen3.6-35b", "model_name": "Qwen3.6-35B-A3B",
                 "task_type": "text-generation", "max_tokens": 262144, "extra": {}},
                {"model_key": "qwen-image-21", "model_name": "Qwen-Image-2.1",
                 "task_type": "text-to-image", "max_tokens": None, "extra": {}},
            ],
            {"ok": True, "url": "https://gw.example.com/json/model-configs.json"},
        )

    monkeypatch.setattr(discovery, "fetch_models", fake_fetch)

    url = f"/api/v1/settings/llm-providers/{provider_id}/models"
    first = client.post(f"{url}/discover", headers=_auth_headers())
    assert first.status_code == 200, first.text
    assert first.json()["added"] == 2
    assert first.json()["ok"] is True

    second = client.post(f"{url}/discover", headers=_auth_headers())
    assert second.json()["added"] == 0
    assert second.json()["updated"] == 2

    listed = client.get(url, headers=_auth_headers()).json()
    assert listed["total"] == 2
    names = {item["model_name"] for item in listed["items"]}
    assert "Qwen3.6-35B-A3B" in names
    assert runtime is not None


def test_model_discovery_requires_usable_account():
    """没有可用登录态时不能靠 discover 蒙出模型清单。"""
    provider_id = _create_cookie_provider()
    resp = client.post(
        f"/api/v1/settings/llm-providers/{provider_id}/models/discover", headers=_auth_headers()
    )
    assert resp.status_code == 400
    assert "账号" in resp.json()["detail"]


def test_roles_endpoint_rejects_model_outside_catalog(monkeypatch):
    from app.services.llm_providers import catalog, discovery

    provider_id = _create_cookie_provider()
    with create_db_session() as db:
        catalog.upsert_models(
            db, provider_id,
            [{"model_key": "qwen3.6-35b", "model_name": "Qwen3.6-35B-A3B",
              "task_type": "text-generation"}],
        )
        db.commit()

    ok = client.put(
        f"/api/v1/settings/llm-providers/{provider_id}/roles",
        json={"roles": {"chat": "Qwen3.6-35B-A3B"}},
        headers=_auth_headers(),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["roles"]["chat"] == "Qwen3.6-35B-A3B"

    # 填 model ID 而不是 name 是最常见的手误，必须在保存时拦住
    bad = client.put(
        f"/api/v1/settings/llm-providers/{provider_id}/roles",
        json={"roles": {"chat": "qwen3.6-35b"}},
        headers=_auth_headers(),
    )
    assert bad.status_code == 400
    assert "目录" in bad.json()["detail"]

    unknown = client.put(
        f"/api/v1/settings/llm-providers/{provider_id}/roles",
        json={"roles": {"dialogue": "x"}},
        headers=_auth_headers(),
    )
    assert unknown.status_code == 400
    assert discovery is not None


# ---------------------------------------------------------------------------
# 6. 探测不能误伤登录态
# ---------------------------------------------------------------------------


def _cookie_spec(provider_id: int):
    from app.services.llm_providers.spec import ProviderSpec

    return ProviderSpec(
        name="网关", slug="gw", provider_type="enterprise_cookie",
        base_url="https://gw.example.com", model="m", provider_id=provider_id,
    )


def test_probe_http_500_does_not_invalidate_cookie(monkeypatch):
    """上游 500 是它自己坏了，不该把我们的 Cookie 判死。

    这是最恶劣的一类误判：点一次「测试」，全站对话立刻停摆，而原因被记成
    「凭据失效」，排查方向完全错。
    """
    from app.services.llm_providers import credentials as cred_module
    from app.services.llm_providers import runtime as runtime_module
    from app.services.llm_providers.credentials import AccountLease

    monkeypatch.setattr(
        cred_module, "acquire",
        lambda provider_id: AccountLease(credential_id=7, cookie="SESSION=ok", label="a"),
    )
    invalidated: list[int] = []
    monkeypatch.setattr(
        cred_module, "mark_cookie_invalid",
        lambda credential_id, reason: invalidated.append(credential_id),
    )

    async def ok_network(spec, transport):
        return {"stage": "network", "ok": True, "elapsed_ms": 1}

    async def boom_registry(spec, transport, headers):
        return (
            {"stage": "auth", "ok": False, "elapsed_ms": 1, "status_code": 500, "message": "boom"},
            [],
        )

    monkeypatch.setattr(runtime_module, "_probe_network", ok_network)
    monkeypatch.setattr(runtime_module, "_probe_registry", boom_registry)

    import asyncio

    result = asyncio.run(runtime_module.test_provider(_cookie_spec(3)))
    assert result["ok"] is False
    assert result["stage"] == "auth"
    assert invalidated == []


def test_probe_401_invalidates_cookie(monkeypatch):
    from app.services.llm_providers import credentials as cred_module
    from app.services.llm_providers import runtime as runtime_module
    from app.services.llm_providers.credentials import AccountLease

    monkeypatch.setattr(
        cred_module, "acquire",
        lambda provider_id: AccountLease(credential_id=7, cookie="SESSION=stale", label="a"),
    )
    invalidated: list[int] = []
    monkeypatch.setattr(
        cred_module, "mark_cookie_invalid",
        lambda credential_id, reason: invalidated.append(credential_id),
    )

    async def ok_network(spec, transport):
        return {"stage": "network", "ok": True, "elapsed_ms": 1}

    async def denied(spec, transport, headers):
        return (
            {"stage": "auth", "ok": False, "elapsed_ms": 1, "status_code": 401, "message": "denied"},
            [],
        )

    monkeypatch.setattr(runtime_module, "_probe_network", ok_network)
    monkeypatch.setattr(runtime_module, "_probe_registry", denied)

    import asyncio

    result = asyncio.run(runtime_module.test_provider(_cookie_spec(3)))
    assert result["ok"] is False
    assert invalidated == [7]


def test_probe_reports_unusable_when_pool_is_empty(monkeypatch):
    from app.services.llm_providers import credentials as cred_module
    from app.services.llm_providers import runtime as runtime_module

    monkeypatch.setattr(cred_module, "acquire", lambda provider_id: None)

    import asyncio

    result = asyncio.run(runtime_module.test_provider(_cookie_spec(3)))
    assert result["ok"] is False
    assert "账号" in result["message"]


# ---------------------------------------------------------------------------
# 7. 标准 OpenAI 响应的消费方式
#    百通的响应体与 OpenAI 一致（reasoning_content / tool_calls / usage），
#    所以这一组测的不是「适配」而是「我们有没有把它读全」。
# ---------------------------------------------------------------------------


def _delta_chunk(content: str = "", reasoning: str | None = None, finish: str | None = None):
    import types

    delta = types.SimpleNamespace(
        content=content, reasoning_content=reasoning, tool_calls=None
    )
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(delta=delta, finish_reason=finish)], usage=None
    )


def _usage_only_chunk():
    """``stream_options.include_usage`` 的收尾帧：choices 为空，只有 usage。"""
    import types

    return types.SimpleNamespace(
        choices=[],
        usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )


def test_streaming_usage_reaches_the_caller(monkeypatch):
    """流式 token 统计不能恒为 0。

    ``include_usage`` 是适配器自己加的，上游按规范回一帧 ``choices: []`` +
    ``usage``。但网关的循环先 parse、拿到 None 就 continue，那帧 usage 读不到
    —— ``agent_usage_events`` 里存的正是这个值，等于所有流式对话的用量都是 0。
    """
    import asyncio

    from app.services.llm_providers import runtime as runtime_module
    from app.services.llm_providers.spec import ProviderSpec

    spec = ProviderSpec(
        name="A", slug="a", provider_type="openai_compatible",
        base_url="https://a.example.com/v1", model="m", api_key="k",
    )
    gateway = runtime_module.build_gateway(spec, max_tokens=64, timeout=5)

    async def fake_call(request):
        async def gen():
            yield _delta_chunk("ok", finish="stop")
            yield _usage_only_chunk()

        return gen()

    gateway.adapter.call = fake_call

    async def consume():
        from wuwei.llm import Message

        stream = await gateway.generate([Message(role="user", content="hi")], stream=True)
        return [chunk async for chunk in stream]

    chunks = asyncio.run(consume())
    assert "".join(chunk.content for chunk in chunks) == "ok"
    assert chunks[-1].usage == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


def test_usage_passthrough_keeps_stream_shape():
    """补 usage 不能顺手把空帧变成「有内容帧」，否则界面会冒出空 delta。"""
    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    adapter = HardenedOpenAIAdapter(api_key="k", model="m")

    assert adapter.parse_stream_chunk(_usage_only_chunk()) == {
        "content": "",
        "reasoning_content": "",
        "finish_reason": None,
    }
    # 正常帧原样透传
    assert adapter.parse_stream_chunk(_delta_chunk("hi", "think"))["content"] == "hi"


def _mock_client(handler):
    import httpx

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _stream_spec():
    from app.services.llm_providers.spec import ProviderSpec

    return ProviderSpec(
        name="网关", slug="gw", provider_type="enterprise_cookie",
        base_url="https://gw.example.com/agents/baitong", model="Qwen3.6-35B-A3B",
    )


def test_stream_probe_fails_when_endpoint_returns_html(monkeypatch):
    """打到 SPA 兜底页时要指出「base_url 少前缀」，而不是只说没收到数据。"""
    import asyncio

    import httpx

    from app.services.llm_providers import runtime as runtime_module

    def handler(request):
        return httpx.Response(
            200, text="<!doctype html><html></html>",
            headers={"content-type": "text/html"},
        )

    monkeypatch.setattr(
        runtime_module, "build_http_client",
        lambda transport, *, timeout: _mock_client(handler),
    )
    result = asyncio.run(
        runtime_module._probe_stream(
            _stream_spec(), runtime_module.resolve_transport({}), {}, model="Qwen3.6-35B-A3B"
        )
    )
    assert result["ok"] is False
    assert "SSE" in result["message"]
    assert "base_url" in (result["hint"] or "")


def test_stream_probe_reads_deltas(monkeypatch):
    import asyncio
    import json

    import httpx

    from app.services.llm_providers import runtime as runtime_module

    body = "".join(
        f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n"
        for piece in ("o", "k")
    ) + "data: [DONE]\n\n"

    def handler(request):
        return httpx.Response(
            200, text=body, headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        runtime_module, "build_http_client",
        lambda transport, *, timeout: _mock_client(handler),
    )
    result = asyncio.run(
        runtime_module._probe_stream(
            _stream_spec(), runtime_module.resolve_transport({}), {}, model="Qwen3.6-35B-A3B"
        )
    )
    assert result["ok"] is True
    assert result["content"] == "ok"
    assert result["frames"] == 2


# ---------------------------------------------------------------------------
# 8. 对 wuwei 三处缺陷的补强（adapter.py）
# ---------------------------------------------------------------------------


def _tool_delta_chunk(index: int = 0, call_id: str = "call_1", name: str = "noop"):
    import types

    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                delta=types.SimpleNamespace(
                    content=None,
                    reasoning_content=None,
                    tool_calls=[
                        types.SimpleNamespace(
                            index=index,
                            id=call_id,
                            function=types.SimpleNamespace(name=name, arguments="{}"),
                        )
                    ],
                ),
                finish_reason=None,
            )
        ],
        usage=None,
    )


def _finish_chunk(reason: str):
    import types

    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                delta=types.SimpleNamespace(
                    content=None, reasoning_content=None, tool_calls=None
                ),
                finish_reason=reason,
            )
        ],
        usage=None,
    )


def test_tool_calls_survive_nonstandard_finish_reason(monkeypatch):
    """收尾帧给 ``stop`` 而不是 ``tool_calls`` 时，工具调用不能被丢掉。

    wuwei 只在 ``finish_reason == "tool_calls"`` 时组装完整调用。有些网关收尾
    只给 ``stop``，模型「说要调工具」会被当成普通回答结束 —— 用户看到的是
    一段空回答，工具根本没执行。
    """
    import asyncio

    from wuwei.llm import Message

    from app.services.llm_providers.adapter import HardenedOpenAIAdapter
    from app.services.llm_providers.runtime import _new_gateway

    gateway = _new_gateway(
        {"provider": "openai", "api_key": "k", "model": "m", "retry": {"max_attempts": 1}}
    )
    gateway.adapter = HardenedOpenAIAdapter(api_key="k", model="m")

    async def fake_call(request):
        async def gen():
            yield _tool_delta_chunk()
            yield _finish_chunk("stop")  # 非标：不给 tool_calls

        return gen()

    gateway.adapter.call = fake_call

    async def consume():
        stream = await gateway.generate([Message(role="user", content="hi")], stream=True)
        return [chunk async for chunk in stream]

    chunks = asyncio.run(consume())
    complete = [c.tool_calls_complete for c in chunks if c.tool_calls_complete]
    assert complete, "工具调用被静默丢弃了"
    assert complete[0][0].function.name == "noop"


def test_standard_finish_reason_untouched():
    """标准形态必须原样透传，不能被补丁改写。"""
    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    adapter = HardenedOpenAIAdapter(api_key="k", model="m")
    adapter.parse_stream_chunk(_token_chunk("hi"))  # 普通文本帧
    data = adapter.parse_stream_chunk(_finish_chunk("stop"))
    assert data["finish_reason"] == "stop"


def _token_chunk(text: str):
    import types

    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                delta=types.SimpleNamespace(
                    content=text, reasoning_content=None, tool_calls=None
                ),
                finish_reason=None,
            )
        ],
        usage=None,
    )


def test_parse_response_tolerates_missing_usage():
    """兼容网关省略 usage 时不能整段失败。

    上游实现直接 ``raw_response.usage.prompt_tokens``，缺 usage 就
    AttributeError —— 一次正常的润色/PPT 请求会变成 500。
    """
    import types

    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    raw = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content="ok", reasoning_content=None, tool_calls=None),
                finish_reason="stop",
            )
        ],
        model="m",
        usage=None,
    )
    response = HardenedOpenAIAdapter(api_key="k", model="m").parse_response(raw)
    assert response.message.content == "ok"
    assert response.usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def test_parse_response_normalizes_unknown_finish_reason():
    """``finish_reason`` 是 Literal，上游给字面量之外的值会 ValidationError。"""
    import types

    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    raw = types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(content="ok", reasoning_content=None, tool_calls=None),
                finish_reason="insufficient_system_resource",
            )
        ],
        model="m",
        usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
    )
    assert HardenedOpenAIAdapter(api_key="k", model="m").parse_response(raw).finish_reason == "stop"


def _gateway_with_streams(scripts):
    """按脚本依次返回多次流式尝试的结果。"""
    from app.services.llm_providers.adapter import HardenedOpenAIAdapter
    from app.services.llm_providers.runtime import _new_gateway

    state = {"attempt": 0}
    gateway = _new_gateway(
        {"provider": "openai", "api_key": "k", "model": "m", "retry": {"max_attempts": 1}},
        )
    gateway.adapter = HardenedOpenAIAdapter(api_key="k", model="m")

    async def fake_call(request):
        index = min(state["attempt"], len(scripts) - 1)
        state["attempt"] += 1
        script = scripts[index]

        async def gen():
            for item in script:
                if isinstance(item, Exception):
                    raise item
                yield item

        return gen()

    gateway.adapter.call = fake_call
    return gateway, state


def test_stream_retries_when_nothing_emitted(monkeypatch):
    """连接层失败且尚未吐字时重试一次 —— 这是「网络抖动不用用户手动重发」的关键。"""
    import asyncio

    import openai
    from wuwei.llm import Message

    from app.services.llm_providers import runtime as runtime_module

    monkeypatch.setattr(
        runtime_module.get_settings(), "llm_stream_retry_attempts", 2, raising=False
    )
    gateway, state = _gateway_with_streams(
        [
            [openai.APIConnectionError(request=None)],  # type: ignore[arg-type]
            [_token_chunk("ok"), _finish_chunk("stop")],
        ]
    )

    async def consume():
        stream = await gateway.generate([Message(role="user", content="hi")], stream=True)
        return [chunk async for chunk in stream]

    chunks = asyncio.run(consume())
    assert state["attempt"] == 2
    assert "".join(c.content for c in chunks) == "ok"


def test_stream_does_not_retry_after_emitting(monkeypatch):
    """已经吐字后绝不重试：否则界面会出现重复内容，工具可能被执行两次。"""
    import asyncio

    import openai
    from wuwei.llm import Message

    from app.services.llm_providers import runtime as runtime_module

    monkeypatch.setattr(
        runtime_module.get_settings(), "llm_stream_retry_attempts", 3, raising=False
    )
    boom = openai.APIConnectionError(request=None)  # type: ignore[arg-type]
    gateway, state = _gateway_with_streams([[_token_chunk("半句"), boom]])

    async def consume():
        stream = await gateway.generate([Message(role="user", content="hi")], stream=True)
        seen = []
        async for chunk in stream:
            seen.append(chunk.content)
        return seen

    with pytest.raises(openai.APIConnectionError):
        asyncio.run(consume())
    assert state["attempt"] == 1


def test_stream_does_not_retry_client_errors(monkeypatch):
    """401 这类客户端错误重试只会烧配额，必须立刻抛出。"""
    import asyncio

    import httpx
    import openai
    from wuwei.llm import Message

    from app.services.llm_providers import runtime as runtime_module

    monkeypatch.setattr(
        runtime_module.get_settings(), "llm_stream_retry_attempts", 3, raising=False
    )

    response = httpx.Response(401, request=httpx.Request("POST", "https://x"))
    denied = openai.AuthenticationError("denied", response=response, body=None)
    gateway, state = _gateway_with_streams([[denied]])

    async def consume():
        stream = await gateway.generate([Message(role="user", content="hi")], stream=True)
        async for _ in stream:
            pass

    with pytest.raises(openai.AuthenticationError):
        asyncio.run(consume())
    assert state["attempt"] == 1


def test_adapter_does_not_leak_sdk_options_into_request_body():
    """``max_retries`` 是 SDK 参数，不能变成上游请求字段。

    ``OpenAIAdapter`` 把 ``**kwargs`` 全塞进 ``default_params`` 并展开进请求体，
    顺手把 SDK 选项写进去就会 ``TypeError: create() got an unexpected keyword
    argument``。这个坑实测踩过，用测试钉住。
    """
    from wuwei.llm import Message

    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    adapter = HardenedOpenAIAdapter(api_key="k", model="m", max_retries=0)
    request = adapter.build_request([Message(role="user", content="x")])
    assert "max_retries" not in request
    assert adapter.client.max_retries == 0
