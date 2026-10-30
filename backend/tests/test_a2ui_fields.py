"""A2UI 字段名/多余字段问题回归测试（在 Tabs 之外的全部同源 bug）。

线上踩过两个同源问题：
  1. Tabs 每项 {label, child}，官方要 {title, content}
  2. TextField 写了 required，官方 schema 无此字段
     → "root: Unrecognized key(s) in object: 'required'"

根因相同：后端组件目录与 @a2ui 官方 schema 不一致，模型照抄就渲染失败。
本文件守住"目录对齐"与"服务端修补"两条防线。
"""
from __future__ import annotations

import pytest

from app.services.a2ui.builder import A2uiBuildError, update_components
from app.services.a2ui.catalog import (
    OFFICIAL_FIELDS,
    catalog_prompt,
    normalize_components,
    validate_components,
)


def _tree(inner: dict, inner_id: str = "f1") -> list[dict]:
    return [
        {"id": "root", "component": "Column", "children": [inner_id]},
        {"id": inner_id, **inner},
    ]


# ---------------------------------------------------------------------------
# 防线一：目录里的字段名必须都在官方 schema 内
# ---------------------------------------------------------------------------


def test_catalog_fields_subset_of_official() -> None:
    """后端目录声明的每个字段都必须是官方 schema 允许的。

    这条是本类 bug 的总护栏：目录一旦写错字段，模型必然照抄。
    """
    from app.services.a2ui.catalog import COMPONENT_SPECS

    problems = []
    for name, (required, optional, _desc) in COMPONENT_SPECS.items():
        official = OFFICIAL_FIELDS.get(name)
        if official is None:
            continue
        declared = set(required) | set(optional)
        extra = declared - official
        if extra:
            problems.append(f"{name}: 多出 {sorted(extra)}")
    assert not problems, "目录字段超出官方 schema：\n" + "\n".join(problems)


def test_catalog_prompt_has_no_required_for_textfield() -> None:
    """TextField 不得再写 required —— 官方用 checks 表达校验。"""
    line = next(x for x in catalog_prompt().splitlines() if "TextField:" in x)
    assert "required" not in line, f"TextField 不该提 required：{line}"


def test_catalog_prompt_uses_url_for_media() -> None:
    """Image/Video/AudioPlayer 用 url，不是 src。"""
    for name in ("Image:", "Video:", "AudioPlayer:"):
        line = next(x for x in catalog_prompt().splitlines() if name in x)
        assert "url" in line, f"{name} 应说明 url：{line}"
        assert "src" not in line, f"{name} 不该提 src：{line}"


# ---------------------------------------------------------------------------
# 防线二：服务端剔除非法字段（本次报错的直接修复）
# ---------------------------------------------------------------------------


def test_drops_required_from_textfield() -> None:
    """线上报错场景：TextField 带 required → 必须被剔除，能正常渲染。"""
    comps = _tree({"component": "TextField", "label": "标题",
                   "value": {"path": "/t"}, "required": True})
    msg = update_components("s1", comps)
    field = msg["updateComponents"]["components"][1]
    assert "required" not in field
    assert field["label"] == "标题"


def test_drops_arbitrary_unknown_fields() -> None:
    comps = _tree({"component": "TextField", "label": "x",
                   "value": {"path": "/x"}, "foo": 1, "bar": [1, 2]})
    out = normalize_components(comps)
    assert "foo" not in out[1] and "bar" not in out[1]


def test_checkbox_checked_rewritten_to_value() -> None:
    """官方 CheckBox 用 value（布尔），没有 checked。"""
    comps = _tree({"component": "CheckBox", "label": "同意",
                   "checked": {"path": "/agree"}})
    out = normalize_components(comps)
    assert out[1]["value"] == {"path": "/agree"}
    assert "checked" not in out[1]


def test_image_src_rewritten_to_url() -> None:
    comps = _tree({"component": "Image", "src": "https://x/y.png",
                   "alt": "图"})
    out = normalize_components(comps)
    assert out[1]["url"] == "https://x/y.png"
    assert out[1]["description"] == "图"
    assert "src" not in out[1] and "alt" not in out[1]


