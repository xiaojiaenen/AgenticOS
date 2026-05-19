import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.schemas.agent import AgentStreamRequest, ApprovalDecisionRequest, PptExportRequest
from app.services.agent_service import AgentService, get_agent_service
from app.services.design_system import get_design_system_registry

router = APIRouter(prefix="/agent", tags=["智能体"])

_logger = logging.getLogger("agent.stream")


def _format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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


@router.get("/sessions", summary="获取当前用户的会话列表")
async def list_sessions(
    current_user: UserModel = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> list[dict[str, Any]]:
    return await agent_service.list_user_sessions(current_user.id)


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
    agent_service: AgentService = Depends(get_agent_service),
) -> Response:
    """Return an HTML page that displays all SVG slides with keyboard navigation."""
    artifact = await agent_service.get_ppt_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"PPT artifact '{artifact_id}' not found")

    svgs = agent_service.ppt_artifacts.extract_svgs_from_artifact(artifact)
    if not svgs:
        raise HTTPException(status_code=400, detail="Artifact contains no SVG slides")

    slides_html = "".join(svgs)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{artifact.get("title", "PPT Preview")}</title>
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
    return Response(content=html, media_type="text/html; charset=utf-8")


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
        headers={"Content-Disposition": f"attachment; filename=export.pptx"},
    )
