"""提示词润色服务与接口测试（LLM 用假对象，不发真实请求）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.prompt_polish_service import (
    POLISH_SYSTEM_PROMPT,
    _clean_polished,
    build_polish_messages,
    polish_prompt,
)


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeLLM:
    """记录传入消息，按脚本返回内容。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.messages: list = []

    async def generate(self, messages, tools=None, stream: bool = False, **kwargs):
        self.messages = messages
        return _FakeResponse(self.reply)


@pytest.fixture
def auth_client():
    """创建一个带 token 的测试客户端（绕过登录限流）。"""
    from app.core.config import get_settings
    from app.core.security import create_access_token, hash_password
    from app.db.session import create_db_session
    from app.db.models import UserModel

    settings = get_settings()
    email = "polish-tester@example.com"
    with create_db_session() as db:
        user = db.query(UserModel).filter(UserModel.email == email).first()
        if user is None:
            user = UserModel(
                email=email,
                name="润色测试员",
                password_hash=hash_password("polish-test-123"),
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        token = create_access_token(
            {"sub": str(user.id), "email": user.email, "role": user.role},
            secret=settings.auth_secret_key,
            expires_in_seconds=3600,
        )
    return TestClient(app), {"Authorization": f"Bearer {token}"}


class TestCleanPolished:
    def test_strips_code_fence(self):
        assert _clean_polished("```markdown\n你好\n```") == "你好"

    def test_strips_label_prefix(self):
        assert _clean_polished("润色后的提示词：帮我分析数据") == "帮我分析数据"

    def test_collapses_blank_lines(self):
        assert _clean_polished("a\n\n\n\nb") == "a\n\nb"

    def test_truncates_overlong(self):
        assert len(_clean_polished("字" * 5000)) == 2000

    def test_handles_empty(self):
        assert _clean_polished("") == ""


class TestBuildPolishMessages:
    def test_system_prompt_forbids_fabrication(self):
        """提示词必须约束模型不得臆造需求。"""
        assert "不得改变或臆造用户意图" in POLISH_SYSTEM_PROMPT
        assert "待补充" in POLISH_SYSTEM_PROMPT

    def test_messages_include_original_text(self):
        messages = build_polish_messages("帮我看下上周数据")
        texts = [m.content for m in messages]
        assert any("帮我看下上周数据" in t for t in texts)
        assert len(messages) == 2


class TestPolishPrompt:
    @pytest.mark.anyio
    async def test_returns_polished_text(self, monkeypatch):
        llm = _FakeLLM("润色后的提示词：\n请分析上周数据\n\n要求：\n- 按渠道拆分")
        monkeypatch.setattr(
            "app.services.upstream.llm_factory.build_llm_for_user",
            lambda *a, **k: llm,
        )
        result = await polish_prompt("分析下上周数据 按渠道", user_id=1)
        assert result["changed"] is True
        assert result["original"] == "分析下上周数据 按渠道"
        assert result["polished"].startswith("请分析上周数据")
        # 用户原文确实传给了模型
        assert any("分析下上周数据" in m.content for m in llm.messages)

    @pytest.mark.anyio
    async def test_empty_input_skips_llm(self, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("不应调用 LLM")

        monkeypatch.setattr("app.services.upstream.llm_factory.build_llm_for_user", _boom)
        result = await polish_prompt("   ", user_id=1)
        assert result == {"polished": "", "changed": False, "original": ""}

    @pytest.mark.anyio
    async def test_input_truncated_to_limit(self, monkeypatch):
        llm = _FakeLLM("ok")
        monkeypatch.setattr(
            "app.services.upstream.llm_factory.build_llm_for_user",
            lambda *a, **k: llm,
        )
        result = await polish_prompt("字" * 5000, user_id=1)
        assert len(result["original"]) == 4000

    @pytest.mark.anyio
    async def test_llm_error_propagates(self, monkeypatch):
        def _raise(*a, **k):
            raise RuntimeError("upstream down")

        monkeypatch.setattr("app.services.upstream.llm_factory.build_llm_for_user", _raise)
        with pytest.raises(RuntimeError):
            await polish_prompt("你好", user_id=1)


class TestPolishEndpoint:
    def test_requires_auth(self):
        client = TestClient(app)
        resp = client.post("/api/v1/agent/polish-prompt", json={"text": "hi"})
        assert resp.status_code in (401, 403)

    def test_rejects_empty_text(self, auth_client):
        client, headers = auth_client
        resp = client.post("/api/v1/agent/polish-prompt", json={"text": ""}, headers=headers)
        assert resp.status_code == 422

    def test_success_returns_payload(self, auth_client, monkeypatch):
        client, headers = auth_client
        monkeypatch.setattr(
            "app.services.prompt_polish_service.polish_prompt",
            _async_fake({"polished": "润色结果", "original": "原文", "changed": True}),
        )
        resp = client.post("/api/v1/agent/polish-prompt", json={"text": "原文"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"polished": "润色结果", "original": "原文", "changed": True}

    def test_llm_failure_returns_502(self, auth_client, monkeypatch):
        client, headers = auth_client

        async def _boom(*a, **k):
            raise RuntimeError("upstream down")

        monkeypatch.setattr("app.services.prompt_polish_service.polish_prompt", _boom)
        resp = client.post("/api/v1/agent/polish-prompt", json={"text": "原文"}, headers=headers)
        assert resp.status_code == 502
        assert "润色失败" in resp.json()["detail"]


def _async_fake(payload):
    async def _fn(*args, **kwargs):
        return payload

    return _fn