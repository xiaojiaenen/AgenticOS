"""LiteLLM Python SDK 旁路 PoC（docs/design/项目逐功能优化方案.md 3B.2 / 3F.0）。

**形态红线（用户明确）**：只用 LiteLLM 的 **Python SDK（纯库，
``pip install litellm`` 进程内 ``litellm.completion()``）**——零部署；
**Proxy / AI Gateway 形态明确排除**（那是独立 HTTP 服务，自带虚拟 key/
预算/看板，本项目用量记账/网关/并发闸已自研，不需要也不引入）。

定位：**旁路 PoC，不进主路径**。自研网关（llm_providers/，5857 行）承载
企业 Cookie 账号池、用量记账、SSE 契约等差异化资产，整块替换风险最高；
本模块只验证「标准 provider 统一调用」这一小块 SDK 价值：

- 入口 ``litellm_chat_completion``：OpenAI 风格消息 → ``litellm.completion``
  → wuwei ``LLMResponse``（含 tool_calls / usage 映射）；
- ``build_litellm_gateway``：包一层 wuwei ``LLMGateway`` 兼容面
  （``generate(messages, tools, stream)``），让 PoC 能直接喂给 agent；
- 依赖可选（``uv sync --extra litellm``）：未安装时报 ``ProviderConfigError``
  并提示装 extra，不影响主路径。

真 litellm 的联网调用属集成验证；单测用 fake litellm 模块锁定**映射契约**
（消息/工具/usage/finish_reason 双向对齐）。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_providers.spec import ProviderConfigError

logger = logging.getLogger("agenticos.llm.litellm")


def _require_litellm() -> Any:
    """按需导入 litellm（可选 extra）；未安装给出明确指引。"""
    try:
        import litellm  # type: ignore[import-not-found]

        return litellm
    except ImportError as exc:
        raise ProviderConfigError(
            "litellm 提供商需要可选依赖：uv sync --extra litellm（LiteLLM Python SDK，"
            "纯库零部署；Proxy 形态按红线排除）"
        ) from exc


def messages_to_litellm(messages: list[Any]) -> list[dict[str, Any]]:
    """wuwei Message（role/content/tool_calls）→ OpenAI 风格 dict 列表。"""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = getattr(msg, "role", None) or ("tool" if hasattr(msg, "tool_call_id") else "user")
        entry: dict[str, Any] = {"role": role, "content": getattr(msg, "content", "") or ""}
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            entry["tool_calls"] = [
                {
                    "type": "function",
                    "id": call.id,
                    "function": {
                        "name": call.function.name,
                        "arguments": (
                            call.function.arguments
                            if isinstance(call.function.arguments, str)
                            else json.dumps(call.function.arguments, ensure_ascii=False)
                        ),
                    },
                }
                for call in tool_calls
            ]
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id:
            entry["tool_call_id"] = tool_call_id
            entry["name"] = getattr(msg, "name", None) or ""
        out.append(entry)
    return out


def tools_to_litellm(tools: list[Any] | None) -> list[dict[str, Any]] | None:
    """wuwei Tool 列表 → OpenAI function schema（litellm 原生吃这个形态）。"""
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or tool.name,
                "parameters": tool.parameters.to_schema(),
            },
        }
        for tool in tools
    ]


def litellm_chat_completion(
    *,
    messages: list[Any],
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    tools: list[Any] | None = None,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> Any:
    """旁路 PoC 入口：litellm.completion → wuwei ``LLMResponse``。

    非 PoC 路径一律走自研网关（build_llm）；本函数只服务于显式配置了
    ``provider_type=litellm`` 的提供商。
    """
    litellm = _require_litellm()

    request_tools = tools_to_litellm(tools)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages_to_litellm(messages),
    }
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["api_base"] = base_url
    if request_tools:
        kwargs["tools"] = request_tools
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if timeout:
        kwargs["timeout"] = timeout

    response = litellm.completion(**kwargs)
    choice = response.choices[0]
    message = choice.message
    usage = getattr(response, "usage", None)

    from app.services.agent.native.types import FunctionCall, ToolCall
    from app.services.agent.native.types import LLMResponse

    tool_calls = [
        ToolCall(
            id=call.id,
            function=FunctionCall(
                name=call.function.name,
                arguments=call.function.arguments
                if isinstance(call.function.arguments, dict)
                else json.loads(call.function.arguments or "{}"),
            ),
        )
        for call in (getattr(message, "tool_calls", None) or [])
    ]
    usage_dict: dict[str, int] | None = None
    if usage is not None:
        usage_dict = {
            "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
        }
    return LLMResponse(
        content=message.content or "",
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason or "stop",
        usage=usage_dict,
        model=getattr(response, "model", None) or model,
    )


class LiteLLMGateway:
    """wuwei ``LLMGateway`` 最小兼容面（PoC 用）：generate(messages, tools, stream)。

    仅支持非流式（PoC 验证统一调用映射；流式走主路径自研网关）。
    """

    provider = "litellm"
    model_name = ""

    def __init__(self, *, model: str, api_key: str | None = None, base_url: str | None = None, max_tokens: int | None = None, timeout: int | None = None) -> None:
        self.model_name = model
        self._api_key = api_key
        self._base_url = base_url
        self._max_tokens = max_tokens
        self._timeout = timeout

    async def generate(self, messages: list[Any], tools: list[Any] | None = None, stream: bool = False, **kwargs: Any) -> Any:
        if stream:
            raise ProviderConfigError(
                "litellm PoC 仅支持非流式；流式主路径请用自研网关（provider_type=openai_compatible）"
            )
        return await _run_completion(
            messages=messages,
            model=self.model_name,
            api_key=self._api_key,
            base_url=self._base_url,
            tools=tools,
            max_tokens=self._max_tokens,
            timeout=self._timeout,
        )


async def _run_completion(**kwargs: Any) -> Any:
    import asyncio

    return await asyncio.to_thread(litellm_chat_completion, **kwargs)


def build_litellm_gateway(spec: Any, *, max_tokens: int, timeout: int, model: str | None = None) -> Any:
    """按 ProviderSpec 构建 LiteLLM PoC 网关（build_gateway 的 litellm 分支）。"""
    return LiteLLMGateway(
        model=(model or spec.model or "").strip(),
        api_key=spec.api_key,
        base_url=spec.base_url,
        max_tokens=spec.max_tokens or max_tokens,
        timeout=spec.timeout_seconds or timeout,
    )
