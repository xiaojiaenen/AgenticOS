"""把 OpenAI 风格的 tools 定义转成 wuwei 的 Tool 对象。

关键设计：**这些工具我们只声明、不执行**。

为什么要这样：对外网关的「直通」是指「不经过 AgenticOS 的智能体编排与
内置工具」，但调用方可能希望模型自己发起 function calling —— 那是模型
自身的能力，不该被削掉。

做法：把客户端传的 tools schema 转成 wuwei Tool，handler 是一个**占位
实现**，只负责把调用意图回传。真正的执行由客户端完成（OpenAI 的
function calling 协议本来就是「模型给参数，客户端执行再回灌结果」）。

这样：
- 模型能看到 tools 定义，能自己决定要不要调、调哪个
- 返回的 tool_calls 原样透传给客户端
- 客户端执行后把结果作为 tool 消息发回来，我们继续下一轮
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("agenticos.direct_tools")


class ToolSpecError(ValueError):
    """客户端传的 tools 定义不合法。"""


def _normalize_parameters(raw: Any) -> dict[str, Any]:
    """把 JSON Schema 规整成 wuwei ToolParameters 能接受的结构。

    OpenAI 的 tools 定义形如::

        {"type": "function",
         "function": {"name": "get_weather",
                      "description": "...",
                      "parameters": {"type": "object",
                                     "properties": {...},
                                     "required": [...]}}}

    有的客户端省略 parameters，或只给 properties。都兜住。
    """
    if not isinstance(raw, dict):
        return {"type": "object", "properties": {}, "required": []}

    props = raw.get("properties")
    if not isinstance(props, dict):
        props = {}
    required = raw.get("required")
    if not isinstance(required, list):
        required = []
    # required 里可能有不在 properties 中的名字 —— 上游会因此报错
    required = [str(r) for r in required if str(r) in props]
    return {
        "type": str(raw.get("type") or "object"),
        "properties": props,
        "required": required,
    }


def openai_tools_to_wuwei(tools: Any) -> list[Any]:
    """把 OpenAI 风格的 tools 数组转成 wuwei Tool 列表。

    无法识别的项跳过并记 warning —— 一个坏定义不该让整次请求失败。
    """
    if not tools:
        return []
    if not isinstance(tools, list):
        raise ToolSpecError("tools 必须是数组")

    from wuwei.tools.tool import Tool, ToolParameters

    out: list[Any] = []
    for index, item in enumerate(tools):
        if not isinstance(item, dict):
            logger.warning("跳过非对象 tools[%d]", index)
            continue

        # 两种形态：{"type":"function","function":{...}} 或直接 {name,...}
        fn = item.get("function") if isinstance(item.get("function"), dict) else item
        name = str(fn.get("name") or "").strip()
        if not name:
            logger.warning("跳过缺少 name 的 tools[%d]", index)
            continue

        description = str(fn.get("description") or "").strip()
        params = _normalize_parameters(fn.get("parameters"))

        # handler 是占位：直通通道不执行工具，只把意图回传。
        # 用闭包捕获 name，方便日志定位「模型想调哪个」。
        def _placeholder(*args: Any, __name: str = name, **kwargs: Any) -> str:
            logger.info("模型请求调用外部工具 %s（由客户端执行）", __name)
            return f"tool {__name} is executed by the client"

        try:
            out.append(
                Tool(
                    name=name,
                    description=description or name,
                    parameters=ToolParameters(**params),
                    handler=_placeholder,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("tools[%d]（%s）构造失败：%s", index, name, exc)

    return out


def wuwei_tool_calls_to_openai(tool_calls: Any) -> list[dict[str, Any]]:
    """把 wuwei 返回的 tool_calls 转成 OpenAI 的 tool_calls 形状。

    OpenAI 形状::

        {"id": "call_x", "type": "function",
         "function": {"name": "...", "arguments": "{...}"}}

    arguments 必须是**字符串**（JSON 序列化后的），不是对象 ——
    很多客户端按字符串解析，给对象会崩。
    """
    import json

    if not tool_calls:
        return []

    out: list[dict[str, Any]] = []
    for index, call in enumerate(tool_calls):
        if isinstance(call, dict):
            fn = call.get("function") if isinstance(call.get("function"), dict) else call
            name = str(fn.get("name") or call.get("name") or "").strip()
            args = fn.get("arguments") if "arguments" in fn else call.get("arguments")
            call_id = str(call.get("id") or call.get("tool_call_id") or f"call_{index}")
        else:
            fn = getattr(call, "function", None)
            name = str(getattr(fn, "name", None) or getattr(call, "name", "") or "").strip()
            args = getattr(fn, "arguments", None) if fn else getattr(call, "arguments", None)
            call_id = str(getattr(call, "id", None) or f"call_{index}")

        if not name:
            continue

        # arguments 统一成字符串
        if isinstance(args, str):
            arguments = args
        elif args is None:
            arguments = "{}"
        else:
            try:
                arguments = json.dumps(args, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                arguments = "{}"

        out.append({
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        })
    return out
