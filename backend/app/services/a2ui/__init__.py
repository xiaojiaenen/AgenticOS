"""A2UI 服务：智能体可调用的界面生成工具 + SSE 事件约定。

为什么做成工具而不是让模型直接吐 JSON：模型吐 JSON 有三个问题 ——
格式容易错、组件名容易编、没有校验。做成工具后：
- 参数由 schema 约束（必填项、枚举值）
- 组件白名单在服务端强制
- 返回值是「已生成 N 个组件」这种模型能理解的话

前端通过 SSE 的 ``a2ui`` 事件拿到消息序列。
"""

from __future__ import annotations

import logging
from typing import Any

from wuwei.tools import ToolRegistry

from app.services.a2ui.builder import (
    A2uiBuildError,
    form_page,
    new_surface_id,
    simple_page,
)

logger = logging.getLogger("agenticos.a2ui")

# 进程内收集「本次 run 产生的 A2UI 消息」。
#
# 用 contextvar 而不是全局变量：一次 SSE 请求一个上下文，并发请求互不干扰。
# 采集器在 agent_service 的流式循环里消费，把消息塞进 SSE 事件。
#
# 注意：ContextVar 没有 default_factory，默认值必须是同一个对象引用。
# 所以这里用 None 作默认，首次访问时创建新列表 —— 避免多个请求共享同一个
# 可变默认值（那是经典陷阱）。
import contextvars

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
            return f"界面生成失败：{exc}"
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
            return f"表单生成失败：{exc}"

        _emit(messages)
        logger.info("a2ui form_page: title=%r fields=%d", title[:40], len(fields))
        return (
            f"已生成表单「{title}」（{len(fields)} 个字段）。"
            "用户填完点击「{submit_label}」后，字段值会作为动作回传。"
        )


__all__ = [
    "register_a2ui_tools",
    "reset_pending",
    "drain_pending",
    "new_surface_id",
]
