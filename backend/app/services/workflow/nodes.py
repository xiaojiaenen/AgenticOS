"""工作流内置节点处理器（engine.WorkflowExecutor 的 handlers 注入集）。

每个 handler 只做一件事：拿到**已解析变量**的 params，产出该节点的输出。
副作用边界在此层显式收口：

- ``llm``：走 llm_factory（全站唯一 LLM 入口），不直连网关；
- ``knowledge``：走 KnowledgeRetrieval（自带 ACL），同步检索放线程；
- ``http``：先过 intranet_policy.check_url（SSRF 防护），禁止跟随重定向
  （重定向目标不再过策略 —— 跟随等于绕过 SSRF 校验），响应体限额读取；
- ``template`` / ``condition``：纯计算，无副作用。

所有输出都做长度限额 —— 输出会整体进 run 的 context_json 落库，
一个失控节点不该把行撑爆。
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.workflow.engine import (
    NODE_OUTPUT_MAX_CHARS,
    Handler,
    WorkflowNodeError,
    truncate_text,
)

_HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD")
_HTTP_BODY_MAX_BYTES = 256_000  # 响应体最多读这么多字节，防止大文件拖垮内存

_KNOWLEDGE_SNIPPET_CHARS = 1_000
_KNOWLEDGE_MAX_RESULTS = 20


# ---------------------------------------------------------------------------
# LLM 节点
# ---------------------------------------------------------------------------

async def run_llm(params: dict[str, Any], context: dict[str, Any]) -> str:
    prompt = params.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise WorkflowNodeError("(llm)", "params.prompt 不能为空")
    from app.services.llm_factory import build_llm

    # role 默认 fast：工作流节点是结构化小任务，不该默认吃对话主力模型；
    # 管理员没配 fast 绑定时 build_llm 自动退回提供商主模型。
    gateway = build_llm(role=params.get("role") or "fast")
    from wuwei.core.message import HumanMessage, SystemMessage

    messages = []
    system = params.get("system")
    if isinstance(system, str) and system.strip():
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    response = await gateway.generate(messages, stream=False)
    content = response.message.content or ""
    return truncate_text(content)


# ---------------------------------------------------------------------------
# 知识检索节点
# ---------------------------------------------------------------------------

def _run_knowledge_sync(
    params: dict[str, Any], user_id: int | None, is_admin: bool
) -> dict[str, Any]:
    from app.db.session import SessionLocal
    from app.services.knowledge.retrieval import KnowledgeRetrieval

    query = str(params.get("query") or "").strip()
    if not query:
        raise WorkflowNodeError("(knowledge)", "params.query 不能为空")
    kb_ids = params.get("kb_ids")
    if kb_ids is not None and not isinstance(kb_ids, list):
        raise WorkflowNodeError("(knowledge)", "params.kb_ids 必须是数组")
    top_k = params.get("top_k") or 5
    try:
        top_k = max(1, min(int(top_k), _KNOWLEDGE_MAX_RESULTS))
    except (TypeError, ValueError):
        top_k = 5

    db = SessionLocal()
    try:
        results = KnowledgeRetrieval(db).search(
            query=query,
            knowledge_base_ids=kb_ids,
            user_id=user_id,
            max_results=top_k,
            is_admin=is_admin,
        )
    finally:
        db.close()
    return {
        "results": [
            {
                "page_id": r.page_id,
                "title": r.title,
                "content": truncate_text(
                    r.snippet or r.content, _KNOWLEDGE_SNIPPET_CHARS
                ),
                "page_type": r.page_type,
                "score": round(r.score, 3),
                "sources": r.sources,
                "authority_level": r.authority_level,
            }
            for r in results
        ],
        "count": len(results),
    }


def make_knowledge_handler(user_id: int | None, is_admin: bool) -> Handler:
    """知识检索按触发者身份过滤（与 knowledge_tools 同一套 ACL）。"""

    async def handler(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(_run_knowledge_sync, params, user_id, is_admin)

    return handler


# ---------------------------------------------------------------------------
# HTTP 节点（SSRF 防护 + 限额）
# ---------------------------------------------------------------------------

async def run_http(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    import httpx

    from app.core.config import get_settings
    from app.services.intranet_policy import check_url

    url = str(params.get("url") or "").strip()
    if not url:
        raise WorkflowNodeError("(http)", "params.url 不能为空")
    method = str(params.get("method") or "GET").upper()
    if method not in _HTTP_METHODS:
        raise WorkflowNodeError("(http)", f"非法 method: {method}（允许: {', '.join(_HTTP_METHODS)}）")

    decision = check_url(url, allowed_cidrs=get_settings().intranet_allowed_cidrs)
    if not decision.allowed:
        raise WorkflowNodeError("(http)", f"目标被访问策略拒绝: {decision.reason}")

    headers = params.get("headers") or {}
    if not isinstance(headers, dict):
        raise WorkflowNodeError("(http)", "params.headers 必须是对象")
    # 不允许借 header 伪造受信任来源
    blocked_headers = {"host", "content-length", "authorization", "cookie"}
    safe_headers = {
        str(k): str(v) for k, v in headers.items()
        if str(k).lower() not in blocked_headers
    }
    body = params.get("body")
    content = body.encode("utf-8") if isinstance(body, str) and method not in ("GET", "HEAD") else None
    try:
        timeout = min(max(float(params.get("timeout_seconds") or 20), 1), 60)
    except (TypeError, ValueError):
        timeout = 20

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
            # 手动限额读取：Content-Length 不可信，stream 到上限就停
            async with client.stream(
                method, url, headers=safe_headers or None, content=content
            ) as resp:
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    chunks.append(chunk)
                    if total >= _HTTP_BODY_MAX_BYTES:
                        break
                raw = b"".join(chunks)
                charset = resp.charset_encoding or "utf-8"
                text = raw.decode(charset, errors="replace")
                return {
                    "status": resp.status_code,
                    "body": truncate_text(text),
                    "truncated": total > len(raw) or len(text) >= NODE_OUTPUT_MAX_CHARS,
                    "content_type": resp.headers.get("content-type", ""),
                }
    except httpx.HTTPError as exc:
        raise WorkflowNodeError("(http)", f"请求失败: {exc}") from exc


# ---------------------------------------------------------------------------
# 模板 / 条件（纯计算）
# ---------------------------------------------------------------------------

async def run_template(params: dict[str, Any], context: dict[str, Any]) -> str:
    template = params.get("template")
    if not isinstance(template, str):
        raise WorkflowNodeError("(template)", "params.template 必须是字符串")
    # 变量已在 executor 里统一解析过；这里只做截断
    return truncate_text(template)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# handler 集装配（engine 注入用）
# ---------------------------------------------------------------------------

def build_default_handlers(*, user_id: int | None, is_admin: bool) -> dict[str, Handler]:
    """按触发者身份装配 handlers（knowledge 的 ACL 随触发人走）。

    condition 是控制节点，由 executor 内建判定，不进 handler 表；
    human_input / end 同理由 executor 特殊处理。
    """
    return {
        "start": _run_start,
        "llm": run_llm,
        "knowledge": make_knowledge_handler(user_id, is_admin),
        "http": run_http,
        "template": run_template,
    }


async def _run_start(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    # start 的输出 = 触发时的输入（下游用 {{nodes.<start_id>.output}} 引用）
    return dict(context.get("inputs") or {})
