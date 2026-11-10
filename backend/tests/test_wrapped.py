"""年度报告（Wrapped）+「AI 眼中的你」画像 + 邮件模板 + cron 回归。"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.core.timezone import APP_TIMEZONE
from app.db.models import AgentUsageEventModel, MemoryModel, MemoryPersonaModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.email_templates import build_wrapped
from app.services.task_queue import CRON_SCHEDULES
from app.services.wrapped_service import compute_wrapped, years_with_data


def _mk_user(email: str, role: str = "user") -> tuple[int, str]:
    with create_db_session() as db:
        u = UserModel(email=email, name="年度报告用户", password_hash=hash_password("pw-123456"),
                      role=role, is_active=True)
        db.add(u)
        db.commit()
        db.refresh(u)
        uid = u.id
    settings = get_settings()
    token = create_access_token(
        {"sub": str(uid), "email": email, "role": role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    return uid, token


def _auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _cleanup(uid: int) -> None:
    with create_db_session() as db:
        db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id == uid))
        db.execute(delete(MemoryModel).where(MemoryModel.user_id == uid))
        db.execute(delete(MemoryPersonaModel).where(MemoryPersonaModel.user_id == uid))
        db.execute(delete(UserModel).where(UserModel.id == uid))
        db.commit()


def _seed_usage(uid: int, year: int) -> None:
    with create_db_session() as db:
        for month, day, mode, tools in [
            (6, 1, "ppt", ["calc", "search"]),
            (6, 2, "ppt", ["calc"]),
            (6, 3, "website", ["build_website"]),
            (12, 31, "general", []),
        ]:
            db.add(AgentUsageEventModel(
                user_id=uid, session_id=f"s-{uid}-{month}-{day}", model_name="m",
                response_mode=mode, total_tokens=100, input_tokens=40, output_tokens=60,
                tool_calls=len(tools), tool_names_json=__import__("json").dumps(tools),
                llm_calls=1, latency_ms=3_600_000,
                created_at=datetime(year, month, day, 10, tzinfo=APP_TIMEZONE),
            ))
        db.commit()


def test_compute_wrapped_aggregates_year() -> None:
    uid, _ = _mk_user(f"wrap-{uuid4().hex[:8]}@example.com")
    try:
        _seed_usage(uid, 2025)
        with create_db_session() as db:
            w = compute_wrapped(db, uid, 2025)
        assert w["has_data"] is True
        assert w["total_runs"] == 4
        assert w["total_tokens"] == 400
        assert w["active_days"] == 4
        assert w["longest_streak"] == 3  # 6/1,6/2,6/3 连续
        assert w["persona"] == "PPT 大师"  # ppt 用最多
        assert w["top_mode"] == "ppt"
        assert {"name": "calc", "count": 2} in w["top_tools"]
        assert w["conversation_count"] == 4
        assert w["total_hours"] == 4.0
        # 别的年份无数据
        with create_db_session() as db:
            assert compute_wrapped(db, uid, 2024)["has_data"] is False
            assert years_with_data(db, uid) == [2025]
    finally:
        _cleanup(uid)


def test_wrapped_endpoint() -> None:
    uid, token = _mk_user(f"wrap-ep-{uuid4().hex[:8]}@example.com")
    try:
        _seed_usage(uid, 2025)
        with TestClient(app) as client:
            r = client.get("/api/v1/wrapped/2025", headers=_auth(token))
            assert r.status_code == 200, r.text
            assert r.json()["total_runs"] == 4
            r = client.get("/api/v1/wrapped/years", headers=_auth(token))
            assert 2025 in r.json()["years"]
            assert client.get("/api/v1/wrapped/1999", headers=_auth(token)).status_code == 422
    finally:
        _cleanup(uid)


def test_portrait_endpoint() -> None:
    uid, token = _mk_user(f"portrait-{uuid4().hex[:8]}@example.com")
    try:
        with create_db_session() as db:
            db.add(MemoryModel(user_id=uid, content="用户喜欢深色模式", memory_type="preference", layer="L1"))
            db.add(MemoryModel(user_id=uid, content="用户在做 AgenticOS", memory_type="fact", layer="L1"))
            db.add(MemoryPersonaModel(
                user_id=uid,
                identity_json='{"name":"小明","role":"工程师"}',
                preferences_json='{"likes":["深色模式"],"dislikes":[]}',
                tech_stack_json='["Python","FastAPI"]',
                goals_json='["上线反馈功能"]',
                projects_json='[{"name":"AgenticOS","status":"active","summary":"AI 平台"}]',
            ))
            db.commit()
        with TestClient(app) as client:
            r = client.get("/api/v1/memory/portrait", headers=_auth(token))
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["has_persona"] is True
            assert d["identity"]["name"] == "小明"
            assert d["atom_count"] == 2
            assert d["atoms_by_type"].get("preference") == 1
            assert "Python" in d["tech_stack"]
            assert d["projects"][0]["name"] == "AgenticOS"
            assert "认识你" in d["summary"]
    finally:
        _cleanup(uid)


def test_portrait_empty_user() -> None:
    uid, token = _mk_user(f"portrait-empty-{uuid4().hex[:8]}@example.com")
    try:
        with TestClient(app) as client:
            d = client.get("/api/v1/memory/portrait", headers=_auth(token)).json()
            assert d["has_persona"] is False
            assert d["atom_count"] == 0
            assert "还不怎么了解你" in d["summary"]
    finally:
        _cleanup(uid)


def test_build_wrapped_email_renders() -> None:
    stats = {
        "year": 2025, "user_name": "小明", "persona": "PPT 大师",
        "total_runs": 327, "active_days": 120, "total_tokens": 1234567,
        "longest_streak": 15, "top_mode_name": "PPT", "busiest_hour": 22,
        "top_tools": [{"name": "calc", "count": 48}],
    }
    html = build_wrapped(stats, "https://agenticos.example.com")
    assert "2025" in html and "小明" in html and "PPT 大师" in html
    assert "327" in html and "1,234,567" in html
    assert "https://agenticos.example.com/wrapped/2025" in html


def test_annual_wrapped_cron_registered() -> None:
    assert ("send_annual_wrapped_task", "0 8 1 1 *") in CRON_SCHEDULES


def test_dispatch_skips_without_notify_config() -> None:
    import asyncio

    from app.services.notification_service import dispatch_annual_wrapped

    # 测试环境未配置 NOTIFY_EMAIL_ADDRESS → 安全跳过，不发信
    result = asyncio.run(dispatch_annual_wrapped(2025, user_id=999999))
    assert result["sent"] == 0
    assert result.get("reason") == "notify_email_not_configured"
