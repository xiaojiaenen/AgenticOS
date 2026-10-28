"""内网爬虫客户端（主项目侧）。

主项目**不包含任何爬虫实现** —— Playwright、解析逻辑、内网证书都在
独立进程里（见 ``deploy/intranet/``）。这里只做三件事：

1. 参数校验与占位符解析（``$CREDENTIAL.x`` / ``$INPUT.x``）；
2. 把请求转成 HTTP 调用内网爬虫服务；
3. 把内网服务的结构化结果翻译成模型看得懂的工具返回值。

**没配 ``INTRANET_SERVICE_URL`` 时**，所有工具返回「服务未启用」——
外网部署的行为与没有这个模块时完全一致。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.intranet_policy import check_url

logger = logging.getLogger("agenticos.intranet")

# 占位符：$CREDENTIAL.<字段> / $INPUT.<字段>
#
# 字段名只允许字母数字和下划线 —— **不含连字符**：连字符在
# "$CREDENTIAL.a-$CREDENTIAL.b" 这类拼接值里会被误当成字段名的一部分，
# 导致第一个占位符解析成 "a-" 而不是 "a"。
_PLACEHOLDER_RE = re.compile(r"\$(CREDENTIAL|INPUT)\.([A-Za-z0-9_]+)")

# 凭据类字段不进日志、不进审计
_CREDENTIAL_MARKERS = ("password", "passwd", "pwd", "secret", "token", "cookie")


class IntranetUnavailable(RuntimeError):
    """内网爬虫服务未启用或不可达。"""


def service_url() -> str:
    return (get_settings().intranet_service_url or "").strip()


def is_enabled() -> bool:
    return bool(service_url())


def _service_token() -> str:
    return (get_settings().intranet_service_token or "").strip()


def _redact(value: str) -> str:
    """把看起来像凭据的值在日志里打码。"""
    low = value.lower()
    if any(m in low for m in _CREDENTIAL_MARKERS):
        return "***"
    return value


def resolve_placeholders(
    values: dict[str, Any],
    *,
    credentials: dict[str, str] | None = None,
    inputs: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """解析 ``$CREDENTIAL.x`` / ``$INPUT.x`` 占位符。

    返回 ``(解析后的值, 缺失的字段列表)``。**凭据值不会进入返回值之外的
    任何通道** —— 调用方只把它塞进 HTTP 请求体，不写日志、不进审计。

    缺失的字段返回给上层，由上层决定是问用户（``$INPUT``）还是提示去
    配置集成（``$CREDENTIAL``）。
    """
    creds = credentials or {}
    ins = inputs or {}
    missing: list[str] = []
    resolved: dict[str, Any] = {}

    for key, raw in values.items():
        if not isinstance(raw, str):
            resolved[key] = raw
            continue

        def _sub(match: re.Match[str]) -> str:
            scope, field = match.group(1), match.group(2)
            source = creds if scope == "CREDENTIAL" else ins
            if field in source:
                return str(source[field])
            missing.append(f"{scope}.{field}")
            return match.group(0)

        resolved[key] = _PLACEHOLDER_RE.sub(_sub, raw)

    return resolved, missing


async def call_service(
    path: str,
    payload: dict[str, Any],
    *,
    timeout: int | None = None,
) -> dict[str, Any]:
    """调用内网爬虫服务的某个端点。"""
    base = service_url()
    if not base:
        raise IntranetUnavailable(
            "内网爬虫服务未启用。请配置 INTRANET_SERVICE_URL 后重启服务。"
        )

    settings = get_settings()
    timeout = timeout or settings.intranet_request_timeout
    headers = {"Content-Type": "application/json"}
    token = _service_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{base.rstrip('/')}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise IntranetUnavailable(f"内网爬虫服务超时（{timeout}s）：{exc}") from exc
    except httpx.HTTPError as exc:
        raise IntranetUnavailable(f"内网爬虫服务不可达：{exc}") from exc

    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise IntranetUnavailable(
            f"内网爬虫服务返回 {resp.status_code}：{detail}"
        )

    try:
        data = resp.json()
    except json.JSONDecodeError:
        return {"ok": False, "error": "内网爬虫服务返回了非 JSON 响应"}
    return data if isinstance(data, dict) else {"ok": False, "error": "响应格式异常"}


def guard_url(url: str) -> None:
    """按策略检查 URL，不通过就抛错。"""
    settings = get_settings()
    decision = check_url(
        url,
        allowed_cidrs=settings.intranet_allowed_cidrs,
        egress_allowlist=settings.intranet_egress_allowlist,
    )
    if not decision.allowed:
        raise PermissionError(f"该地址不在允许访问范围内：{decision.reason}")


def disabled_message() -> str:
    return (
        "内网爬虫服务未启用。\n"
        "该能力需要单独部署内网爬虫容器（见 deploy/intranet/），"
        "并配置环境变量 INTRANET_SERVICE_URL。"
    )
