"""OpenAI 兼容执行器（把 AgenticOS 的智能体暴露成 OpenAI 形状的响应）。

路径由 ``app/api/gateway_v1.py`` 统一挂载：``/v1/models`` 与
``/v1/chat/completions``。本模块**只服务本地智能体**——企业上游透传已随
「移除企业上游」下线，model 未命中本地智能体时网关直接返回 400。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.models import UserModel
from app.schemas.agent import RESPONSE_MODES, AgentStreamRequest
from app.services.agent.service import AgentService

logger = logging.getLogger("openai_compat")

# 可被 OpenAI 客户端直接填进 model 字段的通用别名
GENERIC_MODEL_ALIASES = frozenset({
    "gpt-4o", "gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "assistant", "agent", "default",
})

# AgenticOS 的响应模式名：直接复用 schema 里的单一来源，避免各自维护白名单
# （漏一个就会让该模式的智能体被静默降级成 general）
LOCAL_MODE_NAMES = frozenset(RESPONSE_MODES)

# 通用别名（gpt-4o 等）回退到哪个模式
GENERIC_ALIAS_TARGET = "general"


def _agent_items(user: UserModel) -> list[dict[str, Any]]:
    from app.services.agent_profile_service import AgentProfileService

    return AgentProfileService().list_user_agents(user).get("items", [])


def local_agent_slugs(user: UserModel) -> set[str]:
    """当前用户可用的本地智能体标识（slug + 名称小写）。"""
    items = _agent_items(user)
    slugs: set[str] = set(GENERIC_MODEL_ALIASES) | set(LOCAL_MODE_NAMES)
    for item in items:
        slug = str(item.get("slug") or "").strip().lower()
        name = str(item.get("name") or "").strip().lower()
        if slug:
            slugs.add(slug)
        if name:
            slugs.add(name)
    return slugs


def find_local_agent(model: str, user: UserModel) -> dict[str, Any] | None:
    """把 model 解析为用户可用的本地智能体档案；无法解析返回 None。

    匹配优先级：slug → 名称 → 响应模式名 → 通用别名。
    返回档案而非布尔值，是为了让调用方拿回该智能体**自己的** response_mode，
    否则调用「PPT 智能体」会被按 general 执行、能力被静默削掉。
    响应模式是系统内建能力，即使列表里没有对应智能体也返回合成档案，
    否则 model="general" 这类标准写法会被误判为未知模型。
    """
    key = (model or "").strip().lower()
    items = _agent_items(user)
    if not key:
        key = GENERIC_ALIAS_TARGET
    for field in ("slug", "name", "response_mode"):
        for item in items:
            if str(item.get(field) or "").strip().lower() == key:
                return item
    if key in LOCAL_MODE_NAMES:
        return {"response_mode": key}
    if key in GENERIC_MODEL_ALIASES:
        return {"response_mode": GENERIC_ALIAS_TARGET}
    return None


def is_local_agent(model: str, user: UserModel) -> bool:
    """model 是否命中用户可用的本地智能体（网关据此拒绝未知 model）。"""
    return find_local_agent(model, user) is not None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="智能体名称或 slug，默认 general")
    messages: list[ChatMessage] = Field(..., min_length=1)
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    user: str | None = Field(default=None, description="透传用于审计")
    # AgenticOS 扩展（OpenAI 客户端会忽略未知字段）
    session_id: str | None = None
    approval_mode: str | None = Field(default=None, pattern="^(ask|auto|full)$")
    plan_mode: bool = False


def _extract_user_content(messages: list[ChatMessage]) -> str:
    """取最后一条 user 消息作为本轮输入。"""
    for message in reversed(messages):
        if message.role == "user":
            return message.content.strip()
    return messages[-1].content.strip()


def _resolve_model_name(raw: str) -> str:
    """把 model 名解析为 response_mode（接受 slug、名称或通用模式名）。"""
    value = (raw or "general").strip().lower()
    aliases = {
        "gpt-4o": "general", "gpt-4": "general", "gpt-3.5-turbo": "general",
        "assistant": "general", "agent": "general", "default": "general",
    }
    return aliases.get(value, value)


async def local_models_payload(current_user: UserModel) -> dict[str, Any]:
    """OpenAI 形状的模型列表（本地智能体）。"""
    from app.services.agent_profile_service import AgentProfileService

    items = AgentProfileService().list_user_agents(current_user).get("items", [])
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": item["slug"],
                "object": "model",
                "created": int(
                    (item.get("created_at") and time.mktime(item["created_at"].timetuple()))
                    or now
                ),
                "owned_by": "agenticos",
                "display_name": item["name"],
                "description": item.get("description") or "",
            }
            for item in items
        ],
    }


async def run_local_completion(
    payload: ChatCompletionRequest,
    current_user: UserModel,
    agent_service: AgentService,
    profile: dict[str, Any] | None = None,
):
    prompt = _extract_user_content(payload.messages)
    if not prompt:
        raise HTTPException(status_code=400, detail="messages 中缺少有效的用户消息")

    # 优先采用命中智能体的 response_mode：外部软件填智能体名称时，
    # 也应保留它原本的能力（PPT / 网站 / 办公…），而不是一律当通用智能体跑
    resolved = profile if profile is not None else find_local_agent(payload.model, current_user)
    response_mode = str((resolved or {}).get("response_mode") or "").strip().lower()
    if response_mode not in LOCAL_MODE_NAMES:
        response_mode = _resolve_model_name(payload.model)
    if response_mode not in LOCAL_MODE_NAMES:
        response_mode = "general"

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    request = AgentStreamRequest(
        message=prompt,
        session_id=payload.session_id,
        response_mode=response_mode,
        approval_mode=payload.approval_mode or "auto",
        plan_mode=payload.plan_mode,
    )

    async def run() -> tuple[str, str]:
        """返回 (正文, 推理摘要)。"""
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            agent_service.ensure_ready()
            await agent_service.ensure_session_access(request, current_user)
            async for event in agent_service.stream_chat(request, current_user):
                kind = event.get("event")
                data = event.get("data") or {}
                if kind == "delta":
                    text_parts.append(data.get("content") or "")
                elif kind == "reasoning_delta":
                    reasoning_parts.append(data.get("content") or "")
                elif kind == "error":
                    raise RuntimeError(data.get("message") or "agent error")
        except RuntimeError:
            raise
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return "".join(text_parts), "".join(reasoning_parts)

    if not payload.stream:
        try:
            text, reasoning = await run()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        message: dict[str, Any] = {"role": "assistant", "content": text}
        if reasoning:
            message["reasoning_content"] = reasoning
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": payload.model,
            "choices": [
                {"index": 0, "message": message, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    async def event_stream() -> AsyncIterator[bytes]:
        def _sse(obj: dict[str, Any]) -> bytes:
            return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()

        first = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": payload.model,
            "choices": [
                {"index": 0, "delta": {"role": "assistant"}, "finish_reason": None},
            ],
        }
        yield _sse(first)

        text_parts: list[str] = []
        try:
            agent_service.ensure_ready()
            await agent_service.ensure_session_access(request, current_user)
            async for event in agent_service.stream_chat(request, current_user):
                kind = event.get("event")
                data = event.get("data") or {}
                if kind == "delta":
                    chunk = data.get("content") or ""
                    if not chunk:
                        continue
                    text_parts.append(chunk)
                    yield _sse({
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": payload.model,
                        "choices": [
                            {"index": 0, "delta": {"content": chunk}, "finish_reason": None},
                        ],
                    })
                elif kind == "error":
                    message = data.get("message") or "agent error"
                    yield _sse({
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": payload.model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                        "error": {"message": message},
                    })
        except Exception as exc:  # noqa: BLE001 —— 流已开始，只能以错误块收尾
            logger.exception("openai-compat stream failed: %s", completion_id)
            yield _sse({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": payload.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                "error": {"message": str(exc)},
            })

        yield _sse({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": payload.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        })
        yield b"data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )