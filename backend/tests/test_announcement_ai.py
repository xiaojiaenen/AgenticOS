"""公告 AI 生成测试（announcement_ai_service.py，fake-gateway 契约锁定）。

覆盖：正常生成（字段补全/默认值）/ markdown 与 html 双格式（html 危险脚本
拦截）/ 非 JSON 返回转可操作报错 / 网关异常转 ValueError / cta 可选字段清理。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.announcements import AnnouncementGenerateRequest
from app.services.announcement_ai_service import AnnouncementAIService


class _FakeResponse:
    def __init__(self, content: str):
        self.message = type("M", (), {"content": content})()


def _mock_gateway(content: str):
    gateway = AsyncMock()
    gateway.generate = AsyncMock(return_value=_FakeResponse(content))
    return gateway


def _req(**overrides) -> AnnouncementGenerateRequest:
    base = {"brief": "发布 v2.0 版本上线公告，重点讲双引擎架构升级", "content_format": "markdown"}
    base.update(overrides)
    return AnnouncementGenerateRequest(**base)


def _valid_ai_json(**overrides) -> str:
    payload = {
        "eyebrow": "产品动态",
        "title": "AgenticOS v2.0 正式发布",
        "subtitle": "双引擎架构升级",
        "body": "# 新版本上线\n\n- 双引擎架构\n- 性能提升",
        "cta_label": "立即体验",
        "cta_link": "https://example.com",
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_generate_draft_happy_path_fills_defaults():
    with patch(
        "app.services.announcement_ai_service.build_llm",
        return_value=_mock_gateway(_valid_ai_json()),
    ):
        draft = await AnnouncementAIService().generate_draft(_req())
    assert draft["title"] == "AgenticOS v2.0 正式发布"
    assert draft["eyebrow"] == "产品动态"
    assert draft["content_format"] == "markdown"
    assert draft["theme"] == "aurora"  # request 默认透传
    assert draft["cta_label"] == "立即体验"


@pytest.mark.asyncio
async def test_generate_html_body_blocks_dangerous_scripts():
    """html 格式下 AI 返回 <script> → 拦截（可操作报错，不落库）。"""
    content = _valid_ai_json(body='<p>正文</p><script>alert(1)</script>')
    with patch(
        "app.services.announcement_ai_service.build_llm",
        return_value=_mock_gateway(content),
    ):
        with pytest.raises(ValueError, match="不安全脚本"):
            await AnnouncementAIService().generate_draft(_req(content_format="html"))


@pytest.mark.asyncio
async def test_generate_html_body_allows_inline_style():
    content = _valid_ai_json(body='<p style="color:red">带内联样式正文</p>')
    with patch(
        "app.services.announcement_ai_service.build_llm",
        return_value=_mock_gateway(content),
    ):
        draft = await AnnouncementAIService().generate_draft(_req(content_format="html"))
    assert "style" in draft["body"]


@pytest.mark.asyncio
async def test_generate_non_json_becomes_actionable_error():
    with patch(
        "app.services.announcement_ai_service.build_llm",
        return_value=_mock_gateway("好的，我来帮您写公告……（自然语言而非 JSON）"),
    ):
        with pytest.raises(ValueError, match="格式异常"):
            await AnnouncementAIService().generate_draft(_req())


@pytest.mark.asyncio
async def test_generate_gateway_failure_becomes_value_error():
    gateway = AsyncMock()
    gateway.generate = AsyncMock(side_effect=RuntimeError("connection refused"))
    with patch(
        "app.services.announcement_ai_service.build_llm", return_value=gateway
    ):
        with pytest.raises(ValueError, match="AI 生成失败"):
            await AnnouncementAIService().generate_draft(_req())


@pytest.mark.asyncio
async def test_generate_empty_body_and_missing_fields_get_defaults():
    content = _valid_ai_json(body="", eyebrow=None, cta_label=None, cta_link=None)
    with patch(
        "app.services.announcement_ai_service.build_llm",
        return_value=_mock_gateway(content),
    ):
        draft = await AnnouncementAIService().generate_draft(_req())
    assert draft["eyebrow"] == "系统公告"  # 缺省兜底
    assert draft["cta_label"] is None and draft["cta_link"] is None
