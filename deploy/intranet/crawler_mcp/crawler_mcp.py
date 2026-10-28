"""内网爬虫 MCP 服务 —— 参考实现（你可以直接复制改写）。

这个文件演示「你的爬虫代码」该怎么组织，才能被 AgenticOS 当作插件接进来。

## 核心约定

**你的爬虫 = 一个独立进程 + MCP 协议**。主项目只当客户端，不碰你的代码。

因此：

- 你的代码、依赖（Playwright / 抓取库）、浏览器、内网证书、内网 DNS
  全在这个进程里 —— 主项目的依赖树一点不沾，外网部署完全不受影响。
- 工具的名字、参数、描述**由你定义**。AgenticOS 只负责发现并转发。
- 换爬虫实现（改选择器、改站点逻辑）不需要改主项目代码，重新连接即可。

## 三个必须注意的约定

### 1. 凭据用 ``$CREDENTIAL.<字段>`` 占位，不要让模型直接填

工具参数里写占位符：

    def fetch_report(url: str, token: str = "$CREDENTIAL.report_token"): ...

AgenticOS 在调用前把它替换成**当前用户自己配置的**凭据。
凭据值不会进模型上下文，也不会进审计日志。

没配凭据时，平台会返回「请在集成页配置凭据」的提示。

**占位符可以放在任意嵌套位置**，平台会递归解析：

    headers={"X-Token": "$CREDENTIAL.report_token"}          # dict
    fields=[{"name": "user", "value": "$CREDENTIAL.username"}]  # list[dict]

**推荐写成参数默认值**（如上 `token: str = "$CREDENTIAL.report_token"`）：
模型不会主动填这个参数，但平台会从工具的 inputSchema 里把默认值取出来
替换掉 —— 写成必填参数的话，模型反而会自己编一个值填进去。

### 2. 一次性输入用 ``$INPUT.<字段>`` 占位

验证码、临时口令这类既不该落库也不该让模型编造的值：

    def submit_code(sms: str = "$INPUT.sms_code"): ...

平台会弹出表单问用户，拿到真实值后再调用。

### 3. 只读工具要声明 ``readOnlyHint``

平台据此决定是否需要人工审批：

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True))

写操作（提交、审批、删除）不要声明 → 平台会要求人工确认。

## 跑起来

    pip install "mcp>=2.2,<3" httpx
    python crawler_mcp.py

默认监听 ``127.0.0.1:8931/mcp``（streamable http）。
然后在 AgenticOS 的「管理后台 → 集成管理 → MCP 服务器」里加一条：

- 名称：``intranet_crawler``
- 传输：``http``
- 地址：``http://127.0.0.1:8931/mcp``

内网自签证书的话，勾上「放行自签证书」。
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

# ── 配置 ────────────────────────────────────────────────────────────────────

HOST = os.environ.get("CRAWLER_HOST", "127.0.0.1")
PORT = int(os.environ.get("CRAWLER_PORT", "8931"))

# 出网网段白名单（逗号分隔 CIDR）。留空 = 不限制。
# 内网爬虫的本质就是「让服务器访问任意地址」—— 这正是 SSRF 的定义。
# 没有这层防护，一个被诱导的模型就能用你的服务探测整个内网，
# 甚至打云元数据接口（169.254.169.254）拿实例凭据。
ALLOWED_CIDRS = os.environ.get("CRAWLER_ALLOWED_CIDRS", "").strip()
REQUEST_TIMEOUT = float(os.environ.get("CRAWLER_TIMEOUT", "30"))
MAX_CHARS = int(os.environ.get("CRAWLER_MAX_CHARS", "20000"))

# 云厂商元数据地址：任何情况下都禁止（即使网段白名单写得很宽）
BLOCKED_HOSTS = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.goog",
    "100.100.100.200",
}

server = MCPServer(
    name="intranet-crawler",
    version="1.0.0",
    instructions=(
        "内网站点数据抓取服务。访问目标站点前会校验网段白名单，"
        "越界目标会被拒绝。凭据用 $CREDENTIAL.<字段> 占位，"
        "平台会在调用前注入当前用户的凭据。"
    ),
)


# ── SSRF 防护 ───────────────────────────────────────────────────────────────


def _parse_cidrs(raw: str) -> list:
    import ipaddress

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
    import ipaddress
    import socket

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
    """默认拒绝：只有落在允许网段内的目标才放行。

    注意这里检查的是**所有**解析出的 IP —— 一个域名同时给出内网 IP 和外网 IP
    时（DNS rebinding），只要有一个越界就整体拒绝。
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议：{parsed.scheme}")
    host = (parsed.hostname or "").strip()
    if not host:
        raise ValueError("URL 缺少主机名")
    if host.lower() in BLOCKED_HOSTS:
        raise ValueError(f"禁止访问元数据地址：{host}")

    nets = _parse_cidrs(ALLOWED_CIDRS)
    if not nets:
        raise ValueError(
            "未配置 CRAWLER_ALLOWED_CIDRS，内网访问默认禁止。"
            "请设置允许访问的网段，例如 10.0.0.0/8,172.16.0.0/12"
        )

    ips = _resolve(host)
    if not ips:
        raise ValueError(f"域名无法解析：{host}")
    for ip in ips:
        if not any(ip in n for n in nets):
            raise ValueError(f"目标 {ip} 不在允许网段内（CRAWLER_ALLOWED_CIDRS）")