def test_modal_title_rewritten_to_label() -> None:
    comps = [
        {"id": "root", "component": "Column", "children": ["m"]},
        {"id": "m", "component": "Modal", "child": "t", "title": "确认"},
        {"id": "t", "component": "Text", "text": "内容"},
    ]
    out = normalize_components(comps)
    assert out[1]["label"] == "确认"
    assert "title" not in out[1]


def test_video_and_audio_src_rewritten() -> None:
    for name in ("Video", "AudioPlayer"):
        comps = _tree({"component": name, "src": "https://x/a.mp4"})
        out = normalize_components(comps)
        assert out[1]["url"] == "https://x/a.mp4", name
        assert "src" not in out[1], name


def test_structural_fields_preserved() -> None:
    """id / component 是协议字段，不能被白名单误删。"""
    comps = _tree({"component": "Text", "text": "hi"})
    out = normalize_components(comps)
    assert out[1]["id"] == "f1"
    assert out[1]["component"] == "Text"


def test_valid_component_unchanged() -> None:
    """完全合法的组件不该被改动。"""
    comps = _tree({"component": "TextField", "label": "标题",
                   "value": {"path": "/t"}, "variant": "shortText"})
    before = [dict(c) for c in comps]
    out = normalize_components(comps)
    assert out == before


# ---------------------------------------------------------------------------
# 端到端
# ---------------------------------------------------------------------------


def test_update_components_accepts_required_field() -> None:
    """带 required 的 TextField 现在能正常下发（之前前端会报 unrecognized key）。"""
    comps = _tree({"component": "TextField", "label": "标题",
                   "value": {"path": "/t"}, "required": True})
    msg = update_components("s1", comps)  # 不抛即通过
    assert msg["updateComponents"]["surfaceId"] == "s1"


def test_required_field_does_not_break_validation() -> None:
    comps = _tree({"component": "TextField", "label": "标题",
                   "value": {"path": "/t"}, "required": True})
    normalize_components(comps)
    validate_components(comps)  # 不抛即通过


# ---------------------------------------------------------------------------
# Button.action 兜底（第三个线上报错）
#   action: Expected object, received undefined
# ---------------------------------------------------------------------------


def _btn_tree(action=None, with_text: bool = True) -> list[dict]:
    tree = [
        {"id": "root", "component": "Column", "children": ["btn_submit", "t1"]},
        {"id": "btn_submit", "component": "Button", "child": "t1"},
        {"id": "t1", "component": "Text", "text": "提交"},
    ]
    if action is not None:
        tree[1]["action"] = action
    return tree


def test_button_missing_action_gets_fallback() -> None:
    """线上报错场景：Button 完全没写 action。"""
    comps = _btn_tree()
    out = normalize_components(comps)
    action = out[1]["action"]
    assert isinstance(action, dict), "action 必须补成对象"
    assert isinstance(action.get("event"), dict)
    assert action["event"]["name"] == "submit"


def test_button_flat_name_wrapped_into_event() -> None:
    """目录旧示例 {name:'submit'} 缺 event 层 → 自动包一层。"""
    comps = _btn_tree({"name": "export_csv"})
    out = normalize_components(comps)
    assert out[1]["action"] == {"event": {"name": "export_csv"}}


def test_button_correct_action_untouched() -> None:
    """符合官方结构的不该被改动。"""
    good = {"event": {"name": "submit", "userMessage": "提交"}}
    comps = _btn_tree(good)
    out = normalize_components(comps)
    assert out[1]["action"] == good


def test_button_action_none_gets_fallback() -> None:
    comps = _btn_tree(None)
    comps[1]["action"] = None
    out = normalize_components(comps)
    assert out[1]["action"]["event"]["name"] == "submit"


def test_update_components_accepts_button_without_action() -> None:
    """端到端：缺 action 的按钮不再导致整块界面下发失败。"""
    msg = update_components("s1", _btn_tree())
    btn = msg["updateComponents"]["components"][1]
    assert btn["action"]["event"]["name"] == "submit"


def test_catalog_documents_event_structure() -> None:
    """目录必须写明 action 的 event 结构 —— 模型最容易漏这一层。"""
    prompt = catalog_prompt()
    line = next(x for x in prompt.splitlines() if "Button:" in x)
    assert "action" in line
    assert "event" in line, f"Button 说明应包含 event 结构：{line}"
