"""A2UI 服务：智能体可调用的界面生成工具 + SSE 事件约定。

为什么做成工具而不是让模型直接吐 JSON：模型吐 JSON 有三个问题 ——
格式容易错、组件名容易编、没有校验。做成工具后：
- 参数由 schema 约束（必填项、枚举值）
- 组件白名单在服务端强制
- 返回值是「已生成 N 个组件」这种模型能理解的话

前端通过 SSE 的 ``a2ui`` 事件拿到消息序列。
"""

from __future__ import annotations

import contextvars

import logging
from typing import Any

from wuwei.tools import ToolRegistry

from app.services.a2ui.builder import (
    A2uiBuildError,
    create_surface,
    form_page,
    new_surface_id,
    simple_page,
    update_components,
    update_data_model,
)
from app.services.a2ui.catalog import catalog_prompt, extract_initial_data

logger = logging.getLogger("agenticos.a2ui")


# 本次 run 内各 surface 的校验失败次数（跨工具调用累计）。
# 用来在多次失败后升级提示语，避免模型反复用同一种错写法硬撞。
_failure_counts: contextvars.ContextVar[dict[str, int]] = contextvars.ContextVar(
    "a2ui_failure_counts", default={}
)


def _bump_failure(surface_id: str) -> int:
    counts = dict(_failure_counts.get())
    counts[surface_id] = counts.get(surface_id, 0) + 1
    _failure_counts.set(counts)
    return counts[surface_id]

# 进程内收集「本次 run 产生的 A2UI 消息」。
#
# 用 contextvar 而不是全局变量：一次 SSE 请求一个上下文，并发请求互不干扰。
# 采集器在 agent_service 的流式循环里消费，把消息塞进 SSE 事件。
#
# 注意：ContextVar 没有 default_factory，默认值必须是同一个对象引用。
# 所以这里用 None 作默认，首次访问时创建新列表 —— 避免多个请求共享同一个
# 可变默认值（那是经典陷阱）。

_pending_a2ui: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "a2ui_pending", default=None,
)


def _collector() -> list[dict[str, Any]]:
    """取当前上下文的采集列表，没有就建一个并绑定到上下文。"""
    items = _pending_a2ui.get()
    if items is None:
        items = []
        _pending_a2ui.set(items)
    return items


def reset_pending() -> None:
    """每次 run 开始时清空采集器。"""
    _pending_a2ui.set([])


def drain_pending() -> list[dict[str, Any]]:
    """取走并清空本次 run 累积的 A2UI 消息。"""
    items = _collector()
    _pending_a2ui.set([])
    return items


def _emit(messages: list[dict[str, Any]]) -> None:
    _collector().extend(messages)


