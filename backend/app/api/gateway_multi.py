"""对外多协议网关：OpenAI / Anthropic / Responses / Embeddings / Images。

一个网关同时支持四种协议，让不同客户端都能接：

- **OpenAI Chat Completions** ``/v1/chat/completions``
  存量最广，几乎所有客户端都支持。
- **OpenAI Responses** ``/v1/responses``
  OpenAI 新版主推协议，Codex / 新版 SDK 走这条。
- **Anthropic Messages** ``/v1/messages``
  Claude Code、以及一批只认 Anthropic 协议的工具。
- **Embeddings / Images** ``/v1/embeddings``、``/v1/images/generations``
  向量化与生图，独立端点。

## 核心区分：agent vs llm

同一个 ``/v1/chat/completions`` 上，``model`` 可以指向两类东西：

1. **智能体**（带工具、多步推理、有会话）—— 名字是智能体 slug 或模式名
2. **纯模型**（一次调用出结果，无工具）—— 名字是真实模型名，或带
   ``llm:`` 前缀

区分方式：先按智能体解析，命中就走智能体；未命中且看起来像模型名，
就走直通通道。``llm:xxx`` 前缀可以强制走直通，避免「智能体恰好叫
gpt-4o」这种歧义。

为什么要保留智能体路径：现有接入方已经在用智能体（PPT/网站等），
不能因为新增直通能力就把它们的行为改掉。

## 协议转换的取舍

不做「完美翻译」，只保证**客户端能正常工作**：

- Anthropic 的 ``system`` 是顶层字段，OpenAI 是 messages 里的一条
  → 转换时把 system 抽出来 / 塞回去
- Anthropic 的 ``content`` 是 block 数组，OpenAI 是字符串
  → 单 block 时降级成字符串，多 block 时保留数组
- Responses 的 ``output`` 是 item 数组，不是 choices
  → 按 item 结构组装

刻意不做的：thinking / cache_control / tool_use 这些高级特性。直通通道
本来就不带工具，硬翻会造出「看起来支持但行为不对」的假象。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.services.api_key_service import authenticate_api_key

logger = logging.getLogger("agenticos.gateway.multi")

router = APIRouter(tags=["Multi-Protocol Gateway"])

# 强制走直通通道的模型名前缀
LLM_PREFIX = "llm:"


# ---------------------------------------------------------------------------
# 鉴权与错误
# ---------------------------------------------------------------------------


def _extract_api_key(request: Request) -> str:
    """从 Authorization 头取 key。

    Anthropic 客户端用 ``x-api-key``，OpenAI 用 ``Authorization: Bearer``，
    两种都认 —— 否则 Claude Code 直接连不上。
    """
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or "").strip()


def _unauthorized(protocol: str = "openai") -> JSONResponse:
    if protocol == "anthropic":
        return JSONResponse(
            status_code=401,
            content={"type": "error", "error": {"type": "authentication_error", "message": "Invalid API key"}},
        )
    return JSONResponse(
        status_code=401,
        content={"error": {"message": "Invalid API key", "type": "invalid_request_error"}},
    )


def _error(message: str, status: int = 400, protocol: str = "openai") -> JSONResponse:
    if protocol == "anthropic":
        return JSONResponse(
            status_code=status,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": message}},
        )
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "invalid_request_error"}},
    )


# ---------------------------------------------------------------------------
# 模型分类
# ---------------------------------------------------------------------------


def _strip_llm_prefix(model: str) -> str:
    """剥掉 ``llm:`` 前缀。

    这个前缀是给 /v1/chat/completions 做「强制直通」用的；/v1/messages
    与 /v1/responses 本来就只有直通通道，不需要前缀。但客户端可能
    统一带上（比如同一份配置复用到多个端点），所以要在这里剥掉 ——
    否则 ``llm:xxx`` 会被当成模型名发给上游，直接 404。
    """
    raw = (model or "").strip()
    if raw.lower().startswith(LLM_PREFIX):
        return raw[len(LLM_PREFIX):].strip()
    return raw


def classify_model(model: str, user) -> tuple[str, str]:
    """判断 model 该走哪条通道。

    返回 ``(kind, name)``：
    - ``("agent", slug)`` —— 命中用户可用智能体
    - ``("llm", model_name)`` —— 走直通，name 是去掉前缀的真实模型名
    """
    raw = (model or "").strip()
    if raw.lower().startswith(LLM_PREFIX):
        return "llm", raw[len(LLM_PREFIX):].strip()

    from app.api.v1.endpoints.openai_compat import find_local_agent

    profile = find_local_agent(raw, user)
    if profile is not None:
        return "agent", raw

    # 未命中智能体 —— 当作模型名走直通。
    # 不再像旧实现那样直接 400：接入方填 gpt-4o / deepseek-chat 是常态，
    # 拒掉会让「只想用模型」的用户根本接不进来。
    return "llm", raw


# ---------------------------------------------------------------------------
# /v1/embeddings
# ---------------------------------------------------------------------------


@router.post("/v1/embeddings")
async def embeddings(request: Request):
    """向量化。input 支持字符串或字符串数组。"""
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return _unauthorized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    model = str(body.get("model") or "").strip()
    raw_input = body.get("input")
    if isinstance(raw_input, str):
        inputs = [raw_input]
    elif isinstance(raw_input, list) and all(isinstance(x, str) for x in raw_input):
        inputs = list(raw_input)
    else:
        return _error("input 必须是字符串或字符串数组")

    if not inputs:
        return _error("input 不能为空")

    from app.services.llm_providers.resolve_models import resolve_embedding_endpoint

    try:
        from app.db.session import create_db_session

        with create_db_session() as db:
            endpoint = resolve_embedding_endpoint(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析 embedding 端点失败", exc_info=True)
        return _error(f"读取向量化配置失败：{exc}", 500)

    if endpoint is None:
        return _error(
            "还没有配置向量化模型。请管理员到「AI 提供商」页面，"
            "在模型用途里把「文本向量化」绑定到一个 embedding 模型。",
            503,
        )

    # 本地模型走进程内推理，远程走 HTTP
    if endpoint.source == "local":
        try:
            from app.services.knowledge.local_embedder import get_local_embedder

            embedder = get_local_embedder(endpoint.model, expected_dims=endpoint.dimensions or None)
            vectors = embedder.encode(inputs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("本地向量化失败", exc_info=True)
            return _error(f"本地向量化失败：{exc}", 500)
    else:
        import httpx

        payload: dict[str, Any] = {"model": model or endpoint.model, "input": inputs}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{endpoint.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {endpoint.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code == 404:
                    return _error(
                        f"提供商端点不支持 /embeddings（404）。当前：{endpoint.base_url}", 502
                    )
                if resp.status_code in (401, 403):
                    return _error(f"向量化鉴权失败（{resp.status_code}）", 502)
                resp.raise_for_status()
                data = resp.json()
        except httpx.TimeoutException:
            return _error("向量化请求超时", 504)
        except Exception as exc:  # noqa: BLE001
            logger.warning("远程向量化失败", exc_info=True)
            return _error(f"向量化失败：{type(exc).__name__}: {exc}", 502)

        # 上游返回 OpenAI 形状，原样透传（客户端要的是 data[].embedding）
        return JSONResponse(status_code=200, content=data)

    usage = {"prompt_tokens": sum(len(t) for t in inputs), "total_tokens": sum(len(t) for t in inputs)}
    return JSONResponse(
        status_code=200,
        content={
            "object": "list",
            "data": [
                {"object": "embedding", "index": i, "embedding": vec}
                for i, vec in enumerate(vectors)
            ],
            "model": endpoint.model,
            "usage": usage,
        },
    )


# ---------------------------------------------------------------------------
# /v1/images/generations
# ---------------------------------------------------------------------------


@router.post("/v1/images/generations")
async def images_generations(request: Request):
    """生图。返回 b64_json 或 url，取决于请求里的 response_format。"""
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return _unauthorized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        return _error("prompt 不能为空")

    from app.services.llm_providers.resolve_models import resolve_image_endpoint

    try:
        from app.db.session import create_db_session

        with create_db_session() as db:
            endpoint = resolve_image_endpoint(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析生图端点失败", exc_info=True)
        return _error(f"读取生图配置失败：{exc}", 500)

    if endpoint is None:
        return _error(
            "还没有配置生图模型。请管理员到「AI 提供商」页面，"
            "在模型用途里把「文生图」绑定到一个生图模型。",
            503,
        )

    import httpx

    payload: dict[str, Any] = {
        "model": str(body.get("model") or endpoint.model),
        "prompt": prompt,
        "n": int(body.get("n") or 1),
        "size": str(body.get("size") or "1024x1024"),
        "response_format": str(body.get("response_format") or "url"),
    }
    if body.get("quality"):
        payload["quality"] = body["quality"]
    if body.get("style"):
        payload["style"] = body["style"]

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(
                f"{endpoint.base_url}/images/generations",
                headers={
                    "Authorization": f"Bearer {endpoint.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code == 404:
                return _error(
                    f"提供商端点不支持 /images/generations（404）。当前：{endpoint.base_url}", 502
                )
            if resp.status_code in (401, 403):
                return _error(f"生图鉴权失败（{resp.status_code}）", 502)
            resp.raise_for_status()
            return JSONResponse(status_code=200, content=resp.json())
    except httpx.TimeoutException:
        return _error("生图请求超时", 504)
    except Exception as exc:  # noqa: BLE001
        logger.warning("生图失败", exc_info=True)
        return _error(f"生图失败：{type(exc).__name__}: {exc}", 502)


# ---------------------------------------------------------------------------
# Anthropic 协议转换
# ---------------------------------------------------------------------------


def _anthropic_to_openai_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Anthropic messages → OpenAI messages。

    Anthropic 的 ``system`` 是顶层字段；OpenAI 要放进 messages 里。
    反过来转换时也要抽出来，否则 system 会变成一条普通 user/assistant 消息。
    """
    messages: list[dict[str, Any]] = []

    system = body.get("system")
    if isinstance(system, str) and system.strip():
        messages.append({"role": "system", "content": system})
    elif isinstance(system, list):
        # Anthropic 也允许 block 数组形态的 system
        parts = [
            str(b.get("text") or "")
            for b in system
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        joined = "".join(p for p in parts if p)
        if joined:
            messages.append({"role": "system", "content": joined})

    for item in body.get("messages") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        content = item.get("content")
        if isinstance(content, str):
            messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # block 数组：只保留 text 块，其余（image/tool_use）直通通道不支持
            parts = [
                str(b.get("text") or "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            messages.append({"role": role, "content": "".join(p for p in parts if p)})
        else:
            messages.append({"role": role, "content": str(content or "")})

    return messages


def _openai_to_anthropic_response(
    *, text: str, reasoning: str, usage: dict[str, int], model: str, finish_reason: str
) -> dict[str, Any]:
    """OpenAI 结果 → Anthropic Messages 响应形状。

    Anthropic 的 content 是 block 数组；usage 用 input_tokens/output_tokens。
    """
    content_blocks: list[dict[str, Any]] = []
    if reasoning:
        # ThinkingBlock 的 signature 是**必填**字段（anthropic SDK 2.3.0
        # 的 Pydantic 模型要求）。它是 Anthropic 用来校验思考块未被篡改的
        # 签名；我们这里是转发上游的推理内容，没有真实签名，只能给空串 ——
        # 客户端能解析，但会知道这不是官方签名的思考块。
        content_blocks.append({
            "type": "thinking",
            "thinking": reasoning,
            "signature": "",
        })
    content_blocks.append({"type": "text", "text": text})

    stop_reason = "end_turn"
    if finish_reason == "length":
        stop_reason = "max_tokens"
    elif finish_reason in ("tool_calls", "function_call"):
        stop_reason = "tool_use"

    return {
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


@router.post("/v1/messages")
async def anthropic_messages(request: Request):
    """Anthropic Messages API 兼容端点。"""
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return _unauthorized("anthropic")

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body", 400, "anthropic")

    messages = _anthropic_to_openai_messages(body)
    if not messages:
        return _error("messages 不能为空", 400, "anthropic")

    model = _strip_llm_prefix(str(body.get("model") or ""))
    stream = bool(body.get("stream"))
    max_tokens = body.get("max_tokens")
    temperature = body.get("temperature")
    top_p = body.get("top_p")
    stop = body.get("stop_sequences")

    from app.db.session import create_db_session
    from app.services.llm_providers import direct
    from app.services.llm_providers.direct import DirectLLMError

    try:
        with create_db_session() as db:
            gateway, model_name, result = await direct.complete(
                db,
                messages=messages,
                model=model,
                temperature=temperature,
                top_p=top_p,
                max_tokens=int(max_tokens) if max_tokens else None,
                stop=[str(s) for s in stop] if isinstance(stop, list) else None,
                stream=stream,
            )
    except DirectLLMError as exc:
        return _error(str(exc), 502, "anthropic")

    if not stream:
        text = direct.extract_text(result)
        reasoning = direct.extract_reasoning(result)
        usage = direct.extract_usage(result)
        finish = direct.extract_finish_reason(result)
        return JSONResponse(
            status_code=200,
            content=_openai_to_anthropic_response(
                text=text, reasoning=reasoning, usage=usage, model=model_name, finish_reason=finish
            ),
        )

    async def event_stream() -> AsyncIterator[bytes]:
        """Anthropic SSE：message_start → content_block_delta* → message_stop。"""
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        yield f"event: message_start\ndata: {json.dumps({'type': 'message_start', 'message': {'id': msg_id, 'type': 'message', 'role': 'assistant', 'model': model_name, 'content': [], 'stop_reason': None, 'usage': {'input_tokens': 0, 'output_tokens': 0}}}, ensure_ascii=False)}\n\n".encode()

        # content_block 必须是完整 block：TextBlock 的 text 是必填，
        # 少给字段客户端会解析失败。
        yield f"event: content_block_start\ndata: {json.dumps({'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}, ensure_ascii=False)}\n\n".encode()

        output_chars = 0
        try:
            async for chunk in result:
                delta = _chunk_delta_text(chunk)
                if delta:
                    output_chars += len(delta)
                    yield f"event: content_block_delta\ndata: {json.dumps({'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': delta}}, ensure_ascii=False)}\n\n".encode()
        except Exception as exc:  # noqa: BLE001
            logger.warning("anthropic stream failed", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': str(exc)}}, ensure_ascii=False)}\n\n".encode()

        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0}, ensure_ascii=False)}\n\n".encode()
        # MessageDeltaUsage 的 output_tokens 是**必填**（anthropic SDK 要求）。
        # 原来传空对象 {} 会让客户端解析失败。这里用累计字符数近似，
        # 精确 token 数需要上游返回 —— 直通通道没拿到就不该编造。
        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': output_chars}}, ensure_ascii=False)}\n\n".encode()
        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop'}, ensure_ascii=False)}\n\n".encode()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chunk_delta_text(chunk: Any) -> str:
    """从流式 chunk 里取增量文本。

    统一走 ``direct.chunk_text`` —— wuwei 的 chunk 是扁平 content，
    与 OpenAI 的 choices[0].delta.content 不同。两处实现容易漂移，所以只留一份。
    """
    from app.services.llm_providers.direct import chunk_text

    return chunk_text(chunk)

# ---------------------------------------------------------------------------
# OpenAI Responses API
# ---------------------------------------------------------------------------


def _responses_input_to_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Responses API 的 input → OpenAI messages。

    Responses 的 ``input`` 可以是字符串，也可以是 item 数组
    （``{"type": "message", "role": "user", "content": [...]}``）。
    """
    messages: list[dict[str, Any]] = []

    instructions = body.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    raw_input = body.get("input")
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
    elif isinstance(raw_input, list):
        for item in raw_input:
            if isinstance(item, str):
                messages.append({"role": "user", "content": item})
                continue
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "user")
            content = item.get("content")
            if isinstance(content, str):
                messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                parts = [
                    str(b.get("text") or "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") in ("input_text", "text")
                ]
                messages.append({"role": role, "content": "".join(p for p in parts if p)})
    return messages


def _to_responses_output(
    *, text: str, reasoning: str, usage: dict[str, int], model: str, finish_reason: str
) -> dict[str, Any]:
    """OpenAI 结果 → Responses API 响应形状。

    字段按 openai 3.40.0 的 ``Response`` 模型核对过 —— 必填项一个都不能少，
    否则客户端 Pydantic 解析直接失败：
      id / created_at / model / object / output / parallel_tool_calls /
      tool_choice / tools
    以及 usage 的两个 details 子结构。
    """
    output: list[dict[str, Any]] = []
    if reasoning:
        output.append({
            "type": "reasoning",
            "id": f"rs_{uuid.uuid4().hex[:24]}",
            # ResponseReasoningItem 的 summary 是必填 List；content 可选。
            # 我们转发的是原始推理文本，不是官方 summary 摘要，
            # 所以 summary 留空、正文放 content。
            "summary": [],
            "content": [{"type": "reasoning_text", "text": reasoning}],
        })
    output.append({
        "type": "message",
        "id": f"msg_{uuid.uuid4().hex[:24]}",
        "status": "completed",
        "role": "assistant",
        # ResponseOutputText 必填 annotations；type 是 output_text
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    })

    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", 0) or (prompt + completion)

    return {
        "id": f"resp_{uuid.uuid4().hex[:24]}",
        "object": "response",
        # Response.created_at 是 float（不是 int）
        "created_at": time.time(),
        "status": "completed" if finish_reason != "length" else "incomplete",
        "model": model,
        "output": output,
        # 以下是 Response 的必填字段，缺任何一个客户端都会解析失败
        "parallel_tool_calls": False,
        "tool_choice": "none",
        "tools": [],
        "output_text": text,
        "usage": {
            "input_tokens": prompt,
            "output_tokens": completion,
            "total_tokens": total,
            # 两个 details 子结构都是必填
            "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
        "incomplete_details": (
            {"reason": "max_output_tokens"} if finish_reason == "length" else None
        ),
    }


@router.post("/v1/responses")
async def openai_responses(request: Request):
    """OpenAI Responses API 兼容端点。"""
    api_key = _extract_api_key(request)
    user = authenticate_api_key(api_key)
    if user is None:
        return _unauthorized()

    try:
        body = await request.json()
    except Exception:
        return _error("Invalid JSON body")

    messages = _responses_input_to_messages(body)
    if not messages:
        return _error("input 不能为空")

    model = _strip_llm_prefix(str(body.get("model") or ""))
    stream = bool(body.get("stream"))
    max_output = body.get("max_output_tokens") or body.get("max_tokens")
    temperature = body.get("temperature")
    top_p = body.get("top_p")

    from app.db.session import create_db_session
    from app.services.llm_providers import direct
    from app.services.llm_providers.direct import DirectLLMError

    try:
        with create_db_session() as db:
            gateway, model_name, result = await direct.complete(
                db,
                messages=messages,
                model=model,
                temperature=temperature,
                top_p=top_p,
                max_tokens=int(max_output) if max_output else None,
                stream=stream,
            )
    except DirectLLMError as exc:
        return _error(str(exc), 502)

    if not stream:
        text = direct.extract_text(result)
        reasoning = direct.extract_reasoning(result)
        usage = direct.extract_usage(result)
        finish = direct.extract_finish_reason(result)
        return JSONResponse(
            status_code=200,
            content=_to_responses_output(
                text=text, reasoning=reasoning, usage=usage, model=model_name, finish_reason=finish
            ),
        )

    async def event_stream() -> AsyncIterator[bytes]:
        """Responses SSE。

        事件结构按 openai SDK 核对：每个事件都要 ``sequence_number``
        （单调递增），text delta 还要 item_id / output_index /
        content_index / logprobs。缺这些字段客户端会解析失败。
        """
        resp_id = f"resp_{uuid.uuid4().hex[:24]}"
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        seq = 0

        def _ev(name: str, payload: dict[str, Any]) -> bytes:
            nonlocal seq
            payload["sequence_number"] = seq
            seq += 1
            return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n".encode()

        # 1) response.created —— response 必须是完整 Response 对象
        created_resp = _to_responses_output(
            text="", reasoning="",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            model=model_name, finish_reason="stop",
        )
        created_resp["id"] = resp_id
        created_resp["status"] = "in_progress"
        # output 必须是空数组：SDK 在 created 阶段就会把 response.output
        # 里的 item 记入 _output_items，之后再发 output_item.added 会撞
        # 索引并抛 ``Duplicate response output index``。
        created_resp["output"] = []
        created_resp["output_text"] = ""
        yield _ev("response.created", {"type": "response.created", "response": created_resp})

        # 2) output_item.added —— 声明一个 message item
        yield _ev("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "type": "message", "id": msg_id, "status": "in_progress",
                "role": "assistant", "content": [],
            },
        })

        # 3) content_part.added
        yield _ev("response.content_part.added", {
            "type": "response.content_part.added",
            "item_id": msg_id, "output_index": 0, "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        })

        text_parts: list[str] = []
        try:
            async for chunk in result:
                delta = _chunk_delta_text(chunk)
                if not delta:
                    continue
                text_parts.append(delta)
                yield _ev("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": msg_id,
                    "output_index": 0,
                    "content_index": 0,
                    "delta": delta,
                    "logprobs": [],
                })
        except Exception as exc:  # noqa: BLE001
            logger.warning("responses stream failed", exc_info=True)
            failed = _to_responses_output(
                text="".join(text_parts), reasoning="",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                model=model_name, finish_reason="stop",
            )
            failed["id"] = resp_id
            failed["status"] = "failed"
            failed["error"] = {"code": "stream_error", "message": str(exc)}
            yield _ev("response.failed", {"type": "response.failed", "response": failed})
            return

        final_text = "".join(text_parts)

        # 4) output_text.done
        yield _ev("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": msg_id, "output_index": 0, "content_index": 0,
            "text": final_text, "logprobs": [],
        })

        # 5) content_part.done
        yield _ev("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": msg_id, "output_index": 0, "content_index": 0,
            "part": {"type": "output_text", "text": final_text, "annotations": []},
        })

        # 6) output_item.done
        yield _ev("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": {
                "type": "message", "id": msg_id, "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": final_text, "annotations": []}],
            },
        })

        # 7) response.completed —— 完整 Response
        #
        # 关键：final 里的 output item id 必须与流中 added/done 用过的
        # msg_id 一致。SDK 会按 identity 累积 output item，id 不一致直接抛
        # ``Response snapshot has conflicting output identities``。
        final = _to_responses_output(
            text=final_text, reasoning="",
            usage={"prompt_tokens": 0, "completion_tokens": len(final_text), "total_tokens": len(final_text)},
            model=model_name, finish_reason="stop",
        )
        final["id"] = resp_id
        for item in final.get("output") or []:
            if item.get("type") == "message":
                item["id"] = msg_id
        yield _ev("response.completed", {"type": "response.completed", "response": final})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
