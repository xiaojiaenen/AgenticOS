"""内网爬虫服务 —— 独立进程的骨架。

这个服务**刻意不复用主项目的任何代码**：它有自己的依赖、自己的镜像、
自己的配置。原因是内网环境往往有特殊要求（自签 CA、内网 DNS、内网代理、
特定版本的浏览器），混进主项目会污染外网部署的依赖树。

主项目通过 HTTP 调用它（见 ``backend/app/services/intranet_client.py``）。
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse, urljoin

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

# ── 配置 ────────────────────────────────────────────────────────────────────

SERVICE_TOKEN = os.environ.get("INTRANET_SERVICE_TOKEN", "").strip()
ALLOWED_CIDRS = os.environ.get("INTRANET_ALLOWED_CIDRS", "").strip()
EGRESS_ALLOWLIST = os.environ.get("INTRANET_EGRESS_ALLOWLIST", "").strip()
REQUEST_TIMEOUT = int(os.environ.get("INTRANET_REQUEST_TIMEOUT", "30"))
MAX_CHARS = int(os.environ.get("INTRANET_MAX_CHARS", "20000"))
# 内网自签证书：默认放行（内网场景常见），可关
VERIFY_TLS = os.environ.get("INTRANET_VERIFY_TLS", "false").lower() == "true"

BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "100.100.100.200",
}

app = FastAPI(title="AgenticOS Intranet Crawler", version="1.0.0")


# ── 策略（SSRF 防护）───────────────────────────────────────────────────────


def _parse_cidrs(raw: str) -> list:
    nets = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            nets.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            continue
    return nets


def _resolve(host: str) -> list:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    out = []
    for info in infos:
        try:
            out.append(ipaddress.ip_address(info[4][0]))
        except ValueError:
            continue
    return out


def guard(url: str) -> None:
    """默认拒绝：只有落在允许网段内的目标才放行。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, f"不支持的协议：{parsed.scheme}")
    host = (parsed.hostname or "").strip()
    if not host:
        raise HTTPException(400, "URL 缺少主机名")
    if host.lower() in BLOCKED_HOSTS:
        raise HTTPException(403, f"禁止访问：{host}")

    egress = _parse_cidrs(EGRESS_ALLOWLIST)
    egress_names = {
        c.strip().lower()
        for c in EGRESS_ALLOWLIST.split(",")
        if c.strip() and "/" not in c.strip()
    }
    if host.lower() in egress_names:
        return

    nets = _parse_cidrs(ALLOWED_CIDRS)
    if not nets:
        raise HTTPException(
            403, "未配置 INTRANET_ALLOWED_CIDRS，内网访问默认禁止"
        )

    ips = _resolve(host)
    if not ips:
        raise HTTPException(400, f"域名无法解析：{host}")
    for ip in ips:
        if any(ip in n for n in egress):
            return
        if not any(ip in n for n in nets):
            raise HTTPException(
                403, f"目标 {ip} 不在允许网段内（INTRANET_ALLOWED_CIDRS）"
            )


def _auth(authorization: str | None) -> None:
    if not SERVICE_TOKEN:
        return
    expected = f"Bearer {SERVICE_TOKEN}"
    if (authorization or "") != expected:
        raise HTTPException(401, "服务间 token 无效")


# ── 请求模型 ────────────────────────────────────────────────────────────────


class FetchRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    max_chars: int | None = None


class BrowseRequest(BaseModel):
    url: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    extract: str | None = None
    wait_for: str | None = None
    max_chars: int | None = None


class ExtractRequest(BaseModel):
    html: str
    table_selector: str | None = None
    fields: list[str] = Field(default_factory=list)


class SubmitRequest(BaseModel):
    url: str
    method: str = "POST"
    fields: dict[str, str] = Field(default_factory=dict)


# ── 端点 ────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "intranet-crawler",
        "allowed_cidrs": ALLOWED_CIDRS or "(未配置)",
        "egress": EGRESS_ALLOWLIST or "(无)",
    }


@app.post("/probe")
async def probe(body: FetchRequest, authorization: str | None = Header(None)):
    _auth(authorization)
    guard(body.url)
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, verify=VERIFY_TLS, follow_redirects=False
        ) as client:
            resp = await client.get(body.url)
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"请求失败：{exc}"}

    ctype = resp.headers.get("content-type", "")
    text = resp.text[:MAX_CHARS]
    lowered = text.lower()

    return {
        "ok": True,
        "status_code": resp.status_code,
        "content_type": ctype,
        "is_json": "json" in ctype.lower(),
        "requires_login": _looks_like_login(lowered, resp.status_code),
        "likely_js_rendered": (
            "text/html" in ctype.lower()
            and len(text) < 2000
            and ("<div id=\"app\"" in lowered or "<div id='app'" in lowered)
        ),
        "has_form": "<form" in lowered,
        "has_table": "<table" in lowered,
        "title": _extract_title(text),
        "content_length": len(text),
    }


@app.post("/fetch")
async def fetch(body: FetchRequest, authorization: str | None = Header(None)):
    _auth(authorization)
    guard(body.url)
    limit = min(body.max_chars or MAX_CHARS, MAX_CHARS)

    headers = {k: v for k, v in body.headers.items() if k.lower() != "host"}
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            verify=VERIFY_TLS,
            follow_redirects=False,
            headers=headers,
        ) as client:
            resp = await client.request(
                body.method.upper(), body.url, content=body.body
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"请求失败：{exc}"}

    text = resp.text
    return {
        "ok": True,
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "truncated": len(text) > limit,
        "content": text[:limit],
    }


