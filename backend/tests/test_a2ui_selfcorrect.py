"""A2UI 自修正闭环测试：错误信息可照抄 / 重试指令 / 骨架示例。

目标不是逐个组件打补丁，而是让模型看到错误后**自己改对**。
本文件守住三件事：
  1. 校验错误必须带「该组件的正确写法」+ 整体骨架
  2. 工具返回的错误必须明确要求重试（而不是让模型改回纯文本）
  3. 连续失败会升级提示语
"""
from __future__ import annotations

import pathlib

import pytest

from app.services.a2ui.builder import A2uiBuildError, update_components
from app.services.a2ui.catalog import (
    COMPONENT_EXAMPLES,
    MINIMAL_SKELETON,
    OFFICIAL_FIELDS,
    error_with_example,
)


# ---------------------------------------------------------------------------
# 示例资产必须齐全且合法
# ---------------------------------------------------------------------------


def test_every_component_has_example() -> None:
    """每个可下发的组件都要有可照抄示例 —— 否则模型只能猜。"""
    from app.services.a2ui.catalog import ALLOWED_COMPONENTS

    missing = ALLOWED_COMPONENTS - set(COMPONENT_EXAMPLES)
    assert not missing, f"缺少示例的组件：{sorted(missing)}"


def test_examples_use_only_official_fields() -> None:
    """示例本身不能违规 —— 它会被模型原样照抄。"""
    problems = []
    for name, example in COMPONENT_EXAMPLES.items():
        allowed = OFFICIAL_FIELDS.get(name)
        if not allowed:
            continue
        extra = set(example) - allowed - {"id", "component"}
        if extra:
            problems.append(f"{name}: 多出 {sorted(extra)}")
    assert not problems, "示例含非法字段：\n" + "\n".join(problems)


def test_examples_pass_validation() -> None:
    """把每个示例单独包成合法树，必须能通过校验。"""
    for name, example in COMPONENT_EXAMPLES.items():
        tree = [
            {"id": "root", "component": "Column", "children": [example["id"]]},
            dict(example),
        ]
        # 容器类组件需要它的子组件存在
        extra = []
        for key in ("child",):
            ref = example.get(key)
            if isinstance(ref, str) and ref != "root":
                extra.append({"id": ref, "component": "Text", "text": "x"})
        if isinstance(example.get("children"), list):
            for ref in example["children"]:
                extra.append({"id": ref, "component": "Text", "text": "x"})
        for tab in example.get("tabs") or []:
            content = tab.get("content")
            if content:
                extra.append({"id": content, "component": "Text", "text": "x"})
        tree.extend(extra)
        # 去重 id
        seen, final = set(), []
        for c in tree:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            final.append(c)
        from app.services.a2ui.catalog import normalize_components, validate_components

        normalize_components(final)
        try:
            validate_components(final)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"{name} 的示例无法通过校验：{exc}")


def test_minimal_skeleton_is_valid() -> None:
    """整体骨架必须是合法组件树。"""
    from app.services.a2ui.catalog import normalize_components, validate_components

    tree = [dict(c) for c in MINIMAL_SKELETON]
    normalize_components(tree)
    validate_components(tree)


# ---------------------------------------------------------------------------
# 错误信息必须可照抄
# ---------------------------------------------------------------------------


def test_error_includes_component_example() -> None:
    msg = error_with_example("组件「b1」(Button) 缺少必填字段「action」", "Button")
    assert "action" in msg
    assert "event" in msg, "Button 示例必须含 event 层"
    assert "submit" in msg


def test_error_includes_skeleton() -> None:
    msg = error_with_example("随便什么错", "Button")
    assert "root" in msg, "必须给出整体骨架，模型据此修正结构"


def test_error_without_component_still_has_skeleton() -> None:
    msg = error_with_example("缺少 id='root' 的根容器组件", None)
    assert "root" in msg
    assert "Column" in msg


def test_unknown_component_error_readable() -> None:
    """未知组件名的错误要列出允许清单。"""
    with pytest.raises(Exception) as exc:
        update_components("s", [
            {"id": "root", "component": "Column", "children": ["x"]},
            {"id": "x", "component": "Whatever"},
        ])
    assert "不支持的 component" in str(exc.value)


# ---------------------------------------------------------------------------
# 重试指令
# ---------------------------------------------------------------------------


def _a2ui_module_source() -> str:
    """取 app.services.a2ui 包的源码文本。"""
    import app.services.a2ui as pkg

    return pathlib.Path(pkg.__file__).read_text(encoding="utf-8")


def test_tool_error_asks_for_retry() -> None:
    """工具返回的错误必须明确要求重试，而不是默许改回纯文本。"""
    src = _a2ui_module_source()
    assert "重新调用 render_components" in src
    assert "不要改用纯文本" in src


def test_failure_counter_escalates() -> None:
    """连续失败会升级提示语。"""
    src = _a2ui_module_source()
    assert "_bump_failure" in src
    assert "已连续失败多次" in src