# ── 工具实现 ────────────────────────────────────────────────────────────────


@server.tool(
    name="fetch_page",
    description=(
        "抓取一个内网 URL 的内容（静态 HTML 或 JSON API）。"
        "页面由 JS 渲染时用 browse_page。"
    ),
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def fetch_page(
    url: str,
    headers: dict[str, str] | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """抓取内网页面。

    Args:
        url: 内网地址（http/https）
        headers: 附加请求头。值可写 $CREDENTIAL.<字段> 由平台注入
        max_chars: 返回正文的最大字符数
    """
    guard(url)
    limit = min(max_chars or MAX_CHARS, MAX_CHARS)
    request_headers = dict(headers or {})

    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=False
    ) as client:
        resp = await client.get(url, headers=request_headers)

    text = resp.text
    return {
        "ok": True,
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "truncated": len(text) > limit,
        "content": text[:limit],
    }


@server.tool(
    name="browse_page",
    description=(
        "用无头浏览器打开内网页面（适合 JS 渲染、需登录、带多步表单的页面）。"
        "可执行点击/输入/等待等动作，并可选提取内容。"
    ),
    # 写操作性质（可能触发登录态变更）→ 不声明 readOnlyHint，平台会要求人工确认
)
async def browse_page(
    url: str,
    actions: list[dict[str, Any]] | None = None,
    extract: str | None = None,
    wait_for: str | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """用无头浏览器访问内网页面。

    Args:
        url: 内网地址
        actions: 动作序列，例如
                 [{"type": "click", "selector": "#login"},
                  {"type": "fill", "selector": "#user", "value": "$CREDENTIAL.username"},
                  {"type": "submit", "selector": "form"}]
        extract: 提取选择器（CSS），给出该元素的可见文本
        wait_for: 等待某个选择器出现再继续
        max_chars: 返回内容最大字符数
    """
    guard(url)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"ok": False, "error": "未安装 Playwright，无法启动无头浏览器"}

    limit = min(max_chars or MAX_CHARS, MAX_CHARS)
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            # ignore_https_errors 是 **context** 的参数，不是 launch 的参数 ——
            # 放到 launch 上会直接 TypeError。内网自签证书必须在这里放行。
            context = await browser.new_context(ignore_https_errors=True)
            try:
                page = await context.new_page()
                await page.goto(url, timeout=REQUEST_TIMEOUT * 1000)

                if wait_for:
                    await page.wait_for_selector(wait_for, timeout=15000)

                for action in actions or []:
                    ok = await _run_action(page, action)
                    if not ok:
                        return {
                            "ok": False,
                            "error": f"动作执行失败：{action}",
                            "page_snapshot": (await page.content())[:limit],
                        }

                if extract:
                    el = await page.query_selector(extract)
                    if el is None:
                        return {"ok": False, "error": f"未找到元素：{extract}"}
                    return {"ok": True, "extracted": (await el.inner_text())[:limit]}

                return {
                    "ok": True,
                    "title": await page.title(),
                    "url": page.url,
                    "content": (await page.content())[:limit],
                }
            finally:
                # context 必须关闭 —— 漏掉 close() 会让容器里累积僵尸 Chromium
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
        else:
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


@server.tool(
    name="extract_table",
    description="把抓取到的 HTML 表格/列表抽取成结构化行。",
    annotations=ToolAnnotations(readOnlyHint=True),
)
async def extract_table(
    html: str,
    table_selector: str | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """从 HTML 中抽取结构化数据。

    Args:
        html: HTML 源码
        table_selector: 表格/列表的 CSS 选择器，不填则自动识别
        fields: 要保留的字段名列表（按表头匹配）
    """
    rows = _extract_rows(html, table_selector)
    if fields:
        wanted = {f.strip().lower() for f in fields}
        rows = [
            {k: v for k, v in row.items() if k.strip().lower() in wanted}
            for row in rows
        ]
    return {"ok": True, "rows": rows, "row_count": len(rows)}


@server.tool(
    name="submit_form",
    description=(
        "向内网站点提交表单（写操作，平台会要求人工确认）。"
        "字段值支持 $CREDENTIAL.<字段> / $INPUT.<字段> 占位。"
    ),
)
async def submit_form(
    url: str,
    fields: dict[str, str],
    method: str = "POST",
) -> dict[str, Any]:
    """提交内网表单。

    Args:
        url: 提交目标地址
        fields: 字段键值对，值支持 $CREDENTIAL.<字段> / $INPUT.<字段> 占位
        method: 提交方法，默认 POST
    """
    guard(url)
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=False
    ) as client:
        resp = await client.request(method.upper(), url, data=fields)
    return {
        "ok": resp.status_code < 400,
        "status_code": resp.status_code,
        "location": resp.headers.get("location", ""),
        "body_excerpt": resp.text[:2000],
    }


# ── HTML 抽取辅助 ───────────────────────────────────────────────────────────

import re  # noqa: E402  —— 放在后面是为了让上面的工具定义更醒目

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


if __name__ == "__main__":
    server.run_streamable_http_async(host=HOST, port=PORT, streamable_http_path="/mcp")