@app.post("/browse")
async def browse(body: BrowseRequest, authorization: str | None = Header(None)):
    _auth(authorization)
    guard(body.url)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "未安装 Playwright，无法启动无头浏览器"}

    limit = min(body.max_chars or MAX_CHARS, MAX_CHARS)
    try:
        async with async_playwright() as pw:
            # ignore_https_errors 是 **context** 的参数，不是 launch 的参数 ——
            # 放到 launch 上会直接 TypeError。内网自签证书必须在这里放行。
            browser = await pw.chromium.launch(headless=True)
            # context 必须关闭 —— 旧实现的几条 early-return 分支漏掉 close()
            # 会让容器里累积僵尸 Chromium。
            context = await browser.new_context(ignore_https_errors=not VERIFY_TLS)
            try:
                page = await context.new_page()
                await page.goto(body.url, timeout=REQUEST_TIMEOUT * 1000)

                if body.wait_for:
                    await page.wait_for_selector(body.wait_for, timeout=15000)

                for action in body.actions:
                    ok = await _run_action(page, action)
                    if not ok:
                        return {
                            "ok": False,
                            "error": f"动作执行失败：{action}",
                            "page_snapshot": (await page.content())[:limit],
                        }

                if body.extract:
                    el = await page.query_selector(body.extract)
                    if el is None:
                        return {"ok": False, "error": f"未找到元素：{body.extract}"}
                    text = (await el.inner_text())[:limit]
                    return {"ok": True, "extracted": text}

                return {
                    "ok": True,
                    "title": await page.title(),
                    "url": page.url,
                    "content": (await page.content())[:limit],
                }
            finally:
                await context.close()
                await browser.close()
    except Exception as exc:  # noqa: BLE001 —— 浏览器异常种类繁多
        return {"ok": False, "error": f"浏览器操作失败：{exc}"}


async def _run_action(page, action: dict[str, Any]) -> bool:
    kind = (action.get("type") or "").lower()
    selector = action.get("selector")
    try:
        if kind == "click":
            await page.click(selector, timeout=10000)
        elif kind == "fill":
            await page.fill(selector, str(action.get("value") or ""), timeout=10000)
        elif kind == "select":
            await page.select_option(selector, action.get("value"), timeout=10000)
        elif kind == "submit":
            await page.click(selector, timeout=10000)
        elif kind == "wait":
            await page.wait_for_timeout(int(action.get("ms") or 1000))
        elif kind == "wait_for":
            await page.wait_for_selector(selector, timeout=15000)
        elif kind == "screenshot":
            await page.screenshot(path=action.get("path") or "shot.png")
        else:
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


@app.post("/extract")
async def extract(body: ExtractRequest, authorization: str | None = Header(None)):
    _auth(authorization)

    rows = _extract_rows(body.html, body.table_selector)
    if body.fields:
        wanted = {f.strip().lower() for f in body.fields}
        rows = [
            {k: v for k, v in row.items() if k.strip().lower() in wanted}
            for row in rows
        ]
    return {"ok": True, "rows": rows, "row_count": len(rows)}


@app.post("/submit")
async def submit(body: SubmitRequest, authorization: str | None = Header(None)):
    _auth(authorization)
    guard(body.url)
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, verify=VERIFY_TLS, follow_redirects=False
        ) as client:
            resp = await client.request(
                body.method.upper(), body.url, data=body.fields
            )
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"提交失败：{exc}"}

    return {
        "ok": resp.status_code < 400,
        "status_code": resp.status_code,
        "location": resp.headers.get("location", ""),
        "body_excerpt": resp.text[:2000],
    }


# ── 抽取辅助 ────────────────────────────────────────────────────────────────

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", fragment)).strip()


def _extract_rows(html: str, selector: str | None) -> list[dict[str, str]]:
    """把 HTML 表格抽成行字典。

    不引第三方解析库 —— 内网服务要尽量少依赖（少一个装不上的包，
    就少一次部署失败）。
    """
    if selector:
        # 简化处理：只支持形如 table#id / table.class 的粗粒度定位
        match = re.search(
            rf"<{selector.split()[0]}[^>]*>.*?</{selector.split()[0]}>",
            html,
            re.IGNORECASE | re.DOTALL,
        )
        scope = match.group(0) if match else html
    else:
        scope = html

    rows: list[dict[str, str]] = []
    headers: list[str] | None = None
    for row_html in _ROW_RE.findall(scope):
        cells = [_clean(c) for c in _CELL_RE.findall(row_html)]
        if not cells:
            continue
        if headers is None:
            headers = cells
            continue
        rows.append(
            {headers[i] if i < len(headers) else f"col{i}": cell
             for i, cell in enumerate(cells)}
        )
    return rows


def _looks_like_login(text: str, status: int) -> bool:
    if status in (401, 403):
        return True
    markers = (
        "<form", "type=\"password\"", "type='password'",
        "登录", "sign in", "login",
    )
    return any(m in text for m in markers)


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _clean(match.group(1)) if match else ""
