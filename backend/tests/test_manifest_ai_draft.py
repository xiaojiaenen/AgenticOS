"""AI 生成 manifest 草稿（网站应用化 2.0：业务描述 → 结构化声明）。

覆盖：正常生成（mock 网关返回合法 manifest）→ Schema 校验兜底（mock 返回
权限过宽/字段非法的 manifest 时 400）→ 空描述拒绝 → JSON 解析失败转可操作报错。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.app_platform.manifest_ai import ManifestAIService

_VALID_MANIFEST = {
    "version": 1,
    "name": "客户反馈看板",
    "description": "收集客户反馈",
    "icon": "📊",
    "auth": {"mode": "builtin", "loginMethods": ["email"], "allowSignup": False,
             "roles": ["viewer", "editor", "admin"]},
    "models": [
        {
            "name": "feedback",
            "fields": [
                {"name": "title", "type": "string", "required": True},
                {"name": "ownerId", "type": "string", "ref": "user"},
            ],
            "permissions": {
                "read": ["owner", "role:admin"],
                "create": ["role:viewer", "role:editor", "role:admin"],
                "update": ["owner", "role:editor", "role:admin"],
                "delete": ["role:admin"],
            },
        }
    ],
    "capabilities": {"storage": {"mode": "platform"}, "outbound": {"allow": [], "mode": "deny"}},
    "routes": [{"path": "/", "entry": "index.html"}],
}


class _FakeResponse:
    def __init__(self, content: str):
        self.message = type("M", (), {"content": content})()


def _mock_gateway(content: str):
    gateway = AsyncMock()
    gateway.generate = AsyncMock(return_value=_FakeResponse(content))
    return gateway


@pytest.mark.asyncio
async def test_generate_draft_happy_path():
    content = json.dumps({"requirements_md": "# 需求", "manifest": _VALID_MANIFEST}, ensure_ascii=False)
    with patch(
        "app.services.app_platform.manifest_ai.build_llm", return_value=_mock_gateway(content)
    ):
        draft = await ManifestAIService().generate_draft("做一个客户反馈看板，作者能改自己的，管理员能删")
    assert draft["requirements_md"] == "# 需求"
    assert draft["manifest"]["name"] == "客户反馈看板"


@pytest.mark.asyncio
async def test_generate_draft_rejects_schema_violation():
    # 权限过宽 + 字段类型非法 → 机器可判校验必须拦下（不进审批队列）
    bad = json.loads(json.dumps(_VALID_MANIFEST))
    bad["models"][0]["permissions"]["read"] = ["*"]
    bad["models"][0]["fields"][0]["type"] = "varchar(255)"
    content = json.dumps({"requirements_md": "x", "manifest": bad}, ensure_ascii=False)
    with patch(
        "app.services.app_platform.manifest_ai.build_llm", return_value=_mock_gateway(content)
    ):
        with pytest.raises(ValueError, match="Schema 校验"):
            await ManifestAIService().generate_draft("描述")


@pytest.mark.asyncio
async def test_generate_draft_empty_brief_rejected():
    with pytest.raises(ValueError, match="业务描述不能为空"):
        await ManifestAIService().generate_draft("   ")


@pytest.mark.asyncio
async def test_generate_draft_non_json_converted_to_actionable_error():
    with patch(
        "app.services.app_platform.manifest_ai.build_llm",
        return_value=_mock_gateway("抱歉，我无法完成这个请求……"),
    ):
        with pytest.raises(ValueError, match="格式异常"):
            await ManifestAIService().generate_draft("描述")
