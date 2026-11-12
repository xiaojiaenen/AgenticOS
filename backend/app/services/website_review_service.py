"""部署审批的「审阅包」：让管理员在一个地方看到全部判断依据。

只读聚合，不做决策（决策仍走 ``POST /admin/website/deploys/{id}/decision``）：

- **对话**：来源会话的完整消息（用户怎么提的需求、模型怎么做的）
- **预览**：已构建的 dist 是否可访问 + 封面截图 URL
- **说明**：用户填写的网站说明
- **源码分析**：文件清单 + 大小 + 危险模式扫描（内联脚本、外链、
  表单提交目标、eval/fetch 目标等），标出需要人工确认的点

「AI 评审」走同一个入口的 model 参数：不传则只给静态分析，传了则由
LLM 基于上述材料给出风险意见（可见的只是建议，不自动批准）。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.data_path import WEBSITES_DIR
from app.db.models import AgentMessageModel, WebsiteDeployModel

_logger = logging.getLogger("website.review")

# 静态风险模式：(正则, 说明, 严重度)
_RISK_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"eval\s*\("), "使用 eval() 执行动态代码", "high"),
    (re.compile(r"new\s+Function\s*\("), "使用 new Function() 动态构造函数", "high"),
    (re.compile(r"document\.write\s*\("), "document.write 注入 HTML", "medium"),
    (re.compile(r"innerHTML\s*="), "直接写 innerHTML（XSS 风险）", "medium"),
    (re.compile(r"localStorage\.(set|get)Item\s*\(\s*['\"][^'\"]*token", re.I), "在 localStorage 存 token", "high"),
    (re.compile(r"fetch\s*\(\s*['\"]https?://", re.I), "向外部地址发起请求", "medium"),
    (re.compile(r"<form[^>]+action\s*=", re.I), "存在向外部提交的表单", "medium"),
    (re.compile(r"window\.open\s*\("), "会打开新窗口/外链", "low"),
    (re.compile(r"atob\s*\(|btoa\s*\("), "base64 编解码（可能混淆内容）", "low"),
]

_EXTERNAL_URL = re.compile(r"https?://([a-z0-9.-]+)", re.I)


def _scan_text(path: Path, text: str) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for pattern, label, severity in _RISK_PATTERNS:
        m = pattern.search(text)
        if m:
            hits.append(
                {
                    "file": path.name,
                    "pattern": label,
                    "severity": severity,
                    "sample": text[max(0, m.start() - 40) : m.end() + 40].replace("\n", " ")[:160],
                }
            )
    return {"hits": hits, "external_hosts": sorted(set(_EXTERNAL_URL.findall(text)))}


def analyze_source(project_slug: str, *, max_files: int = 200, max_bytes: int = 2_000_000) -> dict[str, Any]:
    """扫描站点产物，输出文件清单 + 风险命中 + 外链域名。"""
    dist = WEBSITES_DIR / project_slug / "dist"
    if not dist.is_dir():
        return {"available": False, "reason": "dist/ 不存在（尚未构建）", "files": [], "hits": [], "external_hosts": []}

    files: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    hosts: set[str] = set()
    scanned = 0
    total = 0

    text_suffixes = {".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt"}
    for path in sorted(dist.rglob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        rel = str(path.relative_to(dist)).replace("\\", "/")
        files.append({"path": rel, "size": size})
        if len(files) >= max_files:
            break
        if path.suffix.lower() not in text_suffixes:
            continue
        if size > 400_000 or scanned > max_bytes:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += size
        scan = _scan_text(path, text)
        hits.extend(scan["hits"])
        hosts.update(scan["external_hosts"])

    # 去掉本站/本地域名
    hosts = {h for h in hosts if h and not h.startswith(("127.", "localhost"))}
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    hits.sort(key=lambda h: severity_rank.get(h["severity"], 9))

    return {
        "available": True,
        "files": files[:max_files],
        "file_count": len(files),
        "total_bytes": total,
        "hits": hits[:40],
        "external_hosts": sorted(hosts)[:20],
        "entry_has_inline_script": any(
            f["path"].endswith(".html") and f["size"] > 50_000 for f in files
        ),
    }


def load_conversation(session_id: str, *, limit: int = 60) -> list[dict[str, Any]]:
    """取来源会话的消息（截断到可读长度，供审批页展示）。"""
    if not session_id:
        return []
    from app.db.session import create_db_session

    try:
        with create_db_session() as db:
            rows = db.scalars(
                select(AgentMessageModel)
                .where(AgentMessageModel.session_id == session_id)
                .order_by(AgentMessageModel.id.asc())
                .limit(limit)
            ).all()
    except Exception:  # noqa: BLE001
        _logger.warning("读取审批对话失败: session=%s", session_id, exc_info=True)
        return []

    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row.message_json)
        except (json.JSONDecodeError, TypeError):
            continue
        role = payload.get("role") or payload.get("type") or "unknown"
        content = payload.get("content")
        if isinstance(content, list):
            # 多模态 content：只取文本块
            content = " ".join(
                str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text"
            )
        text = str(content or "")
        if not text.strip() and not payload.get("tool_calls"):
            continue
        out.append(
            {
                "role": role,
                "text": text[:2000],
                "tool_calls": [
                    {"name": (tc.get("function") or {}).get("name")}
                    for tc in (payload.get("tool_calls") or [])
                    if isinstance(tc, dict)
                ][:6],
            }
        )
    return out


def build_review_packet(deploy: WebsiteDeployModel) -> dict[str, Any]:
    """组装审批页所需的全部材料。"""
    analysis = analyze_source(deploy.project_slug)
    return {
        "deploy": {
            "id": deploy.id,
            "project_slug": deploy.project_slug,
            "title": deploy.title or deploy.project_slug,
            "description": deploy.description,
            "stack": deploy.stack,
            "visibility": deploy.visibility,
            "status": deploy.status,
            "session_id": deploy.session_id,
            "requested_by": deploy.requested_by,
            "created_at": deploy.created_at.isoformat() if deploy.created_at else None,
            "short_url": f"/s/{deploy.short_code}" if deploy.short_code else None,
            "cover_url": f"/api/v1/website/cover/{deploy.project_slug}" if deploy.cover_path else None,
        },
        "conversation": load_conversation(deploy.session_id),
        "analysis": analysis,
    }


async def ai_review(packet: dict[str, Any]) -> dict[str, Any]:
    """让模型基于审阅包给出风险意见（建议性质，不自动决策）。

    输入只包含：网站说明、文件清单、静态扫描命中、对话摘要 —— 不给原始
    源码全文（太长且容易被注入）。模型输出结构化 JSON：风险等级 +
    理由 + 建议动作。
    """
    import asyncio

    from app.services.llm_factory import build_llm_optional

    analysis = packet.get("analysis") or {}
    deploy = packet.get("deploy") or {}
    convo = packet.get("conversation") or []

    summary = "\n".join(
        f"{m.get('role')}: {str(m.get('text',''))[:200]}" for m in convo[-12:]
    )
    hits = "\n".join(
        f"- [{h['severity']}] {h['file']}: {h['pattern']}" for h in (analysis.get("hits") or [])[:20]
    )
    files = "\n".join(f"- {f['path']} ({f['size']} B)" for f in (analysis.get("files") or [])[:40])

    prompt = f"""你是网站发布的安全评审员。管理员准备把下面这个用户生成的静态网站上线。

