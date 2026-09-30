"""OpenAI 兼容网关：外部软件用 sk-agenticos-* 调用，经 Cookie 转发到 agents.gree.com。"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.upstream.api_key_service import authenticate_api_key
from app.services.upstream.credential_store import get_active_cookie, get_upstream_base_url
from app.services.upstream.login_orchestrator import perform_auto_login

logger = logging.getLogger("agenticos.upstream.gateway")

# 挂在应用根路径 /v1/*（与 OpenAI / Sesame 客户端兼容）
router = APIRouter(tags=["Upstream Gateway"])


def _extract_api_key(request: Request) -> str:
    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


async def _resolve_cookie(user_id: int) -> str:
    cookie = get_active_cookie(user_id)
    if cookie:
        return cookie
    # 无可用 Cookie：自动登录一次（与 Sesame 同流程）
    result = await perform_auto_login(user_id)
    cookie = get_active_cookie(user_id)
    if not cookie:
        raise HTTPException(
            status_code=502,
            detail=result.get("message") or "上游 Cookie 不可用，请先登录 AgenticOS 以自动获取",
        )
    return cookie


@router.get("/v1/models")
async def list_models(request: Request):
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API key", "type": "invalid_request_error"}})

    cookie = await _resolve_cookie(user.id)
    base = get_upstream_base_url()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{base}/v1/models",
            headers={"Cookie": cookie, "Authorization": f"Bearer {api_key}"},
        )
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": resp.text[:300], "code": resp.status_code}}
    return JSONResponse(status_code=resp.status_code, content=data)


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API key", "type": "invalid_request_error"}})

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "Invalid JSON body"}})

    cookie = await _resolve_cookie(user.id)
    base = get_upstream_base_url()
    stream = bool(body.get("stream"))
    headers = {
        "Cookie": cookie,
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }

    async def _proxy_stream():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{base}/v1/chat/completions",
                json=body,
                headers=headers,
            ) as resp:
                if resp.status_code >= 400:
                    raw = await resp.aread()
                    yield raw
                    return
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    if stream:
        return StreamingResponse(_proxy_stream(), media_type="text/event-stream")

    async with httpx.AsyncClient(timeout=300.0) as client:
        resp = await client.post(f"{base}/v1/chat/completions", json=body, headers=headers)
    try:
        data = resp.json()
    except Exception:
        data = {"error": {"message": resp.text[:500], "code": resp.status_code}}
    return JSONResponse(status_code=resp.status_code, content=data)


@router.get("/v1/upstream/ping")
async def ping(request: Request):
    """轻量探活：校验 API Key 并返回所属用户。"""
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return JSONResponse(status_code=401, content={"error": {"message": "Invalid API key"}})
    return {"ok": True, "user_id": user.id, "upstream": "agents.gree.com"}
