"""OpenAI 兼容网关测试（本地智能体路由；上游透传已下线）。"""

from __future__ import annotations


import pytest
from fastapi.testclient import TestClient

from app.api.v1.endpoints.openai_compat import (
    ChatCompletionRequest,
    _extract_user_content,
    _resolve_model_name,
    find_local_agent,
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

    from app.services.api_key_service import create_api_key

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


class TestUsageNormalization:
    """usage 必须从 agent 事件透传到 OpenAI 兼容响应。

    之前流式与非流式的 usage 都硬编码成 0 —— agent 侧的 "done" 事件明明带着
    真实 token 数，转发层却丢掉了。对外是 OpenAI 兼容端点，客户端据此计费，
    报 0 等于所有接入方的账单全错。
    """

    def test_accepts_agent_internal_field_names(self):
        from app.api.v1.endpoints.openai_compat import _normalize_usage

        assert _normalize_usage(
            {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        ) == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}

    def test_accepts_openai_field_names(self):
        """上游网关（百通等）有时直接给 OpenAI 那套字段名，也要认。"""
        from app.api.v1.endpoints.openai_compat import _normalize_usage

        assert _normalize_usage(
            {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}
        ) == {"prompt_tokens": 3, "completion_tokens": 7, "total_tokens": 10}

    def test_derives_total_when_missing(self):
        from app.api.v1.endpoints.openai_compat import _normalize_usage

        assert _normalize_usage({"input_tokens": 4, "output_tokens": 6}) == {
            "prompt_tokens": 4,
            "completion_tokens": 6,
            "total_tokens": 10,
        }

    def test_empty_usage_is_all_zero(self):
        from app.api.v1.endpoints.openai_compat import _normalize_usage

        assert _normalize_usage({}) == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def test_source_has_no_hardcoded_zero_usage(self):
        """静态守护：响应体里不能出现硬编码的 usage 0。

        这是本 bug 的根因 —— 修一次很容易，改回去也只需要复制一行。
        """
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints" / "openai_compat.py"
        text = source.read_text(encoding="utf-8")
        assert '"usage": {"prompt_tokens": 0' not in text


class TestLocalAgentRouting:
    def test_generic_model_is_local(self, api_key):
        _key, uid = api_key
        assert is_local_agent("gpt-4o", _user_by_id(uid)) is True

    def test_agent_slug_is_local(self, api_key):
        _key, uid = api_key
        assert is_local_agent("general", _user_by_id(uid)) is True

    def test_unknown_model_is_rejected(self, api_key):
        _key, uid = api_key
        assert is_local_agent("some-third-party-model", _user_by_id(uid)) is False

    def test_office_mode_is_local(self, api_key):
        """office 也是合法响应模式，漏在白名单外会被静默降级成 general。"""
        _key, uid = api_key
        profile = find_local_agent("office", _user_by_id(uid))
        assert profile is not None
        assert profile["response_mode"] == "office"

    def test_agent_name_resolves_to_own_response_mode(self, api_key):
        """填智能体名称时也要拿回它自己的 response_mode，而非一律 general。"""
        from app.services.agent_profile_service import AgentProfileService

        _key, uid = api_key
        user = _user_by_id(uid)
        items = AgentProfileService().list_user_agents(user).get("items", [])
        target = next((item for item in items if item.get("response_mode") != "general"), None)
        if target is None:
            pytest.skip("没有非 general 模式的内置智能体")
        for field in ("name", "slug"):
            resolved = find_local_agent(str(target[field]), user)
            assert resolved is not None
            assert resolved["response_mode"] == target["response_mode"]

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
        """接口只暴露本地智能体，但仍须返回合法的 OpenAI list 结构。"""
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