"""自有工具注册表（wuwei 退役 A5-1b）。

API 与原 wuwei ToolRegistry 逐一对齐（`@registry.tool(...)` 装饰器、
register/unregister/get/list_tools/to_schema、Tool.invoke 的 schema 校验 +
参数强转），使 `app/tools/*.py` 的 20+ 工具文件只需换 import 行。

与原实现的差异（全新系统）：
- 移除 RunContext 注入机制（业务未使用）；
- 移除 retry_policy（重试统一在网关层）；
- invoke 不再给异常挂 `_wuwei_tool_executed` 标记（补丁层语义，
  由引擎的 tool_end/tool_error 事件表达）。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from jsonschema import ValidationError
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from typing_extensions import get_type_hints

_logger = logging.getLogger("agenticos.tools")


class ToolParameters(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list = Field(default_factory=list)

    def to_schema(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ToolExecutionPolicy(BaseModel):
    timeout_seconds: float | None = None
    side_effect: bool = False
    requires_approval: bool = False
    idempotent: bool = False


class Tool(BaseModel):
    name: str
    description: str
    parameters: ToolParameters
    handler: Callable[..., Any] | Callable[..., Awaitable[Any]]
    execution: ToolExecutionPolicy = Field(default_factory=ToolExecutionPolicy)
    display_name: str | None = None
    is_concurrency_safe: bool | None = None

    _validator: Any = PrivateAttr(default=None)
    _signature: Any = PrivateAttr(default=None)
    _adapters: dict = PrivateAttr(default=None)

    def _validation_cache(self) -> dict:
        if self._validator is None:
            schema = self.parameters.to_schema()
            self._validator = validator_for(schema)(schema)
            self._signature = inspect.signature(self.handler)
            hints = get_type_hints(self.handler)
            self._adapters = {
                key: hints[key] if isinstance(hints[key], type) else None for key in hints
            }
        return {
            "validator": self._validator,
            "signature": self._signature,
            "adapters": self._adapters,
        }

    @property
    def concurrency_safe(self) -> bool:
        if self.is_concurrency_safe is not None:
            return self.is_concurrency_safe
        return not self.execution.side_effect

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters.to_schema(),
            },
        }

    async def invoke(self, args: dict[str, Any] | None = None) -> Any:
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ValueError("Tool arguments must be an object")
        cache = self._validation_cache()
        try:
            cache["validator"].validate(args)
        except ValidationError as exc:
            raise ValueError(f"Invalid tool arguments: {exc.message}") from exc
        args = dict(args)
        cache["signature"].bind(**args)
        try:
            if inspect.iscoroutinefunction(self.handler):
                return await self.handler(**args)
            result = await asyncio.to_thread(self.handler, **args)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as exc:
            exc._native_tool_executed = True  # type: ignore[attr-defined]
            raise


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"工具 {tool.name} 已经注册了")
        self._tools[tool.name] = tool
        return tool

    def unregister(self, tool: Tool) -> None:
        if tool.name not in self._tools:
            raise ValueError(f"工具 {tool.name} 没有注册")
        del self._tools[tool.name]

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_schema(self) -> list[dict]:
        return [tool.to_schema() for tool in self._tools.values()]

    def register_callable(
        self,
        func: Callable[..., Any] | Callable[..., Awaitable[Any]],
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: ToolParameters | None = None,
        execution: ToolExecutionPolicy | None = None,
        timeout_seconds: float | None = None,
        side_effect: bool = False,
        requires_approval: bool = False,
        display_name: str | None = None,
    ) -> Tool:
        tool_name = name or func.__name__
        self.tool(
            name=tool_name,
            description=description,
            parameters=parameters,
            execution=execution,
            timeout_seconds=timeout_seconds,
            side_effect=side_effect,
            requires_approval=requires_approval,
            display_name=display_name,
        )(func)
        tool = self.get(tool_name)
        if tool is None:  # pragma: no cover —— 注册即成功
            raise ValueError(f"工具 {tool_name} 注册失败")
        return tool

    def tool(
        self,
        name: str = None,
        description: str = None,
        parameters: ToolParameters = None,
        execution: ToolExecutionPolicy | None = None,
        timeout_seconds: float | None = None,
        side_effect: bool = False,
        requires_approval: bool = False,
        display_name: str | None = None,
    ):
        def decorator(func: Callable[..., Any] | Callable[..., Awaitable[Any]]):
            tool_name = name or func.__name__
            tool_description = description or func.__doc__ or f"执行{func.__name__}操作"
            if parameters:
                tool_parameters = parameters
            else:
                from pydantic import create_model

                sig = inspect.signature(func)
                hints = get_type_hints(func)
                fields: dict[str, Any] = {}
                for key, param in sig.parameters.items():
                    if key == "self" or param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
                        continue
                    fields[key] = (
                        hints.get(key, Any),
                        ... if param.default is inspect.Parameter.empty else param.default,
                    )
                schema = create_model(f"{tool_name}Arguments", **fields).model_json_schema()
                schema.pop("title", None)
                tool_parameters = ToolParameters.model_validate(schema)
            self.register(
                Tool(
                    name=tool_name,
                    description=tool_description,
                    parameters=tool_parameters,
                    handler=func,
                    execution=execution
                    or ToolExecutionPolicy(
                        timeout_seconds=timeout_seconds,
                        side_effect=side_effect,
                        requires_approval=requires_approval,
                    ),
                    display_name=display_name,
                )
            )
            return func

        return decorator
