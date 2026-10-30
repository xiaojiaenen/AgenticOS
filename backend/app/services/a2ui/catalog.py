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
    "Button": (("child", "action"), ("variant", "label"),
     "按钮。child 是 Text 组件 id；action 是**必填对象**，结构为 {'event':{'name':'submit'}}，event 这一层不能省"),
    "TextField": (("label",), ("value", "placeholder", "variant"), "文本输入。label 是标签文案；value 用 {'path':'/字段名'} 绑定；variant 可选 shortText/longText/number/obscured"),
    "CheckBox": (("label",), ("value",), "勾选框。value 是布尔值，用 {'path':'/字段名'} 绑定"),
    "ChoicePicker": (("options",), ("value",), "单选。options 是 [{label,value}] 数组"),
    "Slider": (("min", "max"), ("value",), "滑块"),
    "DateTimeInput": (("label",), ("value",), "日期时间输入"),
    "Tabs": (("tabs",), (), "标签页。tabs 是 [{title, content}] 数组——title 是标签名（字符串），content 是子组件 id"),
    "Modal": (("child",), ("label",), "弹窗容器。label 是标题文案，child 是内容组件 id"),
    "Image": (("url",), ("description",), "图片。url 是图片地址，description 是替代文本"),
    "Icon": (("name",), (), "图标"),
    "Video": (("url",), ("description", "posterUrl"), "视频。url 是视频地址，posterUrl 是封面图"),
    "AudioPlayer": (("url",), ("description",), "音频播放器。url 是音频地址"),
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
        "4. 不要用未列出的组件名。\n"
        "5. Button 必须带 action，写法 {'event':{'name':'动作名'}}；只写 {name:...} 或缺 action 都会渲染失败。"
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
            # 官方 schema：每个 tab 是 {title, content}，content 才是子组件 id。
            # 历史写法用 child，已废弃 —— 两个都收，兼容旧数据。
            if isinstance(tab, dict):
                for key in ("content", "child"):
                    if isinstance(tab.get(key), str):
                        refs.append(tab[key])
    return refs


# 官方 schema 允许的字段白名单（来自 @a2ui/web_core v1 basic_components.d.ts）。
# 模型多写的任何字段都会被前端 zod 判为 "Unrecognized key(s)"，整块界面报废，
# 所以服务端必须主动剔除，而不是指望模型只写允许的字段。
OFFICIAL_FIELDS: dict[str, frozenset[str]] = {
    "Text": frozenset({"text", "variant", "weight", "child", "children",
                       "align", "direction", "justify", "axis", "checks"}),
    "Column": frozenset({"children", "align", "direction", "justify", "axis",
                         "weight", "checks", "child", "trigger"}),
    "Row": frozenset({"children", "align", "direction", "justify", "axis",
                      "weight", "checks", "child", "trigger"}),
    "Card": frozenset({"child", "children", "variant", "weight", "checks",
                       "align", "direction", "justify", "axis", "trigger"}),
    "List": frozenset({"children", "child", "align", "direction", "justify",
                       "axis", "weight", "checks", "trigger"}),
    "Divider": frozenset({"weight", "checks", "axis", "variant"}),
    "Button": frozenset({"child", "action", "label", "variant", "weight",
                         "checks", "trigger", "align", "direction", "justify"}),
    "TextField": frozenset({"checks", "label", "value", "placeholder",
                            "variant", "weight"}),
    "CheckBox": frozenset({"checks", "displayStyle", "label", "options",
                           "value", "variant", "weight"}),
    "ChoicePicker": frozenset({"options", "value", "label", "variant",
                               "weight", "checks", "displayStyle"}),
    "Slider": frozenset({"min", "max", "value", "label", "step", "variant",
                         "weight", "checks"}),
    "DateTimeInput": frozenset({"label", "value", "variant", "weight",
                                "checks", "placeholder"}),
    "Tabs": frozenset({"tabs", "weight", "checks", "variant", "trigger"}),
    "Modal": frozenset({"action", "axis", "checks", "child", "content", "label",
                        "trigger", "variant", "weight"}),
    "Image": frozenset({"description", "fit", "name", "posterUrl", "url",
                        "variant", "weight", "checks"}),
    "Icon": frozenset({"name", "variant", "weight", "checks", "description"}),
    "Video": frozenset({"align", "child", "children", "description", "direction",
                        "justify", "posterUrl", "url", "weight", "checks", "fit"}),
    "AudioPlayer": frozenset({"align", "axis", "checks", "child", "children",
                              "content", "description", "direction", "justify",
                              "url", "weight", "trigger"}),
}

# 结构字段始终保留（id/component 由协议定义，不属于组件 schema）
STRUCTURAL_FIELDS = frozenset({"id", "component"})


