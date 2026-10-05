import asyncio
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.schemas.agent import AgentStreamRequest, ApprovalDecisionRequest, PptExportRequest
from app.services.agent_service import AgentService, get_agent_service
from app.services.design_system import get_design_system_registry

router = APIRouter(prefix="/agent", tags=["智能体"])

# 表格版本目录名：u{user}_s{session}_v{n}。save 接口拿它拼路径，必须严格校验，
# 否则 ../ 可以写到 data/sheets 之外。
_SHEET_DIR_RE = re.compile(r"^u\d+_s[\w-]+_v\d+$")

_logger = logging.getLogger("agent.stream")


def _format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# SVG 安全净化：按标签/属性白名单移除危险内容，避免拼接进 HTML 后产生存储型 XSS。
_RE_SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_RE_SELF_CLOSING_SCRIPT = re.compile(r"<script\b[^>]*/\s*>", re.IGNORECASE)
_RE_EVENT_ATTR = re.compile(r'\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', re.IGNORECASE)
_RE_JS_URL = re.compile(r"(?:javascript|vbscript)\s*:|data\s*:\s*text/html", re.IGNORECASE)
_RE_FOREIGN_OBJECT = re.compile(r"<foreignObject\b[^>]*>.*?</foreignObject\s*>", re.IGNORECASE | re.DOTALL)
_RE_SELF_CLOSING_FOREIGN_OBJECT = re.compile(r"<foreignObject\b[^>]*/\s*>", re.IGNORECASE)


def _sanitize_svg(svg: str) -> str:
    """移除 SVG 中的脚本向量：<script>、on* 事件属性、javascript:/data:text/html: URL、<foreignObject>。"""
    svg = _RE_SCRIPT_BLOCK.sub("", svg)
    svg = _RE_SELF_CLOSING_SCRIPT.sub("", svg)
    svg = _RE_FOREIGN_OBJECT.sub("", svg)
    svg = _RE_SELF_CLOSING_FOREIGN_OBJECT.sub("", svg)
    svg = _RE_EVENT_ATTR.sub("", svg)
    svg = _RE_JS_URL.sub("", svg)
    return svg


