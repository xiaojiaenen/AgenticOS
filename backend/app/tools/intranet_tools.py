"""内网爬虫工具（主项目侧的薄壳）。

真正的抓取 / 浏览器驱动逻辑在**独立进程**（``deploy/intranet/``）里，
主项目只通过 HTTP 调用它。这样做的原因见
``docs/内网爬虫与无头浏览器方案.md``：

- 内网依赖（自签证书、内网 DNS、内网浏览器）不污染主项目依赖树；
- Chromium 崩溃/内存泄漏不会拖垮 AgenticOS；
- 没配 ``INTRANET_SERVICE_URL`` 时工具直接返回「未启用」，
  外网部署行为与之前完全一致。
"""

from __future__ import annotations

from typing import Any

from wuwei.tools import ToolRegistry

from app.services import intranet_client as client


def register_intranet_tools(registry: ToolRegistry) -> None:
    """注册内网爬虫工具。"""

    @registry.tool(
        name="intranet_probe",
        display_name="探测内网站点",
        description=(
            "探测一个内网 URL 的结构：是否可达、是否需要登录、页面类型"
            "（静态 HTML / JSON API / JS 渲染）、可见的表单与列表特征。"
            "不返回页面正文。操作内网站点前建议先探测。"
        ),
    )
    async def intranet_probe(url: str) -> dict[str, Any]:
        """探测内网 URL 的基本结构。

        参数:
          url: 内网地址（http/https）
        """
        if not client.is_enabled():
            return {"ok": False, "error": client.disabled_message()}
        try:
            client.guard_url(url)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}

        data = await client.call_service("/probe", {"url": url})
        return data

    @registry.tool(
        name="intranet_fetch",
        display_name="抓取内网页面",
        description=(
            "抓取一个内网 URL 的内容（静态 HTML 或 JSON API）。"
            "页面由 JS 渲染时用 intranet_browse。"
        ),
    )
    async def intranet_fetch(
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        max_chars: int | None = None,
    ) -> dict[str, Any]:
        """抓取内网页面。

        参数:
          url: 内网地址
          method: HTTP 方法，默认 GET
          headers: 附加请求头（值支持 $CREDENTIAL.x / $INPUT.x 占位）
          body: 请求体（JSON 字符串），值同样支持占位
          max_chars: 返回正文的最大字符数
        """
        if not client.is_enabled():
            return {"ok": False, "error": client.disabled_message()}
        try:
            client.guard_url(url)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}

        method = (method or "GET").upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            return {"ok": False, "error": f"不支持的 HTTP 方法：{method}"}

        resolved_headers, missing = client.resolve_placeholders(headers or {})
        resolved_body, missing_body = client.resolve_placeholders(
            {"body": body or ""}
        )
        missing = missing + missing_body
        if missing:
            return {
                "ok": False,
                "error": (
                    f"缺少参数：{', '.join(sorted(set(missing)))}。"
                    "请先在「集成」页配置该站点的凭据，"
                    "或用 intranet_ask_user 向用户询问。"
                ),
            }

        payload: dict[str, Any] = {
            "url": url,
            "method": method,
            "headers": resolved_headers,
            "body": resolved_body["body"] or None,
        }
        if max_chars:
            payload["max_chars"] = int(max_chars)

        return await client.call_service("/fetch", payload)

    @registry.tool(
        name="intranet_browse",
        display_name="无头浏览器操作",
        description=(
            "用无头浏览器打开内网页面（适合 JS 渲染的页面、需登录的站点、"
            "带验证码或多步表单的页面）。可执行点击/输入/等待等动作，"
            "并可选提取内容。"
        ),
        side_effect=True,
        requires_approval=True,
    )
    async def intranet_browse(
        url: str,
        actions: list[dict[str, Any]] | None = None,
        extract: str | None = None,
        wait_for: str | None = None,
        max_chars: int | None = None,
    ) -> dict[str, Any]:
        """用无头浏览器访问内网页面。

        参数:
          url: 内网地址
          actions: 动作序列，如
                   [{"type": "click", "selector": "#login"},
                    {"type": "fill", "selector": "#user", "value": "$CREDENTIAL.username"},
                    {"type": "submit", "selector": "form"}]
          extract: 提取选择器（CSS），给出该元素的可见文本
          wait_for: 等待某个选择器出现再继续
          max_chars: 返回内容最大字符数
        """
        if not client.is_enabled():
            return {"ok": False, "error": client.disabled_message()}
        try:
            client.guard_url(url)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}

        resolved_actions, missing = client.resolve_placeholders(
            {f"a{i}": a for i, a in enumerate(actions or [])}
        )
        if missing:
            return {
                "ok": False,
                "error": (
                    f"缺少参数：{', '.join(sorted(set(missing)))}。"
                    "请先在「集成」页配置该站点的凭据。"
                ),
            }

        action_list = [resolved_actions[f"a{i}"] for i in range(len(actions or []))]
        payload: dict[str, Any] = {
            "url": url,
            "actions": action_list,
            "extract": extract,
            "wait_for": wait_for,
        }
        if max_chars:
            payload["max_chars"] = int(max_chars)

        return await client.call_service("/browse", payload)

    @registry.tool(
        name="intranet_extract",
        display_name="抽取内网数据",
        description=(
            "把抓取到的 HTML 表格/列表抽取成结构化行。"
            "用于批量导出场景：先 fetch/browse 拿内容，再 extract 出行。"
        ),
    )
    async def intranet_extract(
        html: str,
        table_selector: str | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """从 HTML 中抽取结构化数据。

        参数:
          html: HTML 源码
          table_selector: 表格/列表的 CSS 选择器，不填则自动识别
          fields: 要保留的字段名列表（按表头匹配）
        """
        if not client.is_enabled():
            return {"ok": False, "error": client.disabled_message()}

        return await client.call_service(
            "/extract",
            {
                "html": html,
                "table_selector": table_selector,
                "fields": fields or [],
            },
        )

    @registry.tool(
        name="intranet_submit",
        display_name="提交内网表单",
        description=(
            "向内网站点提交表单（写操作）。默认需要审批。"
            "字段值支持 $CREDENTIAL.x / $INPUT.x 占位。"
        ),
        side_effect=True,
        requires_approval=True,
    )
    async def intranet_submit(
        url: str,
        fields: dict[str, str],
        method: str = "POST",
    ) -> dict[str, Any]:
        """提交内网表单。

        参数:
          url: 提交目标地址
          fields: 字段键值对，值支持 $CREDENTIAL.x / $INPUT.x 占位
          method: 提交方法，默认 POST
        """
        if not client.is_enabled():
            return {"ok": False, "error": client.disabled_message()}
        try:
            client.guard_url(url)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}

        resolved, missing = client.resolve_placeholders(fields or {})
        if missing:
            return {
                "ok": False,
                "error": (
                    f"缺少参数：{', '.join(sorted(set(missing)))}。"
                    "请先在「集成」页配置该站点的凭据，"
                    "或用 intranet_ask_user 向用户询问。"
                ),
            }

        return await client.call_service(
            "/submit",
            {"url": url, "method": method.upper(), "fields": resolved},
        )
