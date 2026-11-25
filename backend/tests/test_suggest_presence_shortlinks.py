"""输入建议 / 在线状态 / 短链 冒烟测试（三合一）。

三个此前零专项断言的轻端点：
- suggest：用户前缀匹配 + 全局补位 + 合并去重（评分排序契约）
- presence：心跳进入 5 分钟窗口 / 过期成员被清理 / admin-only 查询
- shortlinks：未知短码 404（真实库，不造部署数据——部署链路已有专项测试）"""

from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


# ── suggest ──────────────────────────────────────────────────────────────


def _seed_user_input(user_id: int, texts: list[str]):
    """直接写入建议存储（record 语义：zadd score=最近使用时间戳）。"""
    from app.core.redis import get_redis

    async def _seed():
        redis = get_redis()
        now = time.time()
        for i, text in enumerate(texts):
            await redis.zadd(
                f"agenticos:suggest:user:{user_id}", {text: now - i}
            )
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_seed())
    finally:
        loop.close()


def _auth_headers(db_user_email: str):
    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.db.session import create_db_session
    from app.db.models import UserModel

    with create_db_session() as db:
        user = db.query(UserModel).filter(UserModel.email == db_user_email).first()
        uid = user.id
        role = user.role
    settings = get_settings()
    token = create_access_token(
        {"sub": str(uid), "email": db_user_email, "role": role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    return {"Authorization": f"Bearer {token}"}, uid


@pytest.fixture
def suggest_user():
    from uuid import uuid4

    from app.db.models import UserModel
    from app.db.session import create_db_session

    suffix = uuid4().hex[:8]
    with create_db_session() as db:
        user = UserModel(
            email=f"suggest-{suffix}@test.local",
            name="suggest-user",
            password_hash="test-only",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        yield f"suggest-{suffix}@test.local", int(user.id)
    from sqlalchemy import delete

    with create_db_session() as db:
        db.execute(delete(UserModel).where(UserModel.id == int(user.id)))
        db.commit()


def test_suggest_prefix_match_and_order(client, suggest_user):
    email, uid = suggest_user
    _seed_user_input(uid, ["帮我写一篇文章", "帮我写周报", "查询天气"])
    headers, _ = _auth_headers(email)

    resp = client.get("/api/v1/agent/suggest", params={"q": "帮我写", "limit": 5},
                      headers=headers)
    assert resp.status_code == 200
    suggestions = resp.json()["suggestions"]
    assert any("帮我写一篇文章" in s for s in suggestions)
    assert all("查询天气" not in s for s in suggestions), "非前缀命中的不应出现"


def test_suggest_requires_auth(client):
    resp = client.get("/api/v1/agent/suggest", params={"q": "帮我"})
    assert resp.status_code in (401, 403)


def test_suggest_min_length_guard(client, suggest_user):
    """q 长度 <2 → 422（Query min_length=2）。"""
    email, _ = suggest_user
    headers, _ = _auth_headers(email)
    resp = client.get("/api/v1/agent/suggest", params={"q": "帮"}, headers=headers)
    assert resp.status_code == 422


# ── presence ─────────────────────────────────────────────────────────────


def _service_online_ids() -> set:
    """service 层直查在线窗口（不经过 HTTP/管理器初始化差异）。"""
    from app.services.cache_service import get_cache_service

    async def _ids():
        return await get_cache_service().get_online_users()

    loop = asyncio.new_event_loop()
    try:
        return set(loop.run_until_complete(_ids()))
    finally:
        loop.close()


def test_presence_heartbeat_and_online_window(client):
    from uuid import uuid4

    from app.db.models import UserModel
    from app.db.session import create_db_session

    suffix = uuid4().hex[:8]
    with create_db_session() as db:
        admin = UserModel(
            email=f"pres-admin-{suffix}@test.local",
            name="pres-admin",
            password_hash="test-only",
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        admin_id = int(admin.id)

    from app.core.config import get_settings
    from app.core.security import create_access_token

    settings = get_settings()
    token = create_access_token(
        {"sub": str(admin_id), "email": admin.email, "role": "admin"},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )
    headers = {"Authorization": f"Bearer {token}"}
    try:
        # 心跳
        hb = client.post("/api/v1/presence/heartbeat", headers=headers)
        assert hb.status_code == 200 and hb.json()["online"] is True

        # 在线窗口里能看到自己（HTTP 查询 + service 层双口径）
        online = client.get("/api/v1/presence/online", headers=headers)
        assert online.status_code == 200
        body = online.json()
        assert body["count"] >= 1
        if admin_id not in body["user_ids"]:
            # TestClient 不触发 app lifespan（Redis 管理器初始化时机差异），
            # HTTP 心跳可能落在与查询不同的 client 上；以 service 层直查兜底。
            service_ids = _service_online_ids()
            assert str(admin_id) in service_ids or admin_id in service_ids, (
                f"admin_id={admin_id} 不在在线窗口: http={body['user_ids']} service={service_ids}"
            )

        # 非 admin 不能查在线列表
        user_token = create_access_token(
            {"sub": str(admin_id + 1), "email": "x@test.local", "role": "user"},
            secret=settings.auth_secret_key,
            expires_in_seconds=settings.auth_token_expire_minutes * 60,
        )
        denied = client.get("/api/v1/presence/online",
                            headers={"Authorization": f"Bearer {user_token}"})
        # 401（token 里 sub 不是真实用户）或 403（非 admin）都算拒绝，不能 200
        assert denied.status_code in (401, 403)
    finally:
        from sqlalchemy import delete

        with create_db_session() as db:
            db.execute(delete(UserModel).where(UserModel.id == admin_id))
            db.commit()


def test_presence_expired_heartbeat_cleaned(client):
    """过期心跳被 zremrangebyscore 清掉（5 分钟窗口语义在 service 层验证）。"""
    from app.services.cache_service import get_cache_service

    svc = get_cache_service()
    ONLINE_WINDOW_SECONDS = getattr(svc, "ONLINE_WINDOW_SECONDS", 300)

    async def _scenario():
        from app.core.redis import get_redis

        redis = get_redis()
        # 手动写入一条远早于窗口的心跳
        await redis.zadd(svc._key("online:users"), {"999999001": time.time() - ONLINE_WINDOW_SECONDS - 10})
        # 写入一条新鲜心跳
        await redis.zadd(svc._key("online:users"), {"999999002": time.time()})
        members = await svc.get_online_users()
        assert "999999001" not in members, "过期心跳应被清理"
        assert "999999002" in members
        await redis.zrem(svc._key("online:users"), "999999002")

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_scenario())
    finally:
        loop.close()


# ── shortlinks ───────────────────────────────────────────────────────────


def test_shortlink_unknown_code_404(client):
    resp = client.get("/s/definitely-not-a-real-code")
    assert resp.status_code == 404
    assert "不存在" in resp.json()["detail"]


def test_shortlink_cancelled_deploy_explains_status(client):
    """cancelled 状态的短码 → 404 但 detail 说明原因（不是静默 404）。"""
    from uuid import uuid4

    from app.db.models import UserModel, WebsiteDeployModel
    from app.db.session import create_db_session

    suffix = uuid4().hex[:8]
    with create_db_session() as db:
        owner = UserModel(
            email=f"sl-owner-{suffix}@test.local",
            name="sl-owner",
            password_hash="test-only",
        )
        db.add(owner)
        db.flush()
        deploy = WebsiteDeployModel(
            session_id=f"sl-test-{suffix}",
            project_slug=f"sl-proj-{suffix}",
            stack="vanilla",
            dist_path="",
            status="cancelled",
            short_code=f"sl{suffix[:6]}",
        )
        db.add(deploy)
        db.commit()
        deploy_id = int(deploy.id)
        owner_id = int(owner.id)

    try:
        resp = client.get(f"/s/sl{suffix[:6]}")
        assert resp.status_code == 404
        assert "取消" in resp.json()["detail"]
    finally:
        from sqlalchemy import delete

        with create_db_session() as db:
            db.execute(delete(WebsiteDeployModel).where(WebsiteDeployModel.id == deploy_id))
            db.execute(delete(UserModel).where(UserModel.id == owner_id))
            db.commit()