def normalize_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """修补模型常见的字段名偏差并剔除非法字段，返回可渲染的组件树。

    线上踩过两个坑，本质相同 —— 后端目录与官方 schema 不一致：
      1. Tabs 每项写成 {label, child}，官方要 {title, content}
         → "tabs.0.title: Expected string, received undefined"
      2. TextField 写了 required，官方 schema 没有这个字段
         → "Unrecognized key(s) in object: 'required'"

    二者都会让整块界面渲染失败（对话本身不受影响，用户只看到"渲染坏了"）。
    与其指望 prompt 每次都写对，不如在服务端做确定性修补：
      - 别名改写：label/name → title、child/body → content、src → url 等
      - 字段白名单：不在官方 schema 里的键直接丢弃
    """
    if not isinstance(components, list):
        return components

    TAB_TITLE_ALIASES = ("title", "label", "name", "text")
    TAB_CONTENT_ALIASES = ("content", "child", "body", "component")

    # 组件级别名：模型习惯写法 → 官方字段名
    FIELD_ALIASES: dict[str, dict[str, str]] = {
        "Image": {"src": "url", "alt": "description", "title": "description"},
        "Video": {"src": "url", "alt": "description", "title": "description"},
        "AudioPlayer": {"src": "url", "alt": "description", "title": "description"},
        "Modal": {"title": "label", "text": "label"},
        "Icon": {"src": "name", "title": "description"},
        "TextField": {"placeholder": "placeholder"},
    }
    # 跨组件的通用别名：勾选框的 checked 就是 value
    CHECKBOX_ALIASES = {"checked": "value"}

    for comp in components:
        if not isinstance(comp, dict):
            continue
        name = comp.get("component")

        # --- Tabs 每项修补 ---
        if name == "Tabs":
            tabs = comp.get("tabs")
            if isinstance(tabs, list):
                fixed_tabs: list[Any] = []
                for tab in tabs:
                    if not isinstance(tab, dict):
                        fixed_tabs.append(tab)
                        continue
                    item = dict(tab)
                    if not isinstance(item.get("title"), (str, dict)):
                        for key in TAB_TITLE_ALIASES[1:]:
                            val = item.get(key)
                            if isinstance(val, (str, dict)) and val not in ("", None):
                                item["title"] = val
                                break
                    if not isinstance(item.get("content"), (str, dict)):
                        for key in TAB_CONTENT_ALIASES[1:]:
                            val = item.get(key)
                            if isinstance(val, (str, dict)) and val not in ("", None):
                                item["content"] = val
                                break
                    fixed_tabs.append(item)
                comp["tabs"] = fixed_tabs

        # --- 组件级别名改写（先补字段，再由白名单剔除旧键）---
        aliases = dict(FIELD_ALIASES.get(name, {}))
        if name == "CheckBox":
            aliases.update(CHECKBOX_ALIASES)
        for alias, official in aliases.items():
            if alias == official or alias not in comp:
                continue
            if comp.get(official) in (None, ""):
                comp[official] = comp[alias]

        # --- Button 的 action 兜底 ---
        # 官方 schema 要求 action 是 {event:{name}}。模型经常只写 {name:...}
        # 或干脆漏掉，前端就报 "action: Expected object, received undefined"。
        # 补一个通用的 submit 事件：A2UI 的 event 本来就会回传给智能体，
        # 语义上是「用户点了这个按钮」，不会伪造业务含义。
        if name == "Button":
            action = comp.get("action")
            if not isinstance(action, dict):
                comp["action"] = {"event": {"name": "submit"}}
            elif not isinstance(action.get("event"), dict):
                # {name:'submit'} 这种缺 event 层的写法 → 包一层
                evt_name = action.get("name")
                if isinstance(evt_name, str) and evt_name:
                    comp["action"] = {"event": {"name": evt_name}}
                else:
                    comp["action"] = {"event": {"name": "submit"}}

        # --- 白名单剔除：官方 schema 不认的键会让前端 zod 报错 ---
        allowed = OFFICIAL_FIELDS.get(name)
        if allowed:
            for key in [k for k in comp if k not in STRUCTURAL_FIELDS | allowed]:
                comp.pop(key, None)

    return components


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

        # Tabs 的逐项校验：title 缺失是最高频的渲染失败原因
        if name == "Tabs":
            tabs = comp.get("tabs")
            if not isinstance(tabs, list) or not tabs:
                raise A2uiValidationError(
                    f"组件「{cid}」(Tabs) 的 tabs 必须是非空数组"
                )
            for i, tab in enumerate(tabs):
                if not isinstance(tab, dict):
                    raise A2uiValidationError(
                        f"组件「{cid}」的 tabs[{i}] 不是对象"
                    )
                if not isinstance(tab.get("title"), (str, dict)):
                    raise A2uiValidationError(
                        f"组件「{cid}」的 tabs[{i}] 缺少 title（标签名，字符串）"
                    )
                if not isinstance(tab.get("content"), (str, dict)):
                    raise A2uiValidationError(
                        f"组件「{cid}」的 tabs[{i}] 缺少 content（子组件 id）"
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
