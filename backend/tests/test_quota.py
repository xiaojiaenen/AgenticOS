"""用量配额测试：超限拒绝 / 管理员豁免 / 关闭状态 / 边界。"""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

from app.core.timezone import app_now
from app.db.models import AgentUsageEventModel, UserModel
from app.db.session import create_db_session
from app.services.quota_service import (
    DailyQuotaExceeded,
    check_daily_quota,
    used_tokens_today,
)


@pytest.fixture()
def quota_user():
    """建一个普通用户，返回 (id, role)。"""
    import secrets

    with create_db_session() as db:
        user = UserModel(
            email=f"quota-{secrets.token_hex(4)}@example.test",
            name="Quota Test",
            password_hash=secrets.token_hex(32),
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        uid, role = user.id, user.role
    yield uid, role
    with create_db_session() as db:
        from sqlalchemy import delete

        db.execute(delete(AgentUsageEventModel).where(
            AgentUsageEventModel.user_id == uid))
        obj = db.get(UserModel, uid)
        if obj:
            db.delete(obj)
        db.commit()


def _add_usage(uid: int, tokens: int) -> None:
    with create_db_session() as db:
        db.add(AgentUsageEventModel(
            user_id=uid, session_id=f"q-{uid}",
            model_name="quota-test", response_mode="general",
            input_tokens=tokens // 2, output_tokens=tokens - tokens // 2,
        ))
        db.commit()


def _set_quota(value: str):
    os.environ["USER_DAILY_TOKEN_QUOTA"] = value
    from app.core.config import get_settings

    get_settings.cache_clear()


def _unset_quota():
    os.environ.pop("USER_DAILY_TOKEN_QUOTA", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


def test_quota_disabled_by_default(quota_user) -> None:
    """默认 0 = 不限制（不改变现有部署行为）。"""
    uid, role = quota_user
    _add_usage(uid, 10_000_000)
    _set_quota("0")
    try:
        info = check_daily_quota(uid, role=role)
        assert info["quota"] == 0
    finally:
        _unset_quota()


def test_quota_blocks_when_exceeded(quota_user) -> None:
    uid, role = quota_user
    _add_usage(uid, 5000)
    _set_quota("4000")
    try:
        with pytest.raises(DailyQuotaExceeded) as exc:
            check_daily_quota(uid, role=role)
        assert exc.value.used == 5000
        assert exc.value.quota == 4000
        # 错误信息要带已用/上限 —— 用户需要知道这是配额问题而非故障
        assert "5,000" in str(exc.value) and "4,000" in str(exc.value)
    finally:
        _unset_quota()


def test_quota_allows_under_limit(quota_user) -> None:
    uid, role = quota_user
    _add_usage(uid, 1000)
    _set_quota("4000")
    try:
        info = check_daily_quota(uid, role=role)
        assert info["used"] == 1000
    finally:
        _unset_quota()


def test_admin_never_limited(quota_user) -> None:
    """管理员做运维与验证，配额不能挡住自己。"""
    uid, _ = quota_user
    _add_usage(uid, 10_000_000)
    _set_quota("4000")
    try:
        info = check_daily_quota(uid, role="admin")
        assert info["quota"] == 4000
    finally:
        _unset_quota()


def test_quota_counts_only_today(quota_user) -> None:
    """昨日用量不计入今日配额（日配额语义）。"""
    uid, role = quota_user
    yesterday = app_now() - timedelta(days=1)
    with create_db_session() as db:
        db.add(AgentUsageEventModel(
            user_id=uid, session_id=f"q-y-{uid}",
            model_name="quota-test", response_mode="general",
            input_tokens=9000, output_tokens=1000,
            created_at=yesterday,
        ))
        db.commit()
    _set_quota("4000")
    try:
        info = check_daily_quota(uid, role=role)
        assert info["used"] == 0, "昨日用量不应计入今日"
    finally:
        _unset_quota()


def test_used_tokens_today_sums_io(quota_user) -> None:
    uid, _ = quota_user
    _add_usage(uid, 700)
    assert used_tokens_today(uid) == 700


def test_error_is_permission_error() -> None:
    """DailyQuotaExceeded 是 PermissionError 子类 —— 复用端点已有的 403 处理。"""
    assert issubclass(DailyQuotaExceeded, PermissionError)
