"""OpenAI 兼容网关：外部软件用 sk-agenticos-* 调用，仅路由到 AgenticOS 本地智能体。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

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
    return JSONResponse(status_code=200, content=local)


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
    profile = find_local_agent(model, user)
    if profile is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "message": (
                        f"Unknown model '{model}'. This gateway only serves AgenticOS local agents; "
                        "call GET /v1/models to list available agent ids."
                    ),
                    "type": "invalid_request_error",
                }
            },
        )

    try:
        payload = ChatCompletionRequest(**body)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={"error": {"message": f"invalid request: {exc}"}},
        )

    from app.services.agent_service import get_agent_service

    return await run_local_completion(payload, user, get_agent_service(), profile)
