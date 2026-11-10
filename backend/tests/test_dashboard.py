from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.api.v1.endpoints.dashboard import _day_key
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AgentMessageModel, AgentSessionModel, AgentUsageEventModel, UserModel
from app.db.session import create_db_session
from app.main import app
from app.services.session_storage import dump_json

client = TestClient(app)


def test_dashboard_trend_uses_shanghai_calendar_day() -> None:
    assert _day_key(datetime(2026, 4, 28, 18, 30, tzinfo=timezone.utc)) == "2026-04-29"


def cleanup_records(*emails: str) -> None:
    with create_db_session() as db:
        users = db.scalars(select(UserModel).where(UserModel.email.in_(emails))).all()
        user_ids = [user.id for user in users]
        if user_ids:
            session_ids = db.scalars(select(AgentSessionModel.session_id).where(AgentSessionModel.user_id.in_(user_ids))).all()
            if session_ids:
                db.execute(delete(AgentMessageModel).where(AgentMessageModel.session_id.in_(session_ids)))
            db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id.in_(user_ids)))
            db.execute(delete(AgentSessionModel).where(AgentSessionModel.user_id.in_(user_ids)))
        db.execute(delete(UserModel).where(UserModel.email.in_(emails)))
        db.commit()


def create_admin_and_user(admin_email: str, user_email: str) -> tuple[str, int]:
    with create_db_session() as db:
        admin = UserModel(
            email=admin_email,
            name="Stats Admin",
            password_hash=hash_password("password-123"),
            role="admin",
            is_active=True,
        )
        user = UserModel(
            email=user_email,
            name="Stats User",
            password_hash=hash_password("password-123"),
            role="user",
            is_active=True,
        )
        db.add_all([admin, user])
        db.commit()
        db.refresh(admin)
        db.refresh(user)

    settings = get_settings()
    token = create_access_token(
        {"sub": str(admin.id), "email": admin.email, "role": admin.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    return token, user.id


def test_dashboard_stats_aggregate_usage() -> None:
    admin_email = f"stats-admin-{uuid4().hex}@example.com"
    user_email = f"stats-user-{uuid4().hex}@example.com"
    session_id = f"stats-session-{uuid4().hex[:8]}"

    try:
        with TestClient(app):
            token, user_id = create_admin_and_user(admin_email, user_email)
            with create_db_session() as db:
                db.add(
                    AgentSessionModel(
                        session_id=session_id,
                        user_id=user_id,
                        system_prompt="test",
                        metadata_json=dump_json({"user_id": user_id}),
                    )
                )
                db.add(
                    AgentUsageEventModel(
                        user_id=user_id,
                        session_id=session_id,
                        model_name="gpt-test",
                        response_mode="general",
                        input_tokens=120,
                        output_tokens=80,
                        total_tokens=200,
                        llm_calls=2,
                        tool_calls=1,
                        tool_names_json=dump_json(["time"]),
                        latency_ms=900,
                    )
                )
                db.add(
                    AgentMessageModel(
                        session_id=session_id,
                        message_json=dump_json({"role": "user", "content": "请帮我做一个统计图"}),
                    )
                )
                db.add(
                    AgentMessageModel(
                        session_id=session_id,
                        message_json=dump_json({
                            "role": "assistant",
                            "content": "我会先计算 **统计值**。",
                            "reasoning_content": "需要先确认计算方式。",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "calc",
                                        "arguments": {"expression": "1 + 1"},
                                    },
                                }
                            ],
                        }),
                    )
                )
                db.add(
                    AgentMessageModel(
                        session_id=session_id,
                        message_json=dump_json({"role": "tool", "tool_call_id": "call_1", "content": "2"}),
                    )
                )
                db.commit()

            response = client.get("/api/v1/dashboard/stats", headers={"Authorization": f"Bearer {token}"})

            assert response.status_code == 200
            payload = response.json()
            assert payload["summary"]["total_tokens"] >= 200
            assert payload["summary"]["llm_calls"] >= 2
            assert payload["summary"]["tool_calls"] >= 1
            assert any(item["name"] == "gpt-test" for item in payload["model_distribution"])
            # tool_distribution is a global top-8; on a shared DB historical tools
            # can outrank this test's single tool_names entry. Aggregation is still
            # verified via summary.tool_calls + model/user breakdown below.
            assert any(item["user_id"] == user_id and item["total_tokens"] >= 200 for item in payload["user_usage"])

            conversations_response = client.get(
                "/api/v1/dashboard/conversations",
                headers={"Authorization": f"Bearer {token}"},
                params={"search": "统计图"},
            )
            assert conversations_response.status_code == 200
            conversations_payload = conversations_response.json()
            assert conversations_payload["total"] >= 1
            matched = next(item for item in conversations_payload["items"] if item["session_id"] == session_id)
            assert matched["total_tokens"] == 200

            detail_response = client.get(
                f"/api/v1/dashboard/conversations/{session_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert detail_response.status_code == 200
            detail_payload = detail_response.json()
            assert detail_payload["session_id"] == session_id
            assert detail_payload["message_count"] >= 3
            assert detail_payload["created_at"].endswith("+08:00")
            assert detail_payload["updated_at"].endswith("+08:00")
            assert detail_payload["messages"][0]["created_at"].endswith("+08:00")
            assert detail_payload["messages"][0]["role"] == "user"
            assert "统计图" in detail_payload["messages"][0]["text"]
            assert detail_payload["messages"][1]["tool_calls"][0]["name"] == "calc"
            assert detail_payload["messages"][1]["tool_calls"][0]["arguments"]["expression"] == "1 + 1"
            assert detail_payload["messages"][1]["reasoning_text"] == "需要先确认计算方式。"
            assert detail_payload["messages"][2]["tool_results"][0]["tool_call_id"] == "call_1"
            assert detail_payload["messages"][2]["tool_results"][0]["result"] == "2"

            paged_detail_response = client.get(
                f"/api/v1/dashboard/conversations/{session_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"messages_offset": 1, "messages_limit": 1},
            )
            assert paged_detail_response.status_code == 200
            paged_payload = paged_detail_response.json()
            assert paged_payload["message_count"] >= 3
            assert len(paged_payload["messages"]) == 1
            assert paged_payload["messages_offset"] == 1
            assert paged_payload["messages"][0]["tool_calls"][0]["name"] == "calc"
    finally:
        cleanup_records(admin_email, user_email)


def test_dashboard_active_users_counts_window_usage_not_enabled_accounts() -> None:
    """「活跃用户」口径回归：只统计窗口内有使用记录的去重用户，
    启用但从未对话的账号不得计入（启用 ≠ 活跃）；
    窗口外的历史使用记录同样不得计入。"""
    admin_email = f"active-admin-{uuid4().hex}@example.com"
    used_email = f"active-used-{uuid4().hex}@example.com"
    unused_email = f"active-unused-{uuid4().hex}@example.com"
    session_id = f"active-session-{uuid4().hex[:8]}"
    stale_session_id = f"active-stale-{uuid4().hex[:8]}"

    try:
        # 先取基线：全量跑时其它测试可能留下账号，断言必须相对基线而非全局定值。
        with create_db_session() as db:
            baseline_users = int(db.scalar(select(func.count(UserModel.id))) or 0)
            baseline_active = int(
                db.scalar(
                    select(func.count(func.distinct(AgentUsageEventModel.user_id))).where(
                        AgentUsageEventModel.user_id.is_not(None),
                        AgentUsageEventModel.created_at >= datetime.now(timezone.utc) - timedelta(days=7),
                    )
                )
                or 0
            )

        with TestClient(app):
            token, used_user_id = create_admin_and_user(admin_email, used_email)
            with create_db_session() as db:
                # 第三个账号：启用但从不使用
                db.add(
                    UserModel(
                        email=unused_email,
                        name="Stats Unused",
                        password_hash=hash_password("password-123"),
                        role="user",
                        is_active=True,
                    )
                )
                db.commit()
                unused_id = db.scalar(select(UserModel.id).where(UserModel.email == unused_email))
                assert unused_id is not None

                db.add(
                    AgentSessionModel(
                        session_id=session_id,
                        user_id=used_user_id,
                        system_prompt="test",
                        metadata_json=dump_json({"user_id": used_user_id}),
                    )
                )
                db.add(
                    AgentUsageEventModel(
                        user_id=used_user_id,
                        session_id=session_id,
                        model_name="gpt-test",
                        response_mode="general",
                        input_tokens=10,
                        output_tokens=10,
                        total_tokens=20,
                        llm_calls=1,
                        tool_calls=0,
                        latency_ms=100,
                    )
                )
                # 窗口外的历史记录（40 天前）：不得把该用户算进 7 天活跃
                stale_user_id = int(unused_id)
                db.add(
                    AgentSessionModel(
                        session_id=stale_session_id,
                        user_id=stale_user_id,
                        system_prompt="test",
                        metadata_json=dump_json({"user_id": stale_user_id}),
                    )
                )
                db.add(
                    AgentUsageEventModel(
                        user_id=stale_user_id,
                        session_id=stale_session_id,
                        model_name="gpt-test",
                        response_mode="general",
                        input_tokens=10,
                        output_tokens=10,
                        total_tokens=20,
                        llm_calls=1,
                        tool_calls=0,
                        latency_ms=100,
                        created_at=datetime.now(timezone.utc) - timedelta(days=40),
                    )
                )
                db.commit()

            in_window = client.get(
                "/api/v1/dashboard/stats",
                headers={"Authorization": f"Bearer {token}"},
                params={"days": 7},
            )
            assert in_window.status_code == 200
            summary = in_window.json()["summary"]
            # 3 个账号全部启用，但窗口内只有 used 用户产生过记录。
            # 相对基线断言，不依赖数据库初始状态。
            assert summary["total_users"] == baseline_users + 3
            assert summary["active_users"] == baseline_active + 1

            wide_window = client.get(
                "/api/v1/dashboard/stats",
                headers={"Authorization": f"Bearer {token}"},
                params={"days": 60},
            )
            assert wide_window.status_code == 200
            wide_summary = wide_window.json()["summary"]
            # 60 天窗口能覆盖 40 天前的历史记录 → 比 7 天窗口多 1 个用户
            assert wide_summary["active_users"] == summary["active_users"] + 1
    finally:
        cleanup_records(admin_email, used_email, unused_email)