@router.post("/stream", summary="以流式方式返回 Wuwei 智能体响应")
async def stream_agent(
    request: AgentStreamRequest,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    try:
        agent_service.ensure_ready()
        await agent_service.ensure_session_access(request, current_user)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    async def event_stream():
        session_id = request.session_id or "(new)"
        try:
            async for event in agent_service.stream_chat(request, current_user):
                yield _format_sse(event["event"], event["data"])
        except Exception as exc:
            _logger.exception("stream_chat fatal error: session=%s", session_id)
            yield _format_sse("error", {
                "message": str(exc),
                "error_type": type(exc).__name__,
                "session_id": session_id,
            })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/approvals/{approval_id}/decision", summary="提交工具调用人工审批结果")
async def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    try:
        return await agent_service.decide_approval(
            approval_id,
            status=request.status,
            reason=request.reason,
            current_user=current_user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/decisions/{decision_id}/decision", summary="提交用户决策结果")
async def decide_user_decision(
    decision_id: str,
    request: dict[str, str],
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    from app.tools.decision_tools import resolve_decision
    answer = request.get("answer", "")
    if not answer:
        raise HTTPException(status_code=400, detail="answer 不能为空")
    resolved = await resolve_decision(decision_id, answer)
    if not resolved:
        raise HTTPException(status_code=404, detail="决策不存在或已超时")
    return {"ok": True, "decision_id": decision_id, "answer": answer}


@router.get("/sessions/{session_id}", summary="获取智能体会话运行状态")
async def get_session_state(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    try:
        await agent_service.ensure_session_access(AgentStreamRequest(message="status", session_id=session_id), current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return await agent_service.get_session_state(session_id)


@router.get("/sessions/{session_id}/messages", summary="获取会话的完整消息历史")
async def get_session_messages(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> list[dict[str, Any]]:
    """加载指定会话的全部消息，用于前端刷新后恢复聊天记录。"""
    try:
        await agent_service.ensure_session_access(
            AgentStreamRequest(message="load_messages", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    session = await agent_service.storage.load(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    result = []
    for msg in session.context._messages:
        entry: dict[str, Any] = {
            "role": msg.role,
            "content": msg.content or "",
        }
        if msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name if tc.function else "tool_call",
                    "arguments": tc.function.arguments if tc.function else None,
                }
                for tc in msg.tool_calls
            ]
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            entry["tool_call_id"] = msg.tool_call_id
            entry["name"] = getattr(msg, "name", None)
        result.append(entry)
    return result


@router.get("/sessions", summary="获取当前用户的会话列表")
async def list_sessions(
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> list[dict[str, Any]]:
    return await agent_service.list_user_sessions(current_user.id)


@router.get("/sessions/{session_id}/artifacts", summary="获取会话关联的最新制品（PPT/网站/表格）")
async def get_session_artifacts(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    """用于会话重新打开时恢复 PPT/website/表格 预览面板。"""
    try:
        await agent_service.ensure_session_access(
            AgentStreamRequest(message="load_artifacts", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    result: dict[str, Any] = {
        "ppt_artifact": None,
        "website_artifact": None,
        "sheet_artifact": None,
    }

    # PPT：取该会话最新的 artifact，裁剪字段（不带 deck_json，避免传输 150KB+ 大字段）
    try:
        ppt = await agent_service.ppt_artifacts.get_latest_for_session(session_id)
    except Exception:
        _logger.exception("get_latest_for_session failed: session=%s", session_id)
        ppt = None
    if ppt:
        metadata = ppt.get("metadata") or {}
        result["ppt_artifact"] = {
            "artifact_id": ppt.get("artifact_id"),
            "session_id": ppt.get("session_id"),
            "title": ppt.get("title"),
            "slide_count": ppt.get("slide_count"),
            "html": ppt.get("html"),
            "theme": ppt.get("theme") or metadata.get("theme"),
        }

    # website：从 data/websites/{u*_s{session}_v*} 的 dist 重建
    # （刷新页面后恢复网站预览面板；此前该字段恒为 null，导致刷新即丢失）
    try:
        website = await agent_service.get_latest_website_artifact(session_id)
    except Exception:
        _logger.exception("get_latest_website_artifact failed: session=%s", session_id)
        website = None
    if website:
        result["website_artifact"] = {
            "artifact_id": website.get("artifact_id"),
            "session_id": website.get("session_id"),
            "title": website.get("title"),
            "project_slug": website.get("project_slug"),
            "stack": website.get("stack"),
            "preview_html": website.get("preview_html"),
        }

    # 表格：从 data/sheets/{u*_s{session}_v*}/workbook.json 重建
    try:
        sheet = await agent_service.get_latest_sheet_artifact(session_id)
    except Exception:
        _logger.exception("get_latest_sheet_artifact failed: session=%s", session_id)
        sheet = None
    if sheet:
        result["sheet_artifact"] = sheet

    return result


@router.put("/sessions/{session_id}/sheets/{directory}", summary="保存用户对表格产物的修改")
async def save_sheet_artifact(
    session_id: str,
    directory: str,
    payload: dict[str, Any],
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, Any]:
    """把编辑器里的最新快照写回 data/sheets/{directory}/workbook.json。

    校验两点：目录名必须匹配版本目录的正则（防路径穿越），快照必须带
    sheetOrder/sheets（否则打开就是空表）。
    """
    try:
        await get_agent_service().ensure_session_access(
            AgentStreamRequest(message="save_sheet", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    from app.core.data_path import SHEETS_DIR
    from app.services.sheet.service import read_snapshot, write_snapshot

    if not _SHEET_DIR_RE.match(directory):
        raise HTTPException(status_code=400, detail="非法的表格版本目录名")

    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict) or not snapshot.get("sheetOrder"):
        raise HTTPException(status_code=400, detail="表格快照格式不合法：缺少 sheetOrder")

    target = SHEETS_DIR / directory
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="该表格产物不存在")
    if read_snapshot(target) is None:
        raise HTTPException(status_code=500, detail="该表格产物已损坏，无法保存")

    write_snapshot(target, snapshot)
    return {"ok": True, "directory": directory}


@router.get("/sessions/{session_id}/versions", summary="列出会话的全部产物版本")
async def list_session_versions(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    """列出该会话的 PPT / 网站历史版本（最新在前）。

    PPT 版本来自 ppt_artifacts 表（每轮生成一条记录）；网站版本来自每轮产物快照。
    """
    try:
        await agent_service.ensure_session_access(
            AgentStreamRequest(message="list_versions", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    from app.services.artifact_version_service import list_session_versions as _list

    versions = await _list(session_id, agent_service.ppt_artifacts)
    return {"versions": versions}


@router.get(
    "/sessions/{session_id}/versions/{kind}/{reference}",
    summary="加载指定版本的产物（website/sheet 版本号 / ppt 的 artifact_id）",
)
async def get_session_version(
    session_id: str,
    kind: str,
    reference: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    """按版本引用加载产物，供"查看历史版本"使用。"""
    try:
        await agent_service.ensure_session_access(
            AgentStreamRequest(message="get_version", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if kind == "website":
        from app.services.artifact_version_service import build_website_version_artifact

        try:
            version_no = int(reference.lstrip("vV"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="非法的网站版本号") from exc
        artifact = await asyncio.to_thread(
            build_website_version_artifact, session_id, version_no
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="该版本的网站产物不存在")
        return {"website_artifact": artifact}

    if kind == "sheet":
        from app.services.artifact_version_service import load_sheet_version

        try:
            version_no = int(reference.lstrip("vV"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="非法的表格版本号") from exc
        artifact = await asyncio.to_thread(load_sheet_version, session_id, version_no)
        if artifact is None:
            raise HTTPException(status_code=404, detail="该版本的表格产物不存在")
        return {"sheet_artifact": artifact}

    if kind == "ppt":
        try:
            artifact = await agent_service.ppt_artifacts.get(reference)
        except Exception:
            _logger.exception("get ppt version failed: artifact_id=%s", reference)
            artifact = None
        if artifact is None or artifact.get("session_id") != session_id:
            raise HTTPException(status_code=404, detail="该版本的 PPT 产物不存在")
        metadata = artifact.get("metadata") or {}
        return {
            "ppt_artifact": {
                "artifact_id": artifact.get("artifact_id"),
                "session_id": artifact.get("session_id"),
                "title": artifact.get("title"),
                "slide_count": artifact.get("slide_count"),
                "html": artifact.get("html"),
                "theme": artifact.get("theme") or metadata.get("theme"),
            }
        }

    raise HTTPException(status_code=400, detail=f"不支持的产物类型: {kind}")


@router.delete("/sessions/{session_id}", summary="删除指定会话")
async def delete_session(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, str]:
    try:
        await agent_service.delete_session(session_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "deleted", "session_id": session_id}


@router.get("/design-systems", summary="获取可用设计系统列表")
async def list_design_systems(
    category: str | None = None,
) -> list[dict[str, Any]]:
    registry = get_design_system_registry()
    systems = registry.search(category=category) if category else registry.list_all()
    return [ds.to_dict() for ds in systems]


@router.get("/design-systems/{name}/preview", summary="获取设计系统预览")
async def get_design_system_preview(name: str) -> dict[str, Any]:
    registry = get_design_system_registry()
    ds = registry.get(name)
    if ds is None:
        raise HTTPException(status_code=404, detail=f"设计系统 '{name}' 不存在。")
    return {
        **ds.to_dict(),
        "prompt_excerpt": ds.to_prompt_excerpt(),
    }


@router.get("/artifacts/{artifact_id}", summary="获取 PPT 制品预览")
async def get_ppt_artifact(
    artifact_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    try:
        artifact = await agent_service.get_ppt_artifact(artifact_id, current_user=current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if artifact is None:
        raise HTTPException(status_code=404, detail="PPT 制品不存在。")
    return artifact


@router.get("/ppt/preview/{artifact_id}", summary="PPT SVG 实时预览")
async def preview_pptx(
    artifact_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Return an HTML page that displays all SVG slides with keyboard navigation."""
    artifact = await agent_service.get_ppt_artifact(artifact_id, current_user)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"PPT 产物 {artifact_id} 不存在")

    svgs = agent_service.ppt_artifacts.extract_svgs_from_artifact(artifact)
    if not svgs:
        raise HTTPException(status_code=400, detail="产物中没有可用的幻灯片")

    slides_html = "".join(_sanitize_svg(svg) for svg in svgs)
    # 对 title 进行 HTML 转义防止 XSS
    import html
    safe_title = html.escape(artifact.get("title", "PPT Preview"), quote=True)
    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{safe_title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0f0f0f; color:#e0e0e0; font-family:Inter,Noto Sans SC,sans-serif; overflow:hidden; }}
#counter {{ position:fixed; top:16px; right:24px; z-index:100; font-size:13px; color:#888; font-variant-numeric:tabular-nums; }}
#deck {{ display:flex; flex-direction:column; align-items:center; gap:8px; padding:16px; overflow-y:auto; height:100vh; scroll-snap-type:y mandatory; }}
.slide {{ scroll-snap-align:start; width:100%; max-width:1280px; flex-shrink:0; }}
.slide svg {{ width:100%; height:auto; display:block; border-radius:8px; box-shadow:0 4px 24px rgba(0,0,0,.5); }}
.notes {{ max-width:1280px; margin:4px auto 24px; padding:12px 20px; background:#1a1a1a; border-left:3px solid #444; border-radius:4px; font-size:13px; color:#999; line-height:1.6; white-space:pre-wrap; display:none; }}
.notes.visible {{ display:block; }}
</style></head>
<body>
<div id="counter">1 / {len(svgs)}</div>
<div id="deck">{slides_html}</div>
<script>
(function() {{
  var slides = document.querySelectorAll('.slide');
  var counter = document.getElementById('counter');
  var current = 0;
  function show(i) {{
    current = Math.max(0, Math.min(i, slides.length - 1));
    slides[current].scrollIntoView({{ behavior:'smooth', block:'start' }});
    counter.textContent = (current + 1) + ' / ' + slides.length;
  }}
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight' || e.key === 'j') {{ e.preventDefault(); show(current + 1); }}
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'k') {{ e.preventDefault(); show(current - 1); }}
    if (e.key === 'Home') {{ e.preventDefault(); show(0); }}
    if (e.key === 'End') {{ e.preventDefault(); show(slides.length - 1); }}
    if (e.key === 'n') {{
      e.preventDefault();
      document.querySelectorAll('.notes').forEach(function(n) {{ n.classList.toggle('visible'); }});
    }}
  }});
  // Wrap each SVG in a slide container
  document.querySelectorAll('#deck > svg').forEach(function(svg) {{
    var div = document.createElement('div');
    div.className = 'slide';
    svg.parentNode.insertBefore(div, svg);
    div.appendChild(svg);
  }});
  slides = document.querySelectorAll('.slide');
}})();
</script>
</body></html>"""
    return Response(content=html_content, media_type="text/html; charset=utf-8")


@router.get("/ppt/editor/{artifact_id}", summary="PPT SVG 实时编辑器")
async def ppt_editor(
    artifact_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Return an HTML page for editing SVG slides with live preview."""
    artifact = await agent_service.get_ppt_artifact(artifact_id, current_user)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"PPT 产物 {artifact_id} 不存在")

    svgs = agent_service.ppt_artifacts.extract_svgs_from_artifact(artifact)
    if not svgs:
        raise HTTPException(status_code=400, detail="产物中没有可用的幻灯片")

    import json
    from html import escape as _html_escape

    # XSS 防护：
    # 1) title 走 HTML 转义后插入 <title>/<h2>；
    # 2) svgs_json / artifact_id 用 JSON 编码并把 < > & 转为 \uXXXX，
    #    防止内容里的 </script> 提前闭合脚本标签；
    # 3) 插入预览 DOM 时经 DOMParser 清洗（见前端 sanitizeSvg）。
    svgs_json = (
        json.dumps(svgs, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    artifact_id_js = json.dumps(str(artifact_id)).replace("<", "\\u003c")
    title = _html_escape(str(artifact.get("title", "PPT Editor")))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title} - 编辑器</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:Inter,Noto Sans SC,system-ui,sans-serif; background:#f8fafc; color:#1e293b; }}
.app {{ display:flex; height:100vh; }}
.sidebar {{ width:240px; background:#fff; border-right:1px solid #e2e8f0; display:flex; flex-direction:column; }}
.sidebar-header {{ padding:16px; border-bottom:1px solid #e2e8f0; }}
.sidebar-header h2 {{ font-size:14px; font-weight:600; color:#0f172a; }}
.sidebar-header p {{ font-size:11px; color:#64748b; margin-top:4px; }}
.slide-list {{ flex:1; overflow-y:auto; padding:12px; }}
.slide-thumb {{ cursor:pointer; margin-bottom:12px; border:2px solid transparent; border-radius:8px; overflow:hidden; transition:all 0.15s; }}
.slide-thumb:hover {{ border-color:#94a3b8; }}
.slide-thumb.active {{ border-color:#3b82f6; box-shadow:0 0 0 3px rgba(59,130,246,0.2); }}
.slide-thumb svg {{ width:100%; height:auto; display:block; }}
.slide-thumb .slide-num {{ font-size:11px; color:#64748b; padding:4px 8px; background:#f1f5f9; text-align:center; }}
.main {{ flex:1; display:flex; flex-direction:column; }}
.toolbar {{ height:56px; background:#fff; border-bottom:1px solid #e2e8f0; display:flex; align-items:center; padding:0 20px; gap:8px; }}
.toolbar button {{ padding:8px 16px; border:1px solid #e2e8f0; background:#fff; border-radius:8px; cursor:pointer; font-size:13px; font-weight:500; transition:all 0.15s; }}
.toolbar button:hover {{ background:#f8fafc; border-color:#94a3b8; }}
.toolbar button.primary {{ background:#3b82f6; color:#fff; border-color:#3b82f6; }}
.toolbar button.primary:hover {{ background:#2563eb; }}
.toolbar .spacer {{ flex:1; }}
.toolbar .page-info {{ font-size:13px; color:#64748b; font-variant-numeric:tabular-nums; }}
.editor-area {{ flex:1; display:flex; overflow:hidden; }}
.preview-panel {{ flex:1; overflow:auto; padding:32px; background:#f1f5f9; display:flex; align-items:flex-start; justify-content:center; }}
.preview-container {{ width:100%; max-width:960px; background:#fff; border-radius:12px; box-shadow:0 4px 24px rgba(0,0,0,0.08); overflow:hidden; }}
.preview-container svg {{ width:100%; height:auto; display:block; }}
.code-panel {{ width:480px; background:#1e293b; border-left:1px solid #334155; display:flex; flex-direction:column; }}
.code-header {{ padding:12px 16px; background:#0f172a; border-bottom:1px solid #334155; display:flex; align-items:center; justify-content:space-between; }}
.code-header span {{ font-size:12px; color:#94a3b8; font-weight:500; }}
.code-header button {{ padding:4px 12px; background:#334155; border:none; border-radius:6px; color:#e2e8f0; font-size:12px; cursor:pointer; }}
.code-header button:hover {{ background:#475569; }}
.code-editor {{ flex:1; overflow:hidden; }}
.code-editor textarea {{ width:100%; height:100%; padding:16px; background:#0f172a; color:#e2e8f0; border:none; font-family:'JetBrains Mono','Fira Code',monospace; font-size:13px; line-height:1.6; resize:none; outline:none; tab-size:2; }}
.status-bar {{ height:32px; background:#fff; border-top:1px solid #e2e8f0; display:flex; align-items:center; padding:0 16px; font-size:11px; color:#64748b; }}
.status-bar .saved {{ color:#22c55e; }}
.status-bar .modified {{ color:#f59e0b; }}
</style>
</head>
<body>
<div class="app">
  <div class="sidebar">
    <div class="sidebar-header">
      <h2>{title}</h2>
      <p>{len(svgs)} 页幻灯片</p>
    </div>
    <div class="slide-list" id="slideList"></div>
  </div>
  <div class="main">
    <div class="toolbar">
      <button onclick="prevSlide()" id="btnPrev">◀ 上一页</button>
      <button onclick="nextSlide()" id="btnNext">下一页 ▶</button>
      <span class="page-info" id="pageInfo">-</span>
      <div class="spacer"></div>
      <button onclick="applyChanges()" class="primary" id="btnApply">应用修改</button>
      <button onclick="saveAll()">保存全部</button>
    </div>
    <div class="editor-area">
      <div class="preview-panel">
        <div class="preview-container" id="preview"></div>
      </div>
      <div class="code-panel">
        <div class="code-header">
          <span>SVG 源码</span>
          <button onclick="formatCode()">格式化</button>
        </div>
        <div class="code-editor">
          <textarea id="codeEditor" spellcheck="false"></textarea>
        </div>
      </div>
    </div>
    <div class="status-bar">
      <span id="statusText">就绪</span>
      <div class="spacer"></div>
      <span id="saveStatus" class="saved">● 已保存</span>
    </div>
  </div>
</div>
<script>
const artifactId = {artifact_id_js};
let svgs = {svgs_json};
let currentSlide = 0;
let modified = {{}};

// ── XSS 安全插入：DOMParser 解析 + 清洗 script/on* 危险内容 ──
function sanitizeSvgRoot(markup) {{
  try {{
    const doc = new DOMParser().parseFromString(String(markup || ''), 'image/svg+xml');
    if (!doc || doc.querySelector('parsererror')) return null;
    const root = doc.documentElement;
    if (!root || (root.nodeName || '').toLowerCase() !== 'svg') return null;
    // 移除可执行/嵌套文档元素
    doc.querySelectorAll('script, foreignObject, iframe, object, embed').forEach(function (node) {{
      node.parentNode && node.parentNode.removeChild(node);
    }});
    // 移除事件处理器属性与危险 URL 协议
    doc.querySelectorAll('*').forEach(function (el) {{
      Array.prototype.slice.call(el.attributes || []).forEach(function (attr) {{
        const name = (attr.name || '').toLowerCase();
        const value = String(attr.value || '');
        if (name.indexOf('on') === 0) {{
          el.removeAttribute(attr.name);
          return;
        }}
        if ((name === 'href' || name === 'xlink:href' || name === 'src') &&
            /^\\s*(javascript|vbscript|data:text\\/html)/i.test(value.trim())) {{
          el.removeAttribute(attr.name);
        }}
      }});
    }});
    return root;
  }} catch (e) {{
    return null;
  }}
}}

function setSafeSvg(container, markup) {{
  if (!container) return;
  container.textContent = '';
  const root = sanitizeSvgRoot(markup);
  if (root) container.appendChild(document.importNode(root, true));
}}

function init() {{
  renderSlideList();
  if (svgs.length > 0) showSlide(0);
  updateButtons();
}}

function renderSlideList() {{
  const list = document.getElementById('slideList');
  list.textContent = '';
  svgs.forEach(function (svg, i) {{
    const thumb = document.createElement('div');
    thumb.className = 'slide-thumb' + (i === currentSlide ? ' active' : '');
    thumb.addEventListener('click', function () {{ showSlide(i); }});
    const num = document.createElement('div');
    num.className = 'slide-num';
    num.textContent = '第 ' + (i + 1) + ' 页';
    thumb.appendChild(num);
    setSafeSvg(thumb, svg);
    list.appendChild(thumb);
  }});
}}

function showSlide(index) {{
  if (index < 0 || index >= svgs.length) return;
  currentSlide = index;
  setSafeSvg(document.getElementById('preview'), svgs[index]);
  document.getElementById('codeEditor').value = svgs[index];
  document.getElementById('pageInfo').textContent = `第 ${{index + 1}} 页 / 共 ${{svgs.length}} 页`;
  renderSlideList();
  updateButtons();
  document.getElementById('statusText').textContent = `正在编辑第 ${{index + 1}} 页`;
}}

function updateButtons() {{
  document.getElementById('btnPrev').disabled = currentSlide === 0;
  document.getElementById('btnNext').disabled = currentSlide === svgs.length - 1;
}}

function prevSlide() {{ showSlide(currentSlide - 1); }}
function nextSlide() {{ showSlide(currentSlide + 1); }}

function applyChanges() {{
  const code = document.getElementById('codeEditor').value;
  if (!code.trim()) return;

  // 基本验证
  if (!code.includes('<svg')) {{
    alert('SVG 代码必须包含 <svg> 标签');
    return;
  }}

  svgs[currentSlide] = code;
  modified[currentSlide] = true;
  setSafeSvg(document.getElementById('preview'), code);
  renderSlideList();
  document.getElementById('saveStatus').className = 'modified';
  document.getElementById('saveStatus').textContent = '● 已修改（未保存）';
  document.getElementById('statusText').textContent = `第 ${{currentSlide + 1}} 页已更新`;
}}

// 从 localStorage/sessionStorage 获取 auth token
function getAuthToken() {{
  // AgenticOS 使用 auth_token 作为 key
  for (const storage of [localStorage, sessionStorage]) {{
    const val = storage.getItem('auth_token');
    if (val) return val;
  }}
  return '';
}}

async function saveAll() {{
  const modifiedSlides = Object.keys(modified);
  if (modifiedSlides.length === 0) {{
    alert('没有需要保存的修改');
    return;
  }}

  document.getElementById('statusText').textContent = '正在保存...';
  const token = getAuthToken();

  try {{
    const response = await fetch(`/api/v1/agent/ppt/${{artifactId}}/update-slides`, {{
      method: 'POST',
      headers: {{
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${{token}}`,
      }},
      body: JSON.stringify({{ svgs: svgs }}),
    }});

    if (response.ok) {{
      modified = {{}};
      document.getElementById('saveStatus').className = 'saved';
      document.getElementById('saveStatus').textContent = '● 已保存';
      document.getElementById('statusText').textContent = `已保存 ${{modifiedSlides.length}} 页修改`;
    }} else {{
      const err = await response.text();
      alert('保存失败: ' + err);
    }}
  }} catch (e) {{
    alert('保存失败: ' + e.message);
  }}
}}

function formatCode() {{
  const textarea = document.getElementById('codeEditor');
  let code = textarea.value;
  // 简单的格式化：在 > 后换行（正则空白与换行转义在 Python 源里双写）
  code = code.replace(/>\\s*</g, '>\\n<');
  textarea.value = code;
}}

// 快捷键
document.addEventListener('keydown', function(e) {{
  if (e.ctrlKey && e.key === 's') {{
    e.preventDefault();
    applyChanges();
  }}
  if (e.ctrlKey && e.shiftKey && e.key === 'S') {{
    e.preventDefault();
    saveAll();
  }}
}});

// 实时预览（延迟更新）
let previewTimer = null;
document.getElementById('codeEditor').addEventListener('input', function() {{
  if (previewTimer) clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {{
    const code = this.value;
    if (code.includes('<svg')) {{
      setSafeSvg(document.getElementById('preview'), code);
    }}
  }}, 500);
}});

init();
</script>
</body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.post("/ppt/{artifact_id}/update-slides", summary="更新 PPT 幻灯片")
async def update_ppt_slides(
    artifact_id: str,
    request: dict[str, Any],
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, str]:
    """Update SVG slides for a PPT artifact."""
    from app.db.models import PptArtifactModel

    try:
        await agent_service._ensure_record_owner(artifact_id, PptArtifactModel, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    svgs = request.get("svgs", [])
    if not svgs:
        raise HTTPException(status_code=400, detail="未提供任何幻灯片内容")

    try:
        from app.services.ppt_artifact_service import sanitize_svg_xml

        # 清理 SVG
        cleaned_svgs = [sanitize_svg_xml(svg) for svg in svgs]

        # 获取主题
        artifact = await agent_service.ppt_artifacts.get(artifact_id)
        deck = json.loads(artifact.get("deck_json", "{}")) if artifact else {}
        theme_name = deck.get("theme", "apple")

        # 更新数据库
        await agent_service.ppt_artifacts.update_svgs(artifact_id, cleaned_svgs, theme_name)

        return {"status": "ok", "slides_updated": len(cleaned_svgs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ppt/export", summary="导出 PPT 制品为原生 .pptx 文件")
async def export_pptx(
    request: PptExportRequest,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    try:
        pptx_bytes = await agent_service.export_pptx(
            artifact_id=request.artifact_id,
            canvas_format=request.canvas_format,
            theme=request.theme,
            use_native_shapes=request.use_native_shapes,
            use_compat_mode=request.use_compat_mode,
            transition=request.transition,
            animation=request.animation,
            enable_notes=request.enable_notes,
            current_user=current_user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": "attachment; filename=export.pptx"},
    )


@router.get("/ppt/slides/{session_id}")
async def get_ppt_slides(
    session_id: str,
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
):
    """Return SVG content of all slides for a session. Used for real-time preview."""
    import re
    from app.core.data_path import PPT_SESSIONS_DIR

    # 会话归属校验：非本人（且非管理员）不得读取该会话的幻灯片
    try:
        await agent_service.ensure_session_access(
            AgentStreamRequest(message="ppt_slides", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # Find the slides directory for this session
    def _find_slides_dir():
        if not PPT_SESSIONS_DIR.exists():
            return None
        for child in sorted(PPT_SESSIONS_DIR.iterdir()):
            if not child.is_dir():
                continue
            parts = child.name.split("_v", 1)
            if len(parts) == 2 and parts[0] == f"u{current_user.id}_s{session_id}":
                return child
        return None

    slides_dir = await asyncio.to_thread(_find_slides_dir)

    if slides_dir is None or not slides_dir.exists():
        return {"slides": []}

    slides = []
    for svg_file in sorted(slides_dir.glob("slide_*.svg")):
        match = re.search(r'slide_(\d+)', svg_file.name)
        if not match:
            continue
        num = int(match.group(1))
        svg_content = await asyncio.to_thread(svg_file.read_text, encoding="utf-8")
        # Inject default CSS variables for preview rendering
        css_vars = '<style>:root{--bg:#fff;--bg-soft:#f8fafc;--surface:#f1f5f9;--surface-2:#e2e8f0;--border:#e2e8f0;--border-strong:#cbd5e1;--text-1:#0f172a;--text-2:#475569;--text-3:#94a3b8;--accent:#2563eb;--accent-2:#7c3aed;--accent-3:#0891b2;--good:#16a34a;--warn:#d97706;--bad:#dc2626;}</style>'
        if '<defs>' in svg_content:
            svg_content = svg_content.replace('<defs>', f'<defs>{css_vars}', 1)
        else:
            svg_content = svg_content.replace('<svg', f'<svg>{css_vars}<defs/>', 1)
        mtime = await asyncio.to_thread(lambda f=svg_file: f.stat().st_mtime)
        slides.append({"num": num, "svg": svg_content, "updated_at": int(mtime * 1000)})

    return {"slides": sorted(slides, key=lambda s: s["num"])}


@router.get("/ppt/themes", summary="获取可用的 PPT 主题列表")
async def list_ppt_themes() -> list[dict[str, str]]:
    """返回所有可用的 PPT 主题名称和显示名称。"""
    from app.services.ppt.theme_token_resolver import list_available_themes, load_theme_tokens

    themes = []
    for name in list_available_themes():
        tokens = load_theme_tokens(name)
        # 从 tokens 中提取主色作为预览色
        primary_color = tokens.get("--accent", "#2563eb")
        bg_color = tokens.get("--bg", "#ffffff")
        text_color = tokens.get("--text-1", "#0f172a")
        themes.append({
            "name": name,
            "primary_color": primary_color,
            "bg_color": bg_color,
            "text_color": text_color,
        })
    return themes


@router.post("/ppt/{artifact_id}/retheme", summary="切换 PPT 主题并重新渲染预览")
async def retheme_ppt(
    artifact_id: str,
    request: dict[str, str],
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    """切换指定 PPT 制品的主题，返回更新后的预览 HTML。

    请求体: {"theme": "主题名称"}
    """
    from app.db.models import PptArtifactModel
    from app.services.ppt_artifact_service import PptArtifactService
    from app.services.ppt.theme_token_resolver import list_available_themes

    # 归属校验：仅资源所有者（或管理员）可切换主题
    try:
        await agent_service._ensure_record_owner(artifact_id, PptArtifactModel, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    new_theme = request.get("theme", "")
    if not new_theme:
        raise HTTPException(status_code=400, detail="theme 不能为空")

    available = list_available_themes()
    if new_theme not in available:
        raise HTTPException(
            status_code=400,
            detail=f"主题 '{new_theme}' 不存在。可用主题: {', '.join(available)}"
        )

    service = PptArtifactService()
    result = await service.retheme(artifact_id, new_theme)

    if result is None:
        raise HTTPException(status_code=404, detail="PPT 制品不存在或无法切换主题")

    return result


@router.post("/sessions/{session_id}/user-input", summary="提交用户输入（集成接口所需参数）")
async def submit_user_input(
    session_id: str,
    request: dict[str, object],
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, object]:
    """集成接口需要用户输入参数时，前端调用此接口提交用户填写的内容。"""
    return await agent_service.submit_user_input(session_id, request, current_user)


@router.post("/sessions/{session_id}/api-approval", summary="提交集成接口审批决定")
async def submit_api_approval(
    session_id: str,
    request: dict[str, object],
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, object]:
    """集成接口需要审批时，前端调用此接口提交审批决定。

    request.body:
      - approved: bool — 是否批准
      - allow_all: bool — 是否本次会话全部允许该系统
    """
    from app.services.external_system_service import ApprovalBlocker

    # 会话归属校验：非本人（且非管理员）不得替他人会话做审批决定
    try:
        await agent_service.ensure_session_access(
            AgentStreamRequest(message="api_approval", session_id=session_id), current_user
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    approved = bool(request.get("approved", False))
    allow_all = bool(request.get("allow_all", False))
    ApprovalBlocker.resolve(session_id, {"approved": approved, "allow_all": allow_all})
    return {"status": "ok", "session_id": session_id, "approved": approved, "allow_all": allow_all}
