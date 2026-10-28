"""从上游拉取模型清单并归一化。

上游的模型清单有两种形态，语义完全不同：

- **标准 OpenAI 兼容** ``GET /models`` → ``{"data": [{"id": "gpt-4o"}]}``。
  ``id`` 就是请求体里要填的模型名。
- **静态注册表**（百通 ``/json/model-configs.json``）→ 每个模型有 ``model``
  （ID）和 ``name``（请求体里要填的名字）两套标识，还带 ``taskType``、
  ``maxTokens``、推荐采样参数。

把两者归一成同一张表之后，界面才能做到「选模型而不是背模型名」，也才能在
调用报 404 之前就发现「你填的是 ID 不是 name」。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.services.llm_providers.presets import (
    TransportOptions,
    origin_of,
    resolve_probe,
    resolve_transport,
)

logger = logging.getLogger("agenticos.llm.discovery")

# 归一后的任务类型。上游用词不统一，这里只保留四类，便于界面按用途分组。
TASK_TEXT = "text-generation"
TASK_VISION = "image-text-to-text"
TASK_IMAGE = "text-to-image"
TASK_OMNI = "any-to-any"

_TASK_ALIASES = {
    "text-generation": TASK_TEXT,
    "chat": TASK_TEXT,
    "completion": TASK_TEXT,
    "image-text-to-text": TASK_VISION,
    "vision": TASK_VISION,
    "text-to-image": TASK_IMAGE,
    "image": TASK_IMAGE,
    "any-to-any": TASK_OMNI,
    "omni": TASK_OMNI,
}

# 注册表里 body 携带的是「上游推荐的请求体默认值」，不是配置项。
# 只挑出 OpenAI 认识的采样参数，其余（model / stream / enable_thinking）
# 分别由 provider.model、调用方、transport.extra_body 负责。
_SAMPLING_KEYS = ("temperature", "top_p", "presence_penalty", "frequency_penalty", "seed")


@dataclass
class DiscoveredModel:
    model_key: str
    model_name: str
    task_type: str = TASK_TEXT
    max_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_key": self.model_key,
            "model_name": self.model_name,
            "task_type": self.task_type,
            "max_tokens": self.max_tokens,
            "extra": self.extra,
        }


def _normalize_task(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return _TASK_ALIASES.get(value, value or TASK_TEXT)


def _sampling_from_body(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    return {key: body[key] for key in _SAMPLING_KEYS if key in body}


def parse_gree_registry(payload: Any) -> list[DiscoveredModel]:
    """百通注册表。

    结构：``{"default": {...}, "models": {"<模型ID>": {...}}}``。
    同一份 ``name`` 可能被多个 ID 复用（base 与 thinking 变体），因此按
    ``model_key`` 全量保留 —— 去重交给「用途绑定」那一层，那里关心的是
    name，而这里关心的是「上游到底有哪些入口」。
    """
    if not isinstance(payload, dict):
        return []
    models = payload.get("models")
    if not isinstance(models, dict):
        return []

    result: list[DiscoveredModel] = []
    for key, item in models.items():
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or key).strip()
        if not name:
            continue
        max_tokens = item.get("maxTokens") or item.get("max_tokens")
        result.append(
            DiscoveredModel(
                model_key=str(key),
                model_name=name,
                task_type=_normalize_task(item.get("taskType")),
                max_tokens=int(max_tokens) if isinstance(max_tokens, (int, float)) else None,
                extra=_sampling_from_body(item.get("body")),
            )
        )
    return result


def parse_openai_models(payload: Any) -> list[DiscoveredModel]:
    """标准 ``/models`` 响应。``id`` 同时充当 key 与 name。"""
    items: Any = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []

    result: list[DiscoveredModel] = []
    for item in items:
        if isinstance(item, str):
            model_id = item.strip()
            task = TASK_TEXT
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
            task = _normalize_task(item.get("task_type") or item.get("type") or TASK_TEXT)
        else:
            continue
        if not model_id:
            continue
        result.append(DiscoveredModel(model_key=model_id, model_name=model_id, task_type=task))
    return result


_PARSERS = {
    "gree_registry": parse_gree_registry,
    "openai_models": parse_openai_models,
}


def parse_models_payload(payload: Any, *, parser: str = "openai_models") -> list[dict[str, Any]]:
    """给探测阶段用的轻量入口：返回 dict 列表，不落库。"""
    func = _PARSERS.get(parser) or parse_openai_models
    return [item.as_dict() for item in func(payload)]


def _discovery_url(base_url: str, path: str, scope: str) -> str:
    base = base_url.rstrip("/")
    if scope == "origin":
        base = origin_of(base_url) or base
    return f"{base}{path}"


async def fetch_models(
    *,
    base_url: str,
    extra: dict[str, Any],
    cookie: str | None = None,
    api_key: str | None = None,
    timeout: float = 20.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """拉取并解析模型清单。

    返回 ``(models, meta)``。失败时 ``models`` 为空、``meta`` 带原因，让调用方
    能把「网络不通 / 认证失败 / 返回格式不认识」区分开 —— 这三种在界面上
    完全该给不同的处理建议。
    """
    probe = resolve_probe(extra)
    transport: TransportOptions = resolve_transport(extra)
    url = _discovery_url(base_url, probe.path, probe.scope)

    headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            if transport.browser_user_agent
            else "AgenticOS/1.0"
        )
    }
    if cookie:
        headers["Cookie"] = cookie
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=not transport.insecure_tls, follow_redirects=True
        ) as client:
            response = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return [], {"ok": False, "url": url, "stage": "network", "message": str(exc)[:300]}

    if response.status_code >= 400:
        return [], {
            "ok": False,
            "url": url,
            "stage": "auth" if response.status_code in (401, 403) else "http",
            "status_code": response.status_code,
            "message": response.text[:300] or f"HTTP {response.status_code}",
        }

    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return [], {
            "ok": False,
            "url": url,
            "stage": "format",
            "status_code": response.status_code,
            "message": "返回不是 JSON，可能打到了前端 catch-all 页面，检查 base_url 前缀",
        }

    models = parse_models_payload(payload, parser=probe.parser)
    if not models:
        return [], {
            "ok": False,
            "url": url,
            "stage": "format",
            "status_code": response.status_code,
            "message": f"HTTP 200 但解析不出模型（parser={probe.parser}）",
        }
    return models, {"ok": True, "url": url, "status_code": response.status_code, "count": len(models)}
