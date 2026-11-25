"""公开智能体聊天页鉴权边界测试（/public/agents/{slug}，PublicAgentChat 数据面）。

安全契约：
1. **只发不藏**：未发布 / disabled / 未知 slug → 404（信息不泄漏「存在但下线」）；
2. **公开面零鉴权**：info 端点无 token 可访问，但只吐 name/avatar/welcome/require_code，
   不吐 profile 配置全文；
3. **访问码门卫**：config 带 access_code 时，chat 无码/错码 → 403；对码才放行；
4. **widget.js 公开**：内容含 slug 占位替换。"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.models import AgentProfileModel, UserModel
from app.db.session import create_db_session
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def _mk_profile(suffix: str, *, published: bool, enabled: bool = True,
                slug: str | None = "pub-slug-{s}", config: str = "{}") -> tuple[int, int]:
    """建一个 owner + profile（不挂任何工具）。"""
    with create_db_session() as db:
        owner = UserModel(
            email=f"pub-owner-{suffix}@test.local",
            name="pub-owner",
            password_hash="test-only",
        )
        db.add(owner)
        db.flush()
        profile = AgentProfileModel(
            owner_id=owner.id,
            name=f"公开应用-{suffix}",
            slug=f"pub-app-{suffix}",
            description="",
            system_prompt="你是公开测试助手",
            response_mode="general",
            enabled=enabled,
            published=published,
            publish_slug=slug.format(s=suffix) if slug else None,
            publish_config_json=config,
        )
        db.add(profile)
        db.commit()
        return int(profile.id), int(owner.id)


def _cleanup(profile_id: int, owner_id: int):
    with create_db_session() as db:
        db.execute(delete(AgentProfileModel).where(AgentProfileModel.id == profile_id))
        db.execute(delete(UserModel).where(UserModel.id == owner_id))
        db.commit()


def test_unknown_slug_404(client):
    resp = client.get("/api/v1/public/agents/no-such-slug-xyz")
    assert resp.status_code == 404
    assert "不存在或已下线" in resp.json()["detail"]


def test_unpublished_profile_404_does_not_leak(client):
    """published=False 时同 slug 也 404 —— 不区分「存在但未发布」。"""
    suffix = uuid4().hex[:8]
    profile_id, owner_id = _mk_profile(suffix, published=False)
    try:
        resp = client.get(f"/api/v1/public/agents/pub-slug-{suffix}")
        assert resp.status_code == 404
    finally:
        _cleanup(profile_id, owner_id)


def test_disabled_profile_404(client):
    suffix = uuid4().hex[:8]
    profile_id, owner_id = _mk_profile(suffix, published=True, enabled=False)
    try:
        resp = client.get(f"/api/v1/public/agents/pub-slug-{suffix}")
        assert resp.status_code == 404
    finally:
        _cleanup(profile_id, owner_id)


def test_published_agent_info_public_no_auth(client):
    """已发布 → 无 token 可访问；返回字段是**白名单**（不吐配置全文）。"""
    suffix = uuid4().hex[:8]
    profile_id, owner_id = _mk_profile(
        suffix, published=True,
        config='{"title": "我的应用", "welcome": "你好！"}',
    )
    try:
        resp = client.get(f"/api/v1/public/agents/pub-slug-{suffix}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "我的应用"
        assert body["welcome"] == "你好！"
        assert body["require_code"] is False
        # 白名单外字段不泄漏
        assert "publish_config_json" not in body
        assert "access_code" not in body
    finally:
        _cleanup(profile_id, owner_id)


def test_access_code_gate_on_chat(client):
    """带访问码的公开应用：错码 403 / 对码通过门卫（进入引擎准备阶段后才因
    message/引擎状态报错，说明门卫已放行）。"""
    suffix = uuid4().hex[:8]
    profile_id, owner_id = _mk_profile(
        suffix, published=True,
        config='{"access_code": "letmein"}',
    )
    try:
        # info 提示需要访问码
        info = client.get(f"/api/v1/public/agents/pub-slug-{suffix}")
        assert info.json()["require_code"] is True

        # 无码
        r1 = client.post(
            f"/api/v1/public/agents/pub-slug-{suffix}/chat",
            json={"message": "hi"},
        )
        assert r1.status_code == 403

        # 错码
        r2 = client.post(
            f"/api/v1/public/agents/pub-slug-{suffix}/chat",
            json={"message": "hi", "access_code": "wrong"},
        )
        assert r2.status_code == 403

        # 对码 → 门卫放行（后续因 LLM 未配置/流式开始等非 403 错误）
        r3 = client.post(
            f"/api/v1/public/agents/pub-slug-{suffix}/chat",
            json={"message": "hi", "access_code": "letmein"},
        )
        assert r3.status_code != 403
    finally:
        _cleanup(profile_id, owner_id)


def test_chat_empty_message_422(client):
    suffix = uuid4().hex[:8]
    profile_id, owner_id = _mk_profile(suffix, published=True)
    try:
        resp = client.post(
            f"/api/v1/public/agents/pub-slug-{suffix}/chat",
            json={"message": "   "},
        )
        # 空白消息被双层拒绝：schemas min_length=1 → 400（全局 ValueError handler）；
        # 端点 strip 后兜底 422。两种都是拒绝，不能 200/403 门卫误放。
        assert resp.status_code in (400, 422)
    finally:
        _cleanup(profile_id, owner_id)


def test_widget_js_public_contains_slug(client):
    suffix = uuid4().hex[:8]
    profile_id, owner_id = _mk_profile(suffix, published=True)
    try:
        resp = client.get(f"/api/v1/public/agents/pub-slug-{suffix}/widget.js")
        assert resp.status_code == 200
        text = resp.text
        assert "pub-slug-" + suffix in text
        assert "__SLUG__" not in text  # 占位符被替换
    finally:
        _cleanup(profile_id, owner_id)
