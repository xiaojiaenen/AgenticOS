from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.tool_config import ModeToolConfigUpdateRequest, ToolConfigResponse
from app.services import audit_service
from app.services.agent_service import get_agent_service
from app.services.tool_config_service import ToolConfigService

router = APIRouter(prefix="/tool-config", tags=["Tool Config"])


@router.get("", response_model=ToolConfigResponse)
def get_tool_config(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return ToolConfigService().list_configs()


@router.get("/catalog/labels")
def get_tool_labels(_: UserModel = Depends(get_current_user)) -> dict[str, str]:
    """工具名 → 中文标签。

    对话页的工具块只能拿到内部工具名（``write_text_file``、``calc``），
    直接展示给用户等于暴露实现细节。这里一次性把目录里的 label 发下去，
    前端缓存后本地翻译，不必为每个工具块再查一次目录。
    """
    from app.services.tool_config_service import TOOL_CATALOG

    return {name: str(item.get("label") or name) for name, item in TOOL_CATALOG.items()}


@router.put("/modes/{mode}", response_model=ToolConfigResponse)
def update_mode_tool_config(
    mode: str,
    payload: ModeToolConfigUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = ToolConfigService().update_mode(mode, [item.model_dump() for item in payload.tools])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    # 工具开关直接影响智能体能做哪些危险操作，必须留痕
    audit_service.record_request(
        db, http_request, action="tool_config.update", actor=current_user,
        resource_type="tool_config", resource_id=mode,
        detail={"mode": mode, "tools": [
            {"name": item.get("name"), "enabled": item.get("enabled")}
            for item in (payload.model_dump().get("tools") or [])
        ]},
    )
    return result
