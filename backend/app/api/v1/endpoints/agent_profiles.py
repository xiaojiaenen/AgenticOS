from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_admin
from app.db.models import UserModel
from app.schemas.agent_profiles import (
    AgentProfileCreateRequest,
    AgentProfileListResponse,
    AgentProfileResponse,
    AgentProfileUpdateRequest,
)
from app.services.agent_profile_service import AgentProfileService
from app.services.agent_service import get_agent_service

router = APIRouter(tags=["Agent Profiles"])


@router.get("/agent-profiles", response_model=AgentProfileListResponse)
def list_agent_profiles(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return AgentProfileService().list_admin()


@router.post("/agent-profiles", response_model=AgentProfileResponse, status_code=status.HTTP_201_CREATED)
def create_agent_profile(
    request: AgentProfileCreateRequest,
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = AgentProfileService().create(request, current_user)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    return result


@router.patch("/agent-profiles/{profile_id}", response_model=AgentProfileResponse)
def update_agent_profile(
    profile_id: int,
    request: AgentProfileUpdateRequest,
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = AgentProfileService().update(profile_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    return result


@router.delete("/agent-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent_profile(
    profile_id: int,
    _: UserModel = Depends(require_admin),
) -> None:
    try:
        AgentProfileService().delete(profile_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()


@router.get("/agent-store", response_model=AgentProfileListResponse)
def list_agent_store(current_user: UserModel = Depends(get_current_user)) -> dict[str, object]:
    return AgentProfileService().list_store(current_user)


@router.post("/agent-store/{profile_id}/install", response_model=AgentProfileResponse)
def install_agent(
    profile_id: int,
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, object]:
    try:
        return AgentProfileService().install(profile_id, current_user)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/agent-store/{profile_id}/install", status_code=status.HTTP_204_NO_CONTENT)
def uninstall_agent(
    profile_id: int,
    current_user: UserModel = Depends(get_current_user),
) -> None:
    AgentProfileService().uninstall(profile_id, current_user)


@router.get("/my/agents", response_model=AgentProfileListResponse)
def list_my_agents(current_user: UserModel = Depends(get_current_user)) -> dict[str, object]:
    return AgentProfileService().list_user_agents(current_user)
