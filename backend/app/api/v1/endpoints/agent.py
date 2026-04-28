import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.db.models import UserModel
from app.schemas.agent import AgentStreamRequest, ApprovalDecisionRequest
from app.services.agent_service import AgentService, get_agent_service

router = APIRouter(prefix="/agent", tags=["智能体"])


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
        try:
            async for event in agent_service.stream_chat(request, current_user):
                yield _format_sse(event["event"], event["data"])
        except Exception as exc:
            yield _format_sse("error", {"message": str(exc)})

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
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    try:
        return await agent_service.decide_approval(
            approval_id,
            status=request.status,
            reason=request.reason,
        )
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


@router.get("/artifacts/{artifact_id}", summary="获取 PPT 制品预览")
async def get_ppt_artifact(
    artifact_id: str,
    agent_service: AgentService = Depends(get_agent_service),
) -> dict[str, Any]:
    artifact = await agent_service.get_ppt_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="PPT 制品不存在。")
    return artifact
