from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.agent_profiles import (
    AgentProfileCreateRequest,
    AgentProfileListResponse,
    AgentProfileResponse,
    AgentProfileUpdateRequest,
)
from app.services import audit_service
from app.services.agent_profile_service import AgentProfileService
from app.services.agent_service import get_agent_service

router = APIRouter(tags=["Agent Profiles"])


@router.get("/agent-profiles", response_model=AgentProfileListResponse)
def list_agent_profiles(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return AgentProfileService().list_admin()


@router.post("/agent-profiles", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
def create_agent_profile(
    payload: AgentProfileCreateRequest,
    http_request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """创建智能体。普通用户创建的自建智能体归本人所有；管理员可发布到商店。"""
    try:
        result = AgentProfileService().create(payload, current_user)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="agent_profile.create", actor=current_user,
        resource_type="agent_profile", resource_id=result.get("id"),
        detail={"name": result.get("name"), "slug": result.get("slug")},
    )
    return result


@router.patch("/agent-profiles/{profile_id}", response_model=AgentProfileResponse)
def update_agent_profile(
    profile_id: int,
    payload: AgentProfileUpdateRequest,
    http_request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        result = AgentProfileService().update(profile_id, payload, current_user)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="agent_profile.update", actor=current_user,
        resource_type="agent_profile", resource_id=profile_id,
        detail={"fields": sorted(payload.model_dump(exclude_none=True).keys())},
    )
    return result


@router.delete("/agent-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_profile(
    profile_id: int,
    http_request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        AgentProfileService().delete(profile_id, current_user)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="agent_profile.delete", actor=current_user,
        resource_type="agent_profile", resource_id=profile_id,
    )


@router.get("/agent-store", response_model=AgentProfileListResponse)
def list_agent_store(current_user: UserModel = Depends(get_current_user)) -> dict[str, object]:
    return AgentProfileService().list_store(current_user)


@router.post("/agent-store/{profile_id}/install", response_model=AgentProfileResponse)
def install_agent(
    profile_id: int,
    http_request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    try:
        result = AgentProfileService().install(profile_id, current_user)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="agent_store.install", actor=current_user,
        resource_type="agent_profile", resource_id=profile_id,
    )
    return result


@router.delete("/agent-store/{profile_id}/install", status_code=status.HTTP_204_NO_CONTENT)
def uninstall_agent(
    profile_id: int,
    http_request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    AgentProfileService().uninstall(profile_id, current_user)
    audit_service.record_request(
        db, http_request, action="agent_store.uninstall", actor=current_user,
        resource_type="agent_profile", resource_id=profile_id,
    )


@router.get("/my/agents", response_model=AgentProfileListResponse)
def list_my_agents(current_user: UserModel = Depends(get_current_user)) -> dict[str, object]:
    return AgentProfileService().list_user_agents(current_user)
