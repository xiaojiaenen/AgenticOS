import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas.agent import AgentStreamRequest
from app.services.agent_service import AgentService, get_agent_service

router = APIRouter(prefix="/agent", tags=["智能体"])


def _format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream", summary="以流式方式返回 Wuwei 智能体响应")
async def stream_agent(
    request: AgentStreamRequest,
    agent_service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    try:
        agent_service.ensure_ready()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def event_stream():
        try:
            async for event in agent_service.stream_chat(request):
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
