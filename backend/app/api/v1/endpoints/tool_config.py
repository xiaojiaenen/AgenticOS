from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.db.models import UserModel
from app.schemas.tool_config import ModeToolConfigUpdateRequest, ToolConfigResponse
from app.services.agent_service import get_agent_service
from app.services.tool_config_service import ToolConfigService

router = APIRouter(prefix="/tool-config", tags=["Tool Config"])


@router.get("", response_model=ToolConfigResponse)
def get_tool_config(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return ToolConfigService().list_configs()


@router.put("/modes/{mode}", response_model=ToolConfigResponse)
def update_mode_tool_config(
    mode: str,
    request: ModeToolConfigUpdateRequest,
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = ToolConfigService().update_mode(mode, [item.model_dump() for item in request.tools])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    return result