def register_a2ui_tools(registry: ToolRegistry) -> None:
    """注册界面生成工具（仅 general 模式默认启用）。"""

    @registry.tool(display_name="生成界面")
    async def render_ui(
        title: str,
        body: str,
        style: str = "simple",
    ) -> str:
        """生成一块可视化界面展示给用户（标题 + 正文）。

        什么时候用：用户要「看看整理好的结果」「给我一屏汇总」「做个对比」
        这类需要结构化呈现、而不是一段长文本的需求。

        什么时候不用：普通问答、代码、需要用户复制走的文本 —— 那些直接回文本更好。

        参数:
          title: 界面标题（一句话）
          body: 正文内容，支持简单 Markdown（不含 HTML/图片/链接）
          style: 展示样式，可选 simple（默认）

        返回:
          生成结果说明
        """
        try:
            messages = simple_page(title=title, body=body)
        except A2uiBuildError as exc:
            return f"界面生成失败：{exc}\n请修正参数后重新调用 render_ui。"
        _emit(messages)
        logger.info("a2ui simple_page: title=%r components=2", title[:40])
        return f"已生成界面「{title}」（1 个区块）。用户会直接看到，无需再复述内容。"

    @registry.tool(display_name="生成表单")
    async def render_form(
        title: str,
        fields_json: str,
        submit_label: str = "提交",
    ) -> str:
        """生成一个可交互表单，用户填完点击提交后数据会回传。

        什么时候用：需要用户提供结构化输入（筛选条件、配置项、多字段信息）
        而不是在对话里一段段打字。

        参数:
          title: 表单标题
          fields_json: JSON 数组，每项一个字段::

              [{"id":"name","label":"姓名","type":"text","required":true},
               {"id":"level","label":"级别","type":"choice","options":["高","中","低"]},
               {"id":"agree","label":"同意条款","type":"check"}]

            type 支持: text / choice / check / slider
          submit_label: 提交按钮文案

        返回:
          生成结果说明
        """
        import json

        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError as exc:
            return f"fields_json 不是合法 JSON：{exc}"
        if not isinstance(fields, list) or not fields:
            return "fields_json 必须是非空数组"

        try:
            messages = form_page(
                title=title,
                fields=fields,
                submit_label=submit_label,
            )
        except A2uiBuildError as exc:
            return f"表单生成失败：{exc}\n请修正字段后重新调用 render_form。"

        _emit(messages)
        logger.info("a2ui form_page: title=%r fields=%d", title[:40], len(fields))
        return (
            f"已生成表单「{title}」（{len(fields)} 个字段）。"
            "用户填完点击「{submit_label}」后，字段值会作为动作回传。"
        )

    @registry.tool(display_name="自由组合界面")
    async def render_components(components_json: str, surface_id: str = "") -> str:
        """用 A2UI 基础组件自由组合一个界面（比 render_ui / render_form 更灵活）。

        什么时候用：render_ui 只能标题+正文、render_form 只能表单。需要
        更复杂结构时用这个 —— 卡片、标签页、列表、图表位、多列布局、
        按钮组、混合输入等任意组合。

        组件目录（只能用这些，共 18 个）：

          Text          必填 text        可选 variant(h1/h2/h3/body/caption/label)
          Column        必填 children    纵向布局，children 是 id 数组
          Row           必填 children    横向布局
          Card          必填 child       卡片容器，单个子组件 id
          List          必填 children    列表
          Divider       无必填           分隔线
          Button        必填 child       按钮，child 通常是 Text 的 id；可选 action
          TextField     必填 label       可选 value/required
          CheckBox      必填 label       可选 checked
          ChoicePicker  必填 options     可选 value；options 是 [{label,value}]
          Slider        必填 min,max     可选 value
          DateTimeInput 必填 label       可选 value
          Tabs          必填 tabs        tabs 是 [{label,child}]
          Modal         必填 child       可选 title
          Image         必填 src         可选 alt
          Icon          必填 name
          Video         必填 src
          AudioPlayer   必填 src

        结构规则（必须遵守，否则校验失败）：
          1. 扁平数组，每个组件有唯一 id；父子靠 id 引用，不能嵌套
          2. 必须有 id='root' 的容器组件（通常 Column）
          3. 输入类组件用 {"path":"/字段名"} 绑定值，初值会自动补
          4. 不能用未列出的组件名

        参数:
          components_json: 组件数组的 JSON 字符串，例如::

              [{"id":"root","component":"Column","children":["t","row1"]},
               {"id":"t","component":"Text","text":"汇总","variant":"h2"},
               {"id":"row1","component":"Row","children":["c1","c2"]},
               {"id":"c1","component":"Card","child":"t1"},
               {"id":"t1","component":"Text","text":"完成率 92%"}]

          surface_id: 可选，复用已有界面时传同一个 id；留空则新建

        返回:
          生成结果说明，或具体的校验错误（据此修正后重试）
        """
        import json

        try:
            components = json.loads(components_json)
        except json.JSONDecodeError as exc:
            return f"components_json 不是合法 JSON：{exc}"

        sid = surface_id.strip() or new_surface_id("ui")

        try:
            msg_components = update_components(sid, components)
        except A2uiBuildError as exc:
            # 校验失败：把「错误 + 正确写法」一起回给模型，并明确要求它重试。
            # 之前只回一句错误，模型常常直接放弃或改用纯文本 —— 用户看到的
            # 就是「界面渲染失败」。这里把重试变成指令，而不是可选动作。
            attempts = _bump_failure(sid)
            text = (
                f"组件校验失败（第 {attempts} 次）：{exc}\n"
                "请按上面的提示修正 components_json 后**重新调用 render_components**，"
                "不要改用纯文本回复 —— 用户期望看到界面。"
            )
            if attempts >= 2:
                text += (
                    "\n注意：已连续失败多次，请严格对照「可照抄的正确写法」"
                    "逐字段检查，特别是每个组件的必填字段是否齐全。"
                )
            logger.warning("a2ui render_components validation failed (attempt %d): %s",
                           attempts, str(exc)[:200])
            return text

        messages: list[dict[str, Any]] = [create_surface(sid), msg_components]

        # 自动补数据模型初值：模型常忘记单独发 updateDataModel，
        # 少了这一步输入类组件会绑定到 undefined。
        initial = extract_initial_data(components)
        if initial:
            messages.append(update_data_model(sid, initial))

        _emit(messages)
        logger.info(
            "a2ui render_components: surface=%s components=%d data_keys=%d",
            sid, len(components), len(initial),
        )
        return (
            f"已生成界面（surface={sid}，{len(components)} 个组件"
            + (f"，{len(initial)} 个绑定字段" if initial else "")
            + "）。用户会直接看到，无需在回复里重复组件内容。"
        )


__all__ = [
    "register_a2ui_tools",
    "reset_pending",
    "drain_pending",
    "new_surface_id",
]