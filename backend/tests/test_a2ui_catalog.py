"""A2UI 自由组合：组件目录 / 结构校验 / 自动补数据模型。"""
from __future__ import annotations

import pytest

from app.services.a2ui import builder, catalog


def test_catalog_covers_all_basic_components() -> None:
    expected = {
        "Text", "Image", "Icon", "Video", "AudioPlayer",
        "Row", "Column", "List", "Card", "Tabs", "Modal", "Divider",
        "Button", "TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput",
    }
    assert set(catalog.COMPONENT_SPECS) == expected
    assert catalog.ALLOWED_COMPONENTS == expected


def test_catalog_prompt_is_compact() -> None:
    """目录要能塞进 prompt —— 完整 JSON Schema 约 40KB，这里应 < 3KB。"""
    text = catalog.catalog_prompt()
    assert len(text) < 3000, f"组件目录太长（{len(text)} 字符），会挤占上下文"
    # 每个组件都出现在目录里
    for name in catalog.ALLOWED_COMPONENTS:
        assert f"- {name}:" in text


def test_validate_rejects_unknown_component() -> None:
    with pytest.raises(catalog.A2uiValidationError, match="不支持的 component"):
        catalog.validate_components([
            {"id": "root", "component": "Column", "children": ["x"]},
            {"id": "x", "component": "EvilIframe", "src": "http://evil"},
        ])


def test_validate_rejects_missing_required_field() -> None:
    with pytest.raises(catalog.A2uiValidationError, match="缺少必填字段"):
        catalog.validate_components([
            {"id": "root", "component": "Column", "children": ["t"]},
            {"id": "t", "component": "Text"},  # 缺 text
        ])


def test_validate_rejects_missing_root() -> None:
    with pytest.raises(catalog.A2uiValidationError, match="root"):
        catalog.validate_components([{"id": "t", "component": "Text", "text": "孤立"}])


def test_validate_rejects_duplicate_id() -> None:
    with pytest.raises(catalog.A2uiValidationError, match="重复"):
        catalog.validate_components([
            {"id": "root", "component": "Column", "children": ["t", "t2"]},
            {"id": "t", "component": "Text", "text": "a"},
            {"id": "t", "component": "Text", "text": "b"},
            {"id": "t2", "component": "Text", "text": "c"},
        ])


def test_validate_rejects_dangling_reference() -> None:
    with pytest.raises(catalog.A2uiValidationError, match="不存在的子组件"):
        catalog.validate_components([
            {"id": "root", "component": "Column", "children": ["ghost"]},
        ])


def test_validate_rejects_cycle() -> None:
    """环会让渲染器无限递归 —— 必须在服务端拦住。"""
    with pytest.raises(catalog.A2uiValidationError, match="环"):
        catalog.validate_components([
            {"id": "root", "component": "Column", "children": ["a"]},
            {"id": "a", "component": "Column", "children": ["b"]},
            {"id": "b", "component": "Column", "children": ["a"]},
        ])


def test_validate_accepts_complex_tree() -> None:
    """真实可用的复杂结构：卡片 + 行 + 标签页 + 输入绑定。

    Tabs 每项必须是 {title, content} —— 这是官方 @a2ui schema 的字段名。
    历史这里写的是 {label, child}：服务端能过，前端却报
    "tabs.0.title: Expected string, received undefined"，整块界面渲染失败。
    """
    catalog.validate_components([
        {"id": "root", "component": "Column", "children": ["title", "tabs", "form"]},
        {"id": "title", "component": "Text", "text": "仪表盘", "variant": "h1"},
        {"id": "tabs", "component": "Tabs", "tabs": [
            {"title": "概览", "content": "tab1"},
            {"title": "设置", "content": "tab2"},
        ]},
        {"id": "tab1", "component": "Row", "children": ["c1", "c2"]},
        {"id": "c1", "component": "Card", "child": "c1t"},
        {"id": "c1t", "component": "Text", "text": "完成率 92%"},
        {"id": "c2", "component": "Card", "child": "c2t"},
        {"id": "c2t", "component": "Text", "text": "阻塞 0"},
        {"id": "tab2", "component": "Column", "children": ["kw", "submit"]},
        {"id": "kw", "component": "TextField", "label": "关键词",
         "value": {"path": "/kw"}},
        {"id": "submit", "component": "Button", "child": "title"},
        {"id": "form", "component": "Divider"},
    ])


def test_extract_initial_data_from_bindings() -> None:
    """模型忘记发 updateDataModel 时，自动补初值，避免绑定到 undefined。"""
    comps = [
        {"id": "root", "component": "Column", "children": ["t", "c", "p", "s"]},
        {"id": "t", "component": "TextField", "label": "名称", "value": {"path": "/name"}},
        {"id": "c", "component": "CheckBox", "label": "同意", "checked": {"path": "/agree"}},
        {"id": "p", "component": "ChoicePicker", "options": [
            {"label": "高", "value": "high"}, {"label": "低", "value": "low"},
        ], "value": {"path": "/level"}},
        {"id": "s", "component": "Slider", "min": 0, "max": 10, "value": {"path": "/score"}},
    ]
    data = catalog.extract_initial_data(comps)
    assert data == {"name": "", "agree": False, "level": "high", "score": 0}


def test_builder_uses_catalog_validation() -> None:
    """builder 必须走 catalog 的完整校验，而不是只查组件名。"""
    # 悬空引用在 builder 层也要被拦住
    with pytest.raises(builder.A2uiBuildError, match="不存在的子组件"):
        builder.update_components("s1", [
            {"id": "root", "component": "Column", "children": ["nope"]},
        ])


def test_build_error_message_is_actionable() -> None:
    """错误信息要能让模型自己改 —— 必须指出具体组件与字段。"""
    try:
        builder.update_components("s1", [
            {"id": "root", "component": "Column", "children": ["t"]},
            {"id": "t", "component": "Text"},
        ])
    except builder.A2uiBuildError as exc:
        msg = str(exc)
        assert "t" in msg and "Text" in msg and "text" in msg, (
            f"错误信息不够具体，模型无法据此修正：{msg}"
        )
