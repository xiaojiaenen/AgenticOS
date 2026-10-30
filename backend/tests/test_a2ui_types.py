"""枚举与类型约束回归测试（本轮两个线上报错）。

  Text.variant   收到 'label'  -> Invalid enum value
  ChoicePicker.value 收到 string -> Expected array

根因：目录没有写清枚举取值和字段类型，模型只能猜。
修复思路：目录写全枚举 + 服务端按官方 schema 做类型修正。
"""
from __future__ import annotations

import pytest

from app.services.a2ui.catalog import (
    COMPONENT_EXAMPLES,
    VALID_ENUMS,
    normalize_components,
    validate_components,
)


def _tree(inner: dict) -> list[dict]:
    return [
        {"id": "root", "component": "Column", "children": ["x"]},
        {"id": "x", **inner},
    ]


# ---------------------------------------------------------------------------
# Text.variant 枚举
# ---------------------------------------------------------------------------


def test_text_variant_label_dropped() -> None:
    """线上报错场景：variant='label' 不是合法枚举 -> 丢弃（走默认值）。"""
    comps = _tree({"component": "Text", "text": "标题", "variant": "label"})
    out = normalize_components(comps)
    assert "variant" not in out[1], "非法枚举应被丢弃，而不是猜一个近似值"


def test_text_valid_variants_kept() -> None:
    for v in ("h1", "h2", "h3", "h4", "h5", "caption", "body"):
        comps = _tree({"component": "Text", "text": "x", "variant": v})
        out = normalize_components(comps)
        assert out[1]["variant"] == v, f"{v} 是合法值，不该被删"


def test_text_variant_enum_complete() -> None:
    """枚举白名单必须包含官方全部 7 个值。"""
    allowed = VALID_ENUMS[("Text", "variant")]
    assert allowed == {"h1", "h2", "h3", "h4", "h5", "caption", "body"}


def test_catalog_documents_text_variants() -> None:
    """目录里要写全 variant 取值，模型才不会猜。"""
    from app.services.a2ui.catalog import catalog_prompt

    line = next(x for x in catalog_prompt().splitlines() if "Text:" in x)
    for v in ("h1", "caption", "body"):
        assert v in line, f"目录应列出 {v}：{line}"
    assert "没有 label" in line or "label" in line


# ---------------------------------------------------------------------------
# ChoicePicker.value 类型
# ---------------------------------------------------------------------------


def test_choicepicker_string_value_wrapped() -> None:
    """线上报错场景：value 是字符串 -> 包成数组。"""
    comps = _tree({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
        "value": "a",
    })
    out = normalize_components(comps)
    assert out[1]["value"] == ["a"], "字符串应包成单元素数组"


def test_choicepicker_list_value_normalized() -> None:
    comps = _tree({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}],
        "value": ["a", 1, None],
    })
    out = normalize_components(comps)
    assert out[1]["value"] == ["a", "1"], "应只保留可转字符串的标量"


def test_choicepicker_path_binding_untouched() -> None:
    comps = _tree({
        "component": "ChoicePicker",
        "options": [{"label": "A", "value": "a"}],
        "value": {"path": "/level"},
    })
    out = normalize_components(comps)
    assert out[1]["value"] == {"path": "/level"}, "路径绑定不该被数组化"


def test_catalog_documents_choicepicker_types() -> None:
    from app.services.a2ui.catalog import catalog_prompt

    line = next(x for x in catalog_prompt().splitlines() if "ChoicePicker:" in x)
    assert "数组" in line, f"应说明 value 是数组：{line}"
    assert "multipleSelection" in line, f"应列出 variant 取值：{line}"


# ---------------------------------------------------------------------------
# 其他类型修正
# ---------------------------------------------------------------------------


def test_slider_string_number_to_number() -> None:
    comps = _tree({"component": "Slider", "min": 0, "max": 100, "value": "42"})
    out = normalize_components(comps)
    assert out[1]["value"] == 42


def test_checkbox_string_bool_to_bool() -> None:
    comps = _tree({"component": "CheckBox", "label": "同意", "value": "true"})
    out = normalize_components(comps)
    assert out[1]["value"] is True


def test_text_array_text_joined() -> None:
    comps = _tree({"component": "Text", "text": ["第一行", "第二行"]})
    out = normalize_components(comps)
    assert out[1]["text"] == "第一行 第二行"


# ---------------------------------------------------------------------------
# 示例与真实 schema 一致
# ---------------------------------------------------------------------------


def test_examples_use_valid_enums() -> None:
    """示例里的枚举值必须合法 —— 模型会照抄示例。"""
    problems = []
    for name, example in COMPONENT_EXAMPLES.items():
        for (comp_name, field), allowed in VALID_ENUMS.items():
            if comp_name != name:
                continue
            val = example.get(field)
            if isinstance(val, str) and val not in allowed:
                problems.append(f"{name}.{field} = {val!r} 不在 {sorted(allowed)}")
    assert not problems, "\n".join(problems)


def test_modal_example_uses_trigger_content() -> None:
    """Modal 官方字段是 trigger/content，不是 child/label。"""
    ex = COMPONENT_EXAMPLES["Modal"]
    assert "trigger" in ex and "content" in ex
    assert "child" not in ex and "label" not in ex
