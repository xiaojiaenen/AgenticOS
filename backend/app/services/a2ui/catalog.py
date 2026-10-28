"""A2UI 组件目录（供智能体查询 + 服务端校验）。

上一版只开放了 simple_page / form_page 两个固定组合。这一版让智能体
**自由组合 18 个基础组件**，代价是它必须知道每个组件的字段。

设计取舍：

- **不把整份 JSON Schema 塞进 prompt** —— 18 个组件的完整 schema 约
  40KB，会挤占大量上下文，且模型看不过来。改成「紧凑目录」：每个组件
  一行，只列必填/常用字段。
- **校验仍在服务端** —— 模型可以写任何字段，但 ``validate_components``
  会拒绝未知组件名、缺 id、引用不存在的子组件、以及明显类型错误。
- **错误信息要能自我纠正** —— 校验失败时返回具体是哪个组件哪个字段，
  模型看到后能自己改，不需要人介入。
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 组件目录：紧凑描述，供 prompt 使用
# ---------------------------------------------------------------------------

# 每个组件：名称 → (必填字段, 常用可选字段, 一句话说明)
COMPONENT_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "Text": (("text",), ("variant",), "文本。variant 可选 h1/h2/h3/body/caption/label"),
    "Column": (("children",), (), "纵向排列子组件。children 是 id 数组"),
    "Row": (("children",), (), "横向排列子组件"),
    "Card": (("child",), (), "卡片容器，child 是单个子组件 id"),
    "List": (("children",), (), "列表"),
    "Divider": ((), (), "分隔线"),
    "Button": (("child",), ("action",), "按钮。child 通常是 Text 组件 id；action 形如 {name:'submit'}"),
    "TextField": (("label",), ("value", "required"), "文本输入。value 用 {path:'/字段名'} 绑定"),
    "CheckBox": (("label",), ("checked",), "勾选框。checked 用 {path:'/字段名'}"),
    "ChoicePicker": (("options",), ("value",), "单选。options 是 [{label,value}] 数组"),
    "Slider": (("min", "max"), ("value",), "滑块"),
    "DateTimeInput": (("label",), ("value",), "日期时间输入"),
    "Tabs": (("tabs",), (), "标签页。tabs 是 [{label, child}] 数组"),
    "Modal": (("child",), ("title",), "弹窗容器"),
    "Image": (("src",), ("alt",), "图片"),
    "Icon": (("name",), (), "图标"),
    "Video": (("src",), (), "视频"),
    "AudioPlayer": (("src",), (), "音频播放器"),
}

ALLOWED_COMPONENTS: frozenset[str] = frozenset(COMPONENT_SPECS)

# 需要在 updateDataModel 里给初值的组件字段（用于自动补数据模型）
_BINDING_FIELDS = ("value", "checked")


def catalog_prompt() -> str:
    """生成给模型看的紧凑组件目录（约 1.5KB，而不是 40KB 完整 schema）。"""
    lines = ["可用组件（18 个，只能用这些）："]
    for name, (required, optional, desc) in COMPONENT_SPECS.items():
        if required:
            req = f"必填 [{', '.join(required)}]"
        else:
            req = "无必填字段"
        opt = f" | 可选: {', '.join(optional)}" if optional else ""
        lines.append(f"- {name}: {req}{opt} —— {desc}")
    lines.append("")
    lines.append(
        "结构规则：\n"
        "1. 组件是扁平数组，每个有唯一 id；父子通过 id 引用（children/child/tabs），不能嵌套。\n"
        "2. 必须有一个 id='root' 的容器组件作为根。\n"
        "3. 输入类组件用 {path:'/字段名'} 绑定值，初值放 updateDataModel。\n"
        "4. 不要用未列出的组件名。"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


class A2uiValidationError(ValueError):
    """组件树校验失败。消息要能让模型自我纠正。"""


def _collect_child_refs(comp: dict[str, Any]) -> list[str]:
    """收集一个组件引用的所有子组件 id。"""
    refs: list[str] = []
    for key in ("children", "child"):
        val = comp.get(key)
        if isinstance(val, str):
            refs.append(val)
        elif isinstance(val, list):
            refs.extend(str(v) for v in val if isinstance(v, str))
    tabs = comp.get("tabs")
    if isinstance(tabs, list):
        for tab in tabs:
            if isinstance(tab, dict) and isinstance(tab.get("child"), str):
                refs.append(tab["child"])
    return refs


def validate_components(components: list[dict[str, Any]]) -> None:
    """校验组件树。失败抛 A2uiValidationError，消息指出具体问题。"""
    if not isinstance(components, list) or not components:
        raise A2uiValidationError("components 必须是非空数组")

    ids: set[str] = set()
    for idx, comp in enumerate(components):
        if not isinstance(comp, dict):
            raise A2uiValidationError(f"第 {idx} 项不是对象")
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise A2uiValidationError(f"第 {idx} 项缺少 id")
        if cid in ids:
            raise A2uiValidationError(f"id「{cid}」重复")
        ids.add(cid)

        name = comp.get("component")
        if name not in ALLOWED_COMPONENTS:
            raise A2uiValidationError(
                f"组件「{cid}」使用了不支持的 component「{name}」。"
                f"允许的组件：{', '.join(sorted(ALLOWED_COMPONENTS))}"
            )

        required, _, _ = COMPONENT_SPECS[name]
        for field in required:
            if field not in comp:
                raise A2uiValidationError(
                    f"组件「{cid}」({name}) 缺少必填字段「{field}」。"
                    f"{name} 需要：{', '.join(required)}"
                )

    # 根组件
    if "root" not in ids:
        raise A2uiValidationError("缺少 id='root' 的根容器组件")

    # 悬空引用
    for comp in components:
        for ref in _collect_child_refs(comp):
            if ref not in ids:
                raise A2uiValidationError(
                    f"组件「{comp['id']}」引用了不存在的子组件「{ref}」。"
                    f"已定义的 id：{', '.join(sorted(ids))}"
                )

    # 环检测：从 root 出发做 DFS，走到已访问节点说明有环
    children_of: dict[str, list[str]] = {c["id"]: _collect_child_refs(c) for c in components}
    visiting: set[str] = set()
    visited: set[str] = set()

    def _walk(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise A2uiValidationError(f"组件树存在环，路径回到「{node}」")
        visiting.add(node)
        for child in children_of.get(node, []):
            _walk(child)
        visiting.discard(node)
        visited.add(node)

    _walk("root")


def extract_initial_data(components: list[dict[str, Any]]) -> dict[str, Any]:
    """从组件里的 {path:'/x'} 绑定反推数据模型初值。

    模型经常忘记单独发 updateDataModel —— 这里自动补一份空初值，
    避免表单渲染时绑定到 undefined。
    """
    data: dict[str, Any] = {}
    for comp in components:
        for field in _BINDING_FIELDS:
            binding = comp.get(field)
            if isinstance(binding, dict) and isinstance(binding.get("path"), str):
                key = binding["path"].lstrip("/").split("/")[0]
                if key and key not in data:
                    if field == "checked":
                        data[key] = False
                    elif comp.get("component") == "Slider":
                        data[key] = comp.get("min", 0)
                    elif comp.get("component") == "ChoicePicker":
                        opts = comp.get("options") or []
                        first = opts[0] if opts else None
                        data[key] = (first or {}).get("value", "") if isinstance(first, dict) else ""
                    else:
                        data[key] = ""
    return data
