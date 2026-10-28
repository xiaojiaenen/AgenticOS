from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.db.models import UserModel
from app.schemas.skills import SkillCreateRequest, SkillListResponse, SkillResponse, SkillUpdateRequest
from app.services import audit_service
from app.services.agent_service import get_agent_service
from app.services.skill_service import SkillService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get("", response_model=SkillListResponse)
def list_skills(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return SkillService().list_admin()


@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
def create_skill(
    payload: SkillCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = SkillService().create(payload, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="skill.create", actor=current_user,
        resource_type="skill", resource_id=result.get("id"),
        detail={"slug": result.get("slug"), "name": result.get("name")},
    )
    return result


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_skill(
    http_request: Request,
    file: UploadFile = File(...),
    slug: str | None = Form(default=None),
    enabled: bool = Form(default=True),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    """上传 skill zip 包。支持单 skill 或多 skill 打包上传。"""
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
    # 多 skill 上传返回列表，单 skill 保持兼容
    if isinstance(result, list):
        audit_service.record_request(
            db, http_request, action="skill.upload", actor=current_user,
            resource_type="skill", detail={"filename": file.filename, "count": len(result),
                                           "slugs": [item.get("slug") for item in result]},
        )
        return {"items": result, "count": len(result)}
    audit_service.record_request(
        db, http_request, action="skill.upload", actor=current_user,
        resource_type="skill", resource_id=result.get("id"),
        detail={"filename": file.filename, "slug": result.get("slug")},
    )
    return result


@router.patch("/{skill_id}", response_model=SkillResponse)
def update_skill(
    skill_id: int,
    payload: SkillUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = SkillService().update(skill_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="skill.update", actor=current_user,
        resource_type="skill", resource_id=skill_id,
        detail=payload.model_dump(exclude_none=True),
    )
    return result


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> None:
    try:
        SkillService().delete(skill_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="skill.delete", actor=current_user,
        resource_type="skill", resource_id=skill_id,
    )
