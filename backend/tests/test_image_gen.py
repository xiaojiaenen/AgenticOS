"""生图工具测试：端点解析 / 未配置提示 / 错误分类。

重点不是「能不能真的生成图片」（那需要外部 API），而是：
- 未配置时给出可执行提示而不是崩
- 上游 404/401 能区分并给出针对性建议
- 产物路径落在会话工作区
"""
from __future__ import annotations

import pytest

from app.services.llm_providers import resolve_models


def test_size_presets_cover_common_cases() -> None:
    """三档尺寸要覆盖 PPT / 图标 / 手机端。"""
    from app.tools.image_gen_tools import _SIZE_PRESETS

    assert set(_SIZE_PRESETS) == {"square", "landscape", "portrait"}
    assert _SIZE_PRESETS["landscape"] == "1792x1024"
    assert _SIZE_PRESETS["square"] == "1024x1024"


@pytest.mark.asyncio
async def test_unconfigured_gives_actionable_hint(monkeypatch) -> None:
    """没配生图模型时，返回的是「去哪配」而不是报错。"""
    from wuwei.tools import ToolRegistry

    from app.tools.image_gen_tools import register_image_gen_tools

    registry = ToolRegistry()
    register_image_gen_tools(registry)
    tool = next(t for t in registry.list_tools() if t.name == "generate_image")

    # 强制解析返回 None（模拟未配置）
    monkeypatch.setattr(resolve_models, "resolve_image_endpoint", lambda db=None: None)

    result = await tool.handler(prompt="一只猫")
    assert "还没有配置生图模型" in result
    assert "AI 提供商" in result
    # 要给出替代方案
    assert "search_images" in result


@pytest.mark.asyncio
async def test_missing_api_key_is_reported(monkeypatch) -> None:
    """provider 绑了模型但没 Key 时要说清缺什么。"""
    from wuwei.tools import ToolRegistry

    from app.tools.image_gen_tools import register_image_gen_tools

    registry = ToolRegistry()
    register_image_gen_tools(registry)
    tool = next(t for t in registry.list_tools() if t.name == "generate_image")

    fake = resolve_models.EmbeddingEndpoint(
        base_url="https://x.test/v1", api_key="", model="dall-e-3",
        dimensions=0, source="provider:openai",
    )
    monkeypatch.setattr(resolve_models, "resolve_image_endpoint", lambda db=None: fake)

    result = await tool.handler(prompt="一只猫")
    assert "缺少 API Key" in result
    assert "dall-e-3" in result


@pytest.mark.asyncio
async def test_404_explains_endpoint_mismatch(monkeypatch, tmp_path) -> None:
    """上游 404 → 说明端点不支持生图，并给出当前端点。"""
    from wuwei.tools import ToolRegistry

    import app.tools.image_gen_tools as gen_mod
    from app.tools.image_gen_tools import register_image_gen_tools

    registry = ToolRegistry()
    register_image_gen_tools(registry)
    tool = next(t for t in registry.list_tools() if t.name == "generate_image")

    fake = resolve_models.EmbeddingEndpoint(
        base_url="https://gw.test/v1", api_key="sk-x", model="m",
        dimensions=0, source="provider:gw",
    )
    monkeypatch.setattr(resolve_models, "resolve_image_endpoint", lambda db=None: fake)
    # 注入工作区（真实调用时有会话上下文，测试里直接给一个目录）
    monkeypatch.setattr(gen_mod, "current_workspace_dir", lambda create=False: tmp_path)

    import httpx

    class _Resp:
        status_code = 404

    async def fake_post(self, *a, **kw):
        return _Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    result = await tool.handler(prompt="一只猫")
    assert "404" in result
    assert "https://gw.test/v1" in result
    assert "images/generations" in result


@pytest.mark.asyncio
async def test_no_workspace_gives_clear_message(monkeypatch) -> None:
    """没有会话上下文时，要说清原因而不是抛 TypeError。"""
    from wuwei.tools import ToolRegistry

    import app.tools.image_gen_tools as gen_mod
    from app.tools.image_gen_tools import register_image_gen_tools

    registry = ToolRegistry()
    register_image_gen_tools(registry)
    tool = next(t for t in registry.list_tools() if t.name == "generate_image")

    fake = resolve_models.EmbeddingEndpoint(
        base_url="https://gw.test/v1", api_key="sk-x", model="m",
        dimensions=0, source="provider:gw",
    )
    monkeypatch.setattr(resolve_models, "resolve_image_endpoint", lambda db=None: fake)
    monkeypatch.setattr(gen_mod, "current_workspace_dir", lambda create=False: None)

    result = await tool.handler(prompt="一只猫")
    assert "没有会话工作区" in result


@pytest.mark.asyncio
async def test_empty_prompt_rejected() -> None:
    from wuwei.tools import ToolRegistry

    from app.tools.image_gen_tools import register_image_gen_tools

    registry = ToolRegistry()
    register_image_gen_tools(registry)
    tool = next(t for t in registry.list_tools() if t.name == "generate_image")

    result = await tool.handler(prompt="   ")
    assert "prompt 不能为空" in result


def test_image_tool_registered_in_ppt_and_website() -> None:
    """生图工具应在需要配图的两个模式里可用。"""
    from app.services.tool_config_service import _discover_all_mode_tools

    discovered = _discover_all_mode_tools()
    assert "generate_image" in discovered.get("ppt", set())
    assert "generate_image" in discovered.get("website", set())
