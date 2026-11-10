"""回归测试：管理端点必须设置用户上下文，否则企业网关凭据取不到。

来自内网真实故障：账号池里的凭据绑在具体 user_id 上（LDAP 联动时自动建的），
管理后台点「测试」/「发现模型」时 contextvar 是空的，`acquire()` 把这次调用
当成匿名上下文，只查共享池 → 报「账号池里没有可用账号」，而界面上账号明明是
active 的。修复是在三个端点开头加 `set_current_user_id(current_user.id)`。
"""
from __future__ import annotations

import inspect

import pytest


ENDPOINTS_REQUIRING_USER_CONTEXT = [
    "test_llm_provider",
    "test_provider_draft",
    "discover_provider_models",
    "login_provider",
]


@pytest.mark.parametrize("func_name", ENDPOINTS_REQUIRING_USER_CONTEXT)
def test_endpoint_sets_current_user_id(func_name):
    """这些端点必须显式设置 contextvar —— 靠调用链传递是不可靠的。"""
    from app.api.v1.endpoints import llm_providers as api

    func = getattr(api, func_name, None)
    assert func is not None, f"端点 {func_name} 不存在"

    source = inspect.getsource(func)
    assert "set_current_user_id(current_user.id)" in source, (
        f"{func_name} 缺少 set_current_user_id(current_user.id)："
        f"企业网关凭据将取不到（acquire 会退回共享池并报「没有可用账号」）"
    )


def test_acquire_returns_none_without_user_context():
    """没有用户上下文时，绑定到具体用户的凭据取不到 —— 这是故障的机制。"""
    from app.core.timezone import app_now
    from app.db.models import LlmProviderCredentialModel, LlmProviderModel
    from app.db.session import create_db_session
    from app.services.llm_providers import credentials as creds

    from app.core.data_path import set_current_user_id

    # 确保从干净的匿名上下文开始
    set_current_user_id(0)

    with create_db_session() as db:
        p = LlmProviderModel(
            name="ctx-test", slug="tmp-ctx-test", provider_type="enterprise_cookie",
            base_url="https://gw.example.com", enabled=True,
        )
        db.add(p)
        db.flush()
        pid = p.id
        row = LlmProviderCredentialModel(
            provider_id=pid, label="", username="u1",
            password_encrypted="", cookie_encrypted=creds.encrypt("SESSION=good"),
            login_url=None, status=creds.STATUS_ACTIVE, auto_refresh=True,
            priority=100, failure_count=0, disabled=False,
            expire_at=creds.default_cookie_expire_at(), user_id=1,
        )
        db.add(row)
        db.commit()

        try:
            assert creds.acquire(pid) is None, "匿名上下文不该拿到绑定凭据"

            set_current_user_id(1)
            lease = creds.acquire(pid)
            assert lease is not None, "设置用户后必须拿到绑定凭据"
            assert lease.cookie == "SESSION=good"
        finally:
            db.query(LlmProviderCredentialModel).filter(
                LlmProviderCredentialModel.provider_id == pid
            ).delete()
            db.query(LlmProviderModel).filter(LlmProviderModel.id == pid).delete()
            db.commit()
            set_current_user_id(0)


def test_acquire_falls_back_to_shared_pool_for_anonymous():
    """共享池（user_id 为空）在匿名上下文下仍应可取 —— 传统部署形态。"""
    from app.db.models import LlmProviderCredentialModel, LlmProviderModel
    from app.db.session import create_db_session
    from app.services.llm_providers import credentials as creds
    from app.core.data_path import set_current_user_id

    set_current_user_id(0)

    with create_db_session() as db:
        p = LlmProviderModel(
            name="shared-test", slug="tmp-shared-test", provider_type="enterprise_cookie",
            base_url="https://gw.example.com", enabled=True,
        )
        db.add(p)
        db.flush()
        pid = p.id
        row = LlmProviderCredentialModel(
            provider_id=pid, label="", username="shared",
            password_encrypted="", cookie_encrypted=creds.encrypt("SESSION=shared"),
            login_url=None, status=creds.STATUS_ACTIVE, auto_refresh=True,
            priority=100, failure_count=0, disabled=False,
            expire_at=creds.default_cookie_expire_at(), user_id=None,
        )
        db.add(row)
        db.commit()

        try:
            lease = creds.acquire(pid)
            assert lease is not None
            assert lease.cookie == "SESSION=shared"
        finally:
            db.query(LlmProviderCredentialModel).filter(
                LlmProviderCredentialModel.provider_id == pid
            ).delete()
            db.query(LlmProviderModel).filter(LlmProviderModel.id == pid).delete()
            db.commit()
