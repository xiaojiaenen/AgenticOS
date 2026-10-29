"""OpenAI 兼容网关：外部软件用 sk-agenticos-* 调用，仅路由到 AgenticOS 本地智能体。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.gateway_multi import classify_model
from app.services.api_key_service import authenticate_api_key

logger = logging.getLogger("agenticos.gateway")

# 挂在应用根路径 /v1/*（与 OpenAI / Sesame 客户端兼容）
router = APIRouter(tags=["OpenAI-Compatible Gateway"])


def _extract_api_key(request: Request) -> str:
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


def _unauthorized() -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": {"message": "Invalid API key", "type": "invalid_request_error"}})


@router.get("/v1/models")
async def list_models(request: Request):
    """模型列表：仅暴露 AgenticOS 本地智能体。"""
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return _unauthorized()

    from app.api.v1.endpoints.openai_compat import local_models_payload

    local = await local_models_payload(user)
    items = list(local.get("data") or [])

    # 同时列出「纯模型」—— 接入方据此知道可以填哪些真实模型名。
    # 不带 llm: 前缀的模型名与智能体共享命名空间，冲突时智能体优先
    # （classify_model 的顺序），这里额外提供 llm: 形式作为无歧义写法。
    try:
        from app.db.session import create_db_session
        from app.services.llm_providers.resolve_models import (
            resolve_embedding_endpoint,
            resolve_image_endpoint,
        )
        from app.services.llm_providers.spec import resolve_active_provider

        with create_db_session() as db:
            try:
                active = resolve_active_provider()
                chat_model = (active.model or "").strip()
                if chat_model:
                    items.append({
                        "id": f"llm:{chat_model}",
                        "object": "model",
                        "created": int(__import__("time").time()),
                        "owned_by": "agenticos",
                        "display_name": f"直通模型 {chat_model}",
                        "description": "纯模型调用，不带工具与智能体编排",
                    })
            except Exception:  # noqa: BLE001
                pass

            try:
                emb = resolve_embedding_endpoint(db)
                if emb is not None:
                    items.append({
                        "id": emb.model,
                        "object": "model",
                        "created": int(__import__("time").time()),
                        "owned_by": "agenticos",
                        "display_name": f"向量化 {emb.model}",
                        "description": f"用于 /v1/embeddings（来源 {emb.source}）",
                    })
            except Exception:  # noqa: BLE001
                pass

            try:
                img = resolve_image_endpoint(db)
                if img is not None:
                    items.append({
                        "id": img.model,
                        "object": "model",
                        "created": int(__import__("time").time()),
                        "owned_by": "agenticos",
                        "display_name": f"生图 {img.model}",
                        "description": f"用于 /v1/images/generations（来源 {img.source}）",
                    })
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        logger.debug("列模型时解析 provider 失败", exc_info=True)

    return JSONResponse(status_code=200, content={"object": "list", "data": items})


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return _unauthorized()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON body"}})

    from app.api.v1.endpoints.openai_compat import (
        ChatCompletionRequest,
        find_local_agent,
        run_local_completion,
    )

    model = str(body.get("model") or "")

    # 双通道：命中智能体走智能体（保留工具与多步能力）；否则走纯模型直通。
    #
    # 旧实现未命中就 400，导致「只想用模型」的接入方根本接不进来 ——
    # 填 gpt-4o / deepseek-chat 是常态，不该被拒。用 llm: 前缀可强制直通，
    # 避免「智能体恰好叫 gpt-4o」的歧义。
    kind, name = classify_model(model, user)

    if kind == "llm":
        return await _run_direct_chat(body, name)

    profile = find_local_agent(model, user)
    try:
        payload = ChatCompletionRequest(**body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={"error": {"message": f"invalid request: {exc}"}},
        )

    from app.services.agent_service import get_agent_service

    return await run_local_completion(payload, user, get_agent_service(), profile)


async def _run_direct_chat(body: dict, model_name: str):
    """纯模型直通（不带工具、不启会话）。"""
    import json as _json
    from typing import Any as _Any

    from fastapi.responses import StreamingResponse as _StreamingResponse

    from app.services.llm_providers import direct
    from app.services.llm_providers.direct import DirectLLMError

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "messages 不能为空", "type": "invalid_request_error"}},
        )

    stream = bool(body.get("stream"))
    temperature = body.get("temperature")
    top_p = body.get("top_p")
    max_tokens = body.get("max_tokens") or body.get("max_completion_tokens")
    stop = body.get("stop")

    from app.db.session import create_db_session

    try:
        with create_db_session() as db:
            gateway, resolved_model, result = await direct.complete(
                db,
                messages=messages,
                model=model_name,
                temperature=temperature,
                top_p=top_p,
                max_tokens=int(max_tokens) if max_tokens else None,
                stop=stop if isinstance(stop, list) else None,
                stream=stream,
            )
    except DirectLLMError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": str(exc), "type": "api_error"}},
        )

    completion_id = direct.new_completion_id()
    created = direct.now_ts()

    if not stream:
        return JSONResponse(
            status_code=200,
            content={
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": resolved_model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": direct.extract_text(result),
                            **(
                                {"reasoning_content": direct.extract_reasoning(result)}
                                if direct.extract_reasoning(result)
                                else {}
                            ),
                        },
                        "finish_reason": direct.extract_finish_reason(result),
                    }
                ],
                "usage": direct.extract_usage(result),
            },
        )

    async def event_stream():
        def _sse(obj: dict[str, _Any]) -> bytes:
            return f"data: {_json.dumps(obj, ensure_ascii=False, default=str)}\n\n".encode()

        yield _sse({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": resolved_model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        })
        try:
            async for chunk in result:
                delta = _chunk_text(chunk)
                if delta:
                    yield _sse({
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": resolved_model,
                        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                    })
        except Exception as exc:  # noqa: BLE001
            logger.warning("direct chat stream failed", exc_info=True)
            yield _sse({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": resolved_model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                "error": {"message": str(exc)},
            })
        yield _sse({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": resolved_model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        })
        yield b"data: [DONE]\n\n"

    return _StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chunk_text(chunk) -> str:
    """从流式 chunk 里取增量文本（统一走 direct.chunk_text）。"""
    from app.services.llm_providers.direct import chunk_text

    return chunk_text(chunk)