请判断它是否安全、合规、不涉及敏感数据外泄，输出 JSON（不要markdown围栏）：
{{"risk":"low|medium|high","reasons":["..."],"recommendation":"approve|review|reject","notes":"一句话建议"}}

网站名：{deploy.get('title')}
说明（用户填写）：{deploy.get('description') or '（未填写）'}
技术栈：{deploy.get('stack')}
可见性：{deploy.get('visibility')}

文件清单（前 40 个）：
{files or '（无）'}

静态扫描命中：
{hits or '（无）'}

外部域名：{', '.join(analysis.get('external_hosts') or []) or '（无）'}

对话摘要（最后 12 条）：
{summary or '（无）'}

判断要点：是否有 eval/innerHTML 等 XSS 面、是否向陌生外部域名发送数据、
是否有登录凭据处理、是否像钓鱼页（模仿登录界面 + 外发表单）。
"""

    llm = build_llm_optional(max_tokens=800, timeout=45, role="fast")
    if llm is None:
        return {"available": False, "reason": "未配置可用模型"}
    try:
        resp = await asyncio.wait_for(llm.generate([{"role": "user", "content": prompt}]), timeout=50)
        text = getattr(getattr(resp, "message", None), "content", "") or ""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1] if "```" in text[3:] else text[3:]
            text = text.lstrip("json").strip()
        return {"available": True, **json.loads(text)}
    except Exception:  # noqa: BLE001 —— 评审失败不阻断人工审批
        _logger.warning("AI 评审失败", exc_info=True)
        return {"available": False, "reason": "评审模型调用失败"}
