from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import require_admin
from app.db.models import UserModel
from app.schemas.skills import SkillCreateRequest, SkillListResponse, SkillResponse, SkillUpdateRequest
from app.services.agent_service import get_agent_service
from app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get("", response_model=SkillListResponse)
def list_skills(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return SkillService().list_admin()


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(
    request: SkillCreateRequest,
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = SkillService().create(request, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    return result


@router.post("/upload", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def upload_skill(
    file: UploadFile = File(...),
    slug: str | None = Form(default=None),
    enabled: bool = Form(default=True),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        content = await file.read()
        result = SkillService().upload_zip(
            filename=file.filename or "skill.zip",
            content=content,
            creator=current_user,
            slug=slug,
            enabled=enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    return result


@router.patch("/{skill_id}", response_model=SkillResponse)
def update_skill(
    skill_id: int,
    request: SkillUpdateRequest,
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = SkillService().update(skill_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    return result


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    _: UserModel = Depends(require_admin),
) -> None:
    try:
        SkillService().delete(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
