"""请求唯一上游 https://agents.gree.com（Cookie 登录态）。"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.upstream import credential_store
from app.services.upstream.login_orchestrator import perform_auto_login

logger = logging.getLogger("agenticos.upstream.client")


class UpstreamAuthError(RuntimeError):
    """上游 Cookie 无效或缺失。"""


class UpstreamClient:
    """带用户 Cookie 的上游 HTTP 客户端。"""

    def __init__(self, *, base_url: str | None = None, timeout: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.upstream_base_url or "https://agents.gree.com").rstrip("/")
        self.timeout = timeout or float(settings.llm_timeout or 60)

    def _headers(self, cookie: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Cookie": cookie,
            "Content-Type": "application/json",
            "User-Agent": "AgenticOS-UpstreamClient/1.0",
        }
        if extra:
            headers.update(extra)
        return headers

    async def request(
        self,
        user_id: int,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_login_on_auth_error: bool = True,
    ) -> httpx.Response:
        cookie = credential_store.get_active_cookie(user_id)
        if not cookie:
            if retry_login_on_auth_error:
                result = await perform_auto_login(user_id)
                if not result.get("success"):
                    raise UpstreamAuthError(result.get("message") or "上游自动登录失败")
                cookie = credential_store.get_active_cookie(user_id)
            if not cookie:
                raise UpstreamAuthError("上游 Cookie 不可用，请重新登录")

        url = path if path.startswith("http") else f"{self.base_url}{path if path.startswith('/') else '/' + path}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.request(
                method.upper(),
                url,
                json=json_body,
                headers=self._headers(cookie, headers),
            )

        # Cookie 失效：标记并触发一次自动登录后重试
        if resp.status_code in {401, 403} and retry_login_on_auth_error:
            logger.info(f"upstream auth failed user={user_id} status={resp.status_code}, re-login")
            credential_store.apply_login_result(
                user_id,
                success=False,
                cookie=None,
                expire_at=None,
                error=f"upstream HTTP {resp.status_code}",
            )
            result = await perform_auto_login(user_id)
            if result.get("success"):
                return await self.request(
                    user_id,
                    method,
                    path,
                    json_body=json_body,
                    headers=headers,
                    retry_login_on_auth_error=False,
                )

        return resp

    async def chat_completions(
        self,
        user_id: int,
        *,
        model: str,
        messages: list[dict[str, Any]],
        stream: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any] | httpx.Response:
        """OpenAI 兼容 /v1/chat/completions（Cookie 认证）。"""
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if extra:
            body.update(extra)

        path = "/v1/chat/completions"
        if stream:
            return await self.request(user_id, "POST", path, json_body=body)

        resp = await self.request(user_id, "POST", path, json_body=body)
        try:
            data = resp.json()
        except Exception:
            data = {"error": {"message": resp.text[:500], "status_code": resp.status_code}}
        if resp.status_code >= 400:
            raise UpstreamAuthError(
                f"上游 chat.completions 失败 HTTP {resp.status_code}: {json.dumps(data, ensure_ascii=False)[:300]}"
            )
        return data

    async def list_models(self, user_id: int) -> dict[str, Any]:
        resp = await self.request(user_id, "GET", "/v1/models")
        try:
            return resp.json()
        except Exception:
            return {"error": resp.text[:300], "status_code": resp.status_code}

    async def health(self, user_id: int | None = None) -> dict[str, Any]:
        """探测上游可达性；有 user_id 时同时校验 cookie。"""
        info: dict[str, Any] = {
            "base_url": self.base_url,
            "login_url": credential_store.get_upstream_login_url(),
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(self.base_url)
            info["reachable"] = resp.status_code < 500
            info["http_status"] = resp.status_code
        except Exception as e:
            info["reachable"] = False
            info["error"] = str(e)[:200]
        if user_id is not None:
            cookie = credential_store.get_active_cookie(user_id)
            info["has_cookie"] = bool(cookie)
            if cookie:
                try:
                    models = await self.list_models(user_id)
                    info["models_ok"] = "data" in models or "error" not in models
                except Exception as e:
                    info["models_ok"] = False
                    info["models_error"] = str(e)[:200]
        return info


def get_upstream_client() -> UpstreamClient:
    return UpstreamClient()
