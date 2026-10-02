"""OpenAI 兼容网关测试（本地智能体分支 + 上游透传分支的路由选择）。"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.openai_compat import (
    ChatCompletionRequest,
    _extract_user_content,
    _resolve_model_name,
    is_local_agent,
    local_agent_slugs,
)
from app.core.security import hash_password
from app.db.models import UserModel
from app.db.session import create_db_session
from app.main import app


@pytest.fixture
def api_key():
    """创建管理员并返回可用的 API Key 明文（sk-agenticos-*）。"""
    with create_db_session() as db:
        user = db.query(UserModel).filter(
            UserModel.email == "openai-compat@example.com"
        ).first()
        if user is None:
            user = UserModel(
                email="openai-compat@example.com",
                name="兼容测试员",
                password_hash=hash_password("compat-test-123"),
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id, role, email = int(user.id), user.role, user.email

    from app.services.upstream.api_key_service import create_api_key

    created = create_api_key(user_id, name="openai-compat-test")
    return created["key"], user_id


def _user_by_id(user_id: int) -> UserModel:
    with create_db_session() as db:
        user = db.get(UserModel, user_id)
        assert user is not None
        db.expunge(user)
        return user


def _mode_names_are_local() -> None:
    """模式名恒为本地：general/ppt/website/email/bigdata。"""


@pytest.fixture
def client():
    return TestClient(app)


class TestHelpers:
    def test_picks_last_user_message(self):
        from app.api.v1.endpoints.openai_compat import ChatMessage

        messages = [
            ChatMessage(role="system", content="你是助手"),
            ChatMessage(role="user", content="第一个问题"),
            ChatMessage(role="assistant", content="回答"),
            ChatMessage(role="user", content="第二个问题"),
        ]
        assert _extract_user_content(messages) == "第二个问题"

    def test_falls_back_to_last_message(self):
        from app.api.v1.endpoints.openai_compat import ChatMessage

        messages = [ChatMessage(role="assistant", content="只有回答")]
        assert _extract_user_content(messages) == "只有回答"

    def test_generic_aliases_map_to_general(self):
        assert _resolve_model_name("gpt-4o") == "general"
        assert _resolve_model_name("GPT-4") == "general"
        assert _resolve_model_name("assistant") == "general"

    def test_explicit_mode_passthrough(self):
        assert _resolve_model_name("ppt") == "ppt"
        assert _resolve_model_name("website") == "website"


class TestLocalAgentRouting:
    def test_generic_model_is_local(self, api_key):
        _key, uid = api_key
        assert is_local_agent("gpt-4o", _user_by_id(uid)) is True

    def test_agent_slug_is_local(self, api_key):
        _key, uid = api_key
        assert is_local_agent("general", _user_by_id(uid)) is True

    def test_unknown_model_is_upstream(self, api_key):
        _key, uid = api_key
        assert is_local_agent("some-third-party-model", _user_by_id(uid)) is False

    def test_mode_names_always_local(self, api_key):
        _key, uid = api_key
        slugs = local_agent_slugs(_user_by_id(uid))
        for mode in ("general", "ppt", "website", "email", "bigdata"):
            assert mode in slugs
        assert "gpt-4o" in slugs
        assert "gpt-4o-mini" not in slugs

    def test_installed_agent_name_becomes_local(self, api_key):
        """安装过的智能体，其 slug/名称也应路由到本地。"""
        _key, uid = api_key
        user = _user_by_id(uid)
        from app.db.models import AgentProfileModel, UserInstalledAgentModel

        with create_db_session() as db:
            profile = db.query(AgentProfileModel).filter(
                AgentProfileModel.slug == "general"
            ).first()
            assert profile is not None
            db.add(UserInstalledAgentModel(user_id=uid, profile_id=profile.id))
            db.commit()
        try:
            assert is_local_agent("general", user) is True
        finally:
            with create_db_session() as db:
                db.query(UserInstalledAgentModel).filter(
                    UserInstalledAgentModel.user_id == uid
                ).delete()
                db.commit()


class TestGatewayRoutes:
    def test_models_requires_api_key(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 401
        assert resp.json()["error"]["type"] == "invalid_request_error"

    def test_models_returns_openai_shape_without_upstream(self, client, api_key):
        """上游不可达（无 Cookie）时，接口仍应返回合法的 OpenAI list 结构。"""
        key, _uid = api_key
        resp = client.get(
            "/v1/models", headers={"Authorization": f"Bearer {key}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        for item in data["data"]:
            assert item["object"] == "model"
            assert "id" in item and "created" in item and "owned_by" in item

    def test_models_lists_installed_agent(self, client, api_key):
        key, uid = api_key
        from app.db.models import AgentProfileModel, UserInstalledAgentModel

        with create_db_session() as db:
            profile = db.query(AgentProfileModel).filter(
                AgentProfileModel.slug == "general"
            ).first()
            assert profile is not None
            db.add(UserInstalledAgentModel(user_id=uid, profile_id=profile.id))
            db.commit()
        try:
            resp = client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
            ids = [item["id"] for item in resp.json()["data"]]
            assert "general" in ids
        finally:
            with create_db_session() as db:
                db.query(UserInstalledAgentModel).filter(
                    UserInstalledAgentModel.user_id == uid
                ).delete()
                db.commit()

    def test_chat_completions_rejects_bad_key(self, client):
        _ = None
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "general", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 401

    def test_chat_completions_empty_messages_rejected(self, client, api_key):
        key, _uid = api_key
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "general", "messages": []},
            headers={"Authorization": f"Bearer {key}"},
        )
        # 空 messages 由 pydantic 拒绝，或落到本地分支后 400
        # 空 messages：本地分支直接 400；若路由到上游则 502（Cookie 不可用）
        assert resp.status_code in (400, 422, 502)

    def test_payload_parses_agenticos_extensions(self):
        payload = ChatCompletionRequest(
            model="general",
            messages=[{"role": "user", "content": "hi"}],
            approval_mode="auto",
            plan_mode=True,
            session_id="s1",
        )
        assert payload.approval_mode == "auto"
        assert payload.plan_mode is True
        assert payload.stream is False

    def test_invalid_approval_mode_rejected(self):
        with pytest.raises(Exception):
            ChatCompletionRequest(
                model="general",
                messages=[{"role": "user", "content": "hi"}],
                approval_mode="yolo",
            )