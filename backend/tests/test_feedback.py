"""反馈广场 + 在线状态 + 每用户分析 的端到端回归。"""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import (
    AgentUsageEventModel,
    FeedbackCommentModel,
    FeedbackIssueModel,
    FeedbackVoteModel,
    UserModel,
)
from app.db.session import create_db_session
from app.main import app


def _mk_user(email: str, role: str) -> tuple[int, str]:
    with create_db_session() as db:
        u = UserModel(email=email, name=email.split("@")[0], password_hash=hash_password("pw-123456"),
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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup(*uids: int) -> None:
    with create_db_session() as db:
        ids = db.scalars(select(FeedbackIssueModel.id).where(FeedbackIssueModel.user_id.in_(uids))).all()
        if ids:
            db.execute(delete(FeedbackVoteModel).where(FeedbackVoteModel.issue_id.in_(ids)))
            db.execute(delete(FeedbackCommentModel).where(FeedbackCommentModel.issue_id.in_(ids)))
            db.execute(delete(FeedbackIssueModel).where(FeedbackIssueModel.id.in_(ids)))
        db.execute(delete(AgentUsageEventModel).where(AgentUsageEventModel.user_id.in_(uids)))
        db.execute(delete(UserModel).where(UserModel.id.in_(uids)))
        db.commit()


def test_feedback_full_lifecycle() -> None:
    suffix = uuid4().hex[:8]
    admin_id, admin_tok = _mk_user(f"fb-admin-{suffix}@example.com", "admin")
    user_id, user_tok = _mk_user(f"fb-user-{suffix}@example.com", "user")
    other_id, other_tok = _mk_user(f"fb-other-{suffix}@example.com", "user")
    try:
        with TestClient(app) as client:
            # 创建公开 + 私密各一条
            r = client.post("/api/v1/feedback", headers=_auth(user_tok),
                            json={"type": "feature", "title": "希望支持深色模式", "body": "晚上太亮"})
            assert r.status_code == 201, r.text
            pub_id = r.json()["id"]
            r = client.post("/api/v1/feedback", headers=_auth(user_tok),
                            json={"type": "bug", "title": "私密问题", "visibility": "private"})
            priv_id = r.json()["id"]

            # 他人列表：能看到公开，看不到私密
            r = client.get("/api/v1/feedback", headers=_auth(other_tok))
            ids = {i["id"] for i in r.json()["items"]}
            assert pub_id in ids and priv_id not in ids
            # 管理员能看到私密
            r = client.get("/api/v1/admin/feedback", headers=_auth(admin_tok))
            assert priv_id in {i["id"] for i in r.json()["items"]}
            # 他人直接访问私密详情 → 404
            assert client.get(f"/api/v1/feedback/{priv_id}", headers=_auth(other_tok)).status_code == 404

            # 投票：toggle 两次回到 0
            r = client.post(f"/api/v1/feedback/{pub_id}/vote", headers=_auth(other_tok))
            assert r.json() == {"voted": True, "vote_count": 1}
            r = client.post(f"/api/v1/feedback/{pub_id}/vote", headers=_auth(other_tok))
            assert r.json() == {"voted": False, "vote_count": 0}
            client.post(f"/api/v1/feedback/{pub_id}/vote", headers=_auth(other_tok))

            # 评论
            r = client.post(f"/api/v1/feedback/{pub_id}/comments", headers=_auth(other_tok),
                            json={"body": "我也需要这个"})
            assert r.status_code == 201 and r.json()["is_official"] is False

            # 管理员官方回复 + 状态流转到 shipped
            r = client.post(f"/api/v1/admin/feedback/{pub_id}/reply", headers=_auth(admin_tok),
                            json={"body": "已排期，下个版本上线"})
            assert r.json()["is_official"] is True
            r = client.patch(f"/api/v1/admin/feedback/{pub_id}", headers=_auth(admin_tok),
                             json={"status": "shipped", "shipped_version": "v1.2.0", "priority": "high"})
            assert r.status_code == 200 and r.json()["status"] == "shipped"
            assert r.json()["shipped_version"] == "v1.2.0"

            # 详情含系统状态评论
            r = client.get(f"/api/v1/feedback/{pub_id}", headers=_auth(user_tok))
            comments = r.json()["comments"]
            assert any(c["is_system"] for c in comments)
            assert r.json()["issue"]["vote_count"] == 1

            # 统计
            r = client.get("/api/v1/feedback/stats", headers=_auth(admin_tok))
            assert r.json()["shipped"] >= 1

            # 普通用户不能改状态
            assert client.patch(f"/api/v1/admin/feedback/{pub_id}", headers=_auth(user_tok),
                                json={"status": "closed"}).status_code == 403

            # 管理员删除
            assert client.delete(f"/api/v1/admin/feedback/{priv_id}", headers=_auth(admin_tok)).status_code == 204
    finally:
        _cleanup(admin_id, user_id, other_id)


def test_presence_heartbeat_and_online() -> None:
    suffix = uuid4().hex[:8]
    admin_id, admin_tok = _mk_user(f"pr-admin-{suffix}@example.com", "admin")
    user_id, user_tok = _mk_user(f"pr-user-{suffix}@example.com", "user")
    try:
        with TestClient(app) as client:
            assert client.post("/api/v1/presence/heartbeat", headers=_auth(user_tok)).status_code == 200
            r = client.get("/api/v1/presence/online", headers=_auth(admin_tok))
            assert r.status_code == 200
            assert user_id in r.json()["user_ids"]
            # 普通用户不能看在线列表
            assert client.get("/api/v1/presence/online", headers=_auth(user_tok)).status_code == 403
            # 登出后离线
            client.post("/api/v1/auth/logout", headers=_auth(user_tok))
            r = client.get("/api/v1/presence/online", headers=_auth(admin_tok))
            assert user_id not in r.json()["user_ids"]
    finally:
        _cleanup(admin_id, user_id)


def test_user_analytics_aggregates_tools_and_modes() -> None:
    suffix = uuid4().hex[:8]
    admin_id, admin_tok = _mk_user(f"ua-admin-{suffix}@example.com", "admin")
    user_id, _ = _mk_user(f"ua-user-{suffix}@example.com", "user")
    try:
        with create_db_session() as db:
            db.add(AgentUsageEventModel(
                user_id=user_id, session_id=f"s-{suffix}", model_name="m", response_mode="ppt",
                total_tokens=100, tool_calls=2, tool_names_json='["calc","calc","search"]',
            ))
            db.commit()
        with TestClient(app) as client:
            r = client.get("/api/v1/admin/user-analytics", headers=_auth(admin_tok))
            assert r.status_code == 200
            row = next(x for x in r.json()["items"] if x["user_id"] == user_id)
            assert row["runs"] == 1 and row["total_tokens"] == 100
            assert {"name": "calc", "count": 2} in row["top_tools"]
            assert {"name": "ppt", "count": 1} in row["top_modes"]
            assert "online" in row

            r = client.get(f"/api/v1/admin/user-analytics/{user_id}", headers=_auth(admin_tok))
            assert r.status_code == 200
            assert r.json()["summary"]["runs"] == 1
            assert {"name": "calc", "value": 2} in r.json()["tool_distribution"]
            assert {"name": "ppt", "value": 1} in r.json()["mode_distribution"]
    finally:
        _cleanup(admin_id, user_id)
