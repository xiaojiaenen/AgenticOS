"""A2UI 消息构造器（后端侧）。

智能体不直接吐裸 JSON —— 那既容易格式错，也没法复用。这里提供一组
Python 辅助函数，把「要展示什么」翻译成 A2UI v0.9 的声明式消息。

设计要点：

- **邻接表模型**：A2UI 的组件是扁平列表，父子通过 ``id`` 引用
  （``children: ["a", "b"]``），不是嵌套结构。这正好适合流式生成 ——
  可以先发一批组件，再补一批。
- **只用 basic catalog 的 18 个组件**：Text / Column / Row / Card /
  Button / TextField / CheckBox / ChoicePicker / Slider / Divider /
  List / Tabs / Modal / Image / Icon / Video / AudioPlayer / DateTimeInput。
  不开放自定义组件，避免渲染层被模型随意扩张。
- **数据与结构分离**：``updateDataModel`` 只改数据，组件树不动。
  表单类界面改值时不重建整棵树。
"""

from __future__ import annotations

import uuid
from typing import Any

CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"
PROTOCOL_VERSION = "v0.9"

# 允许智能体使用的组件（basic catalog 全集）
ALLOWED_COMPONENTS: frozenset[str] = frozenset({
    "Text", "Image", "Icon", "Video", "AudioPlayer",
    "Row", "Column", "List", "Card", "Tabs", "Modal", "Divider",
    "Button", "TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput",
})


class A2uiBuildError(ValueError):
    """构造 A2UI 消息时的参数错误（面向开发者，不是用户操作问题）。"""


def new_surface_id(prefix: str = "s") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def create_surface(surface_id: str, *, send_data_model: bool = True) -> dict[str, Any]:
    """创建 surface。一个 surface = 一块独立渲染区域。"""
    return {
        "version": PROTOCOL_VERSION,
        "createSurface": {
            "surfaceId": surface_id,
            "catalogId": CATALOG_ID,
            "sendDataModel": send_data_model,
        },
    }


def update_components(surface_id: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    """下发/更新组件。``components`` 是邻接表列表（含 id 与 component 字段）。"""
    for comp in components:
        name = comp.get("component")
        if name not in ALLOWED_COMPONENTS:
            raise A2uiBuildError(
                f"不支持的组件「{name}」。允许的组件：{', '.join(sorted(ALLOWED_COMPONENTS))}"
            )
        if not comp.get("id"):
            raise A2uiBuildError(f"组件缺少 id：{comp}")
    return {
        "version": PROTOCOL_VERSION,
        "updateComponents": {"surfaceId": surface_id, "components": components},
    }


def update_data_model(surface_id: str, value: Any, path: str | None = None) -> dict[str, Any]:
    """更新数据模型。不传 path 表示整棵替换。"""
    payload: dict[str, Any] = {"surfaceId": surface_id, "value": value}
    if path:
        payload["path"] = path
    return {"version": PROTOCOL_VERSION, "updateDataModel": payload}


# ---------------------------------------------------------------------------
# 常用组合：把常见需求拼成完整消息序列
# ---------------------------------------------------------------------------


def _text(cid: str, text: Any, *, variant: str | None = None) -> dict[str, Any]:
    comp: dict[str, Any] = {"id": cid, "component": "Text", "text": text}
    if variant:
        comp["variant"] = variant
    return comp


def simple_page(
    title: str,
    body: Any,
    *,
    surface_id: str | None = None,
) -> list[dict[str, Any]]:
    """一屏「标题 + 正文」—— 最常用的展示形态。

    返回完整消息序列，可直接放进 SSE 的 ``a2ui`` 事件。
    """
    sid = surface_id or new_surface_id("page")
    return [
        create_surface(sid),
        update_components(
            sid,
            [
                {"id": "root", "component": "Column", "children": ["title", "body"]},
                _text("title", title, variant="h2"),
                _text("body", body),
            ],
        ),
    ]


def form_page(
    title: str,
    fields: list[dict[str, Any]],
    *,
    submit_label: str = "提交",
    surface_id: str | None = None,
) -> list[dict[str, Any]]:
    """表单页：标题 + N 个输入项 + 提交按钮。

    ``fields`` 每项形如::

        {"id": "name", "label": "姓名", "type": "text", "required": True}
        {"id": "level", "label": "级别", "type": "choice", "options": ["A", "B"]}
        {"id": "agree", "label": "同意", "type": "check"}

    数据与组件分离：初始值走 updateDataModel，改值不需要重建组件树。
    """
    sid = surface_id or new_surface_id("form")
    children: list[str] = ["title"]
    components: list[dict[str, Any]] = [_text("title", title, variant="h2")]
    initial: dict[str, Any] = {}

    for field in fields:
        fid = str(field.get("id") or "").strip()
        if not fid:
            raise A2uiBuildError("表单字段缺少 id")
        label = str(field.get("label") or fid)
        ftype = str(field.get("type") or "text")

        label_id = f"{fid}-label"
        components.append(_text(label_id, label))
        children.append(label_id)

        if ftype == "choice":
            options = list(field.get("options") or [])
            components.append({
                "id": fid,
                "component": "ChoicePicker",
                "options": [{"label": str(o), "value": str(o)} for o in options],
                "value": {"path": f"/{fid}"},
            })
            initial[fid] = field.get("default") or (str(options[0]) if options else "")
        elif ftype == "check":
            components.append({
                "id": fid,
                "component": "CheckBox",
                "label": label,
                "checked": {"path": f"/{fid}"},
            })
            initial[fid] = bool(field.get("default", False))
        elif ftype == "slider":
            components.append({
                "id": fid,
                "component": "Slider",
                "min": field.get("min", 0),
                "max": field.get("max", 100),
                "value": {"path": f"/{fid}"},
            })
            initial[fid] = field.get("default", 0)
        else:
            components.append({
                "id": fid,
                "component": "TextField",
                "label": label,
                "value": {"path": f"/{fid}"},
                "required": bool(field.get("required", False)),
            })
            initial[fid] = str(field.get("default") or "")

        children.append(fid)

    components.append({
        "id": "submit-label",
        "component": "Text",
        "text": submit_label,
    })
    components.append({
        "id": "submit",
        "component": "Button",
        "child": "submit-label",
        "action": {"name": "submit_form"},
    })
    children.append("submit")

    components.insert(0, {"id": "root", "component": "Column", "children": children})

    return [
        create_surface(sid),
        update_components(sid, components),
        update_data_model(sid, initial),
    ]
