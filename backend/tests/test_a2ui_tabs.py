"""A2UI Tabs 字段名问题回归测试。

线上报错：`Validation failed for component 'Tabs' (tabs):
tabs.0.title: Expected string, received undefined`

根因：A2UI 官方 schema 要求每项 `{title, content}`，但后端组件目录把
Tabs 写成了 `[{label, child}]`，模型照抄就渲染失败。修了三处：
1. 目录说明改正；
2. normalize_components 做确定性修补（label→title / child→content）；
3. validate_components 对 Tabs 逐项校验，提前报出可读错误。
"""
from __future__ import annotations

import pytest

from app.services.a2ui.builder import A2uiBuildError, update_components
from app.services.a2ui.catalog import (
    A2uiValidationError,
    catalog_prompt,
    normalize_components,
    validate_components,
)


def _tabs_tree(tabs: list[dict]) -> list[dict]:
    return [
        {"id": "root", "component": "Column", "children": ["tabs1"]},
        {"id": "tabs1", "component": "Tabs", "tabs": tabs},
        {"id": "p1", "component": "Text", "text": "第一页"},
        {"id": "p2", "component": "Text", "text": "第二页"},
    ]


# ---------------------------------------------------------------------------
# 目录说明必须与官方 schema 一致
# ---------------------------------------------------------------------------


def test_catalog_prompt_documents_title_content() -> None:
    """目录里写的字段名必须是官方 schema 的字段名。

    这条测试是本 bug 的护栏：目录写错 label/child，模型就会照抄。
    """
    prompt = catalog_prompt()
    tabs_line = next(line for line in prompt.splitlines() if "Tabs:" in line)
    assert "title" in tabs_line, f"Tabs 目录应说明 title 字段，实际：{tabs_line}"
    assert "content" in tabs_line, f"Tabs 目录应说明 content 字段，实际：{tabs_line}"
    assert "label" not in tabs_line, "Tabs 不该再提 label（官方 schema 无此字段）"
    assert "child" not in tabs_line, "Tabs 不该再提 child（官方 schema 用 content）"


# ---------------------------------------------------------------------------
# 修补：模型写错字段名也能渲染
# ---------------------------------------------------------------------------


def test_normalize_label_child_to_title_content() -> None:
    """最常见的错误写法：[{label, child}] → [{title, content}]。"""
    comps = _tabs_tree([
        {"label": "概览", "child": "p1"},
        {"label": "详情", "child": "p2"},
    ])
    out = normalize_components(comps)
    tabs = out[1]["tabs"]
    assert tabs[0] == {"label": "概览", "child": "p1", "title": "概览", "content": "p1"}
    assert tabs[1]["title"] == "详情"
    assert tabs[1]["content"] == "p2"


def test_normalize_partial_title_child() -> None:
    """半对半错：title 对、child 错。"""
    comps = _tabs_tree([{"title": "概览", "child": "p1"}])
    tabs = normalize_components(comps)[1]["tabs"]
    assert tabs[0]["title"] == "概览"
    assert tabs[0]["content"] == "p1"


def test_normalize_keeps_valid_tabs_untouched() -> None:
    comps = _tabs_tree([{"title": "概览", "content": "p1"}])
    tabs = normalize_components(comps)[1]["tabs"]
    assert tabs[0] == {"title": "概览", "content": "p1"}


def test_normalize_ignores_non_tabs_components() -> None:
    comps = [
        {"id": "root", "component": "Column", "children": ["t1"]},
        {"id": "t1", "component": "Text", "text": "hi"},
    ]
    before = [dict(c) for c in comps]
    normalize_components(comps)
    assert comps == before


def test_normalize_allows_path_binding_title() -> None:
    """title 也可以是 {path:...} 绑定，不该被当成缺失。"""
    comps = _tabs_tree([{"title": {"path": "/name"}, "content": "p1"}])
    tabs = normalize_components(comps)[1]["tabs"]
    assert tabs[0]["title"] == {"path": "/name"}


# ---------------------------------------------------------------------------
# 校验：修不好的要给出可读错误，而不是让前端报 zod 错
# ---------------------------------------------------------------------------


def test_validate_rejects_missing_title() -> None:
    comps = _tabs_tree([{"content": "p1"}])
    normalize_components(comps)  # 没有 label 可修补
    with pytest.raises(A2uiValidationError) as exc:
        validate_components(comps)
    msg = str(exc.value)
    assert "title" in msg and "tabs[0]" in msg, f"错误信息要指出位置与字段：{msg}"


def test_validate_rejects_missing_content() -> None:
    comps = _tabs_tree([{"title": "概览"}])
    normalize_components(comps)
    with pytest.raises(A2uiValidationError) as exc:
        validate_components(comps)
    assert "content" in str(exc.value)


def test_validate_rejects_empty_tabs() -> None:
    comps = _tabs_tree([])
    with pytest.raises(A2uiValidationError) as exc:
        validate_components(comps)
    assert "非空数组" in str(exc.value)


def test_validate_accepts_normalized_tabs() -> None:
    comps = _tabs_tree([{"label": "概览", "child": "p1"}])
    normalize_components(comps)
    validate_components(comps)  # 不抛即通过


# ---------------------------------------------------------------------------
# 端到端：update_components 会自动修补，不再抛错
# ---------------------------------------------------------------------------


def test_update_components_repairs_bad_tabs() -> None:
    """线上报错场景：模型下发 label/child，builder 应自动修好。"""
    comps = _tabs_tree([
        {"label": "概览", "child": "p1"},
        {"label": "详情", "child": "p2"},
    ])
    msg = update_components("s1", comps)
    tabs = msg["updateComponents"]["components"][1]["tabs"]
    assert tabs[0]["title"] == "概览"
    assert tabs[0]["content"] == "p1"


def test_update_components_still_rejects_unfixable() -> None:
    """缺 title 且无 label 可救 —— 抛 A2uiBuildError，带可读原因。"""
    comps = _tabs_tree([{"content": "p1"}])
    with pytest.raises(A2uiBuildError) as exc:
        update_components("s1", comps)
    assert "title" in str(exc.value)


def test_dangling_content_ref_detected() -> None:
    """content 指向不存在的组件，必须能查出来。"""
    comps = _tabs_tree([{"label": "概览", "child": "nope"}])
    normalize_components(comps)
    with pytest.raises(A2uiValidationError) as exc:
        validate_components(comps)
    assert "nope" in str(exc.value)
