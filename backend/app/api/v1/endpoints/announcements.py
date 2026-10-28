from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.announcements import (
    ActiveAnnouncementResponse,
    AnnouncementCreateRequest,
    AnnouncementGenerateRequest,
    AnnouncementGeneratedDraft,
    AnnouncementItem,
    AnnouncementListResponse,
    AnnouncementUpdateRequest,
)
from app.services import audit_service
from app.services.announcement_ai_service import AnnouncementAIService
from app.services.announcement_service import AnnouncementService

router = APIRouter(prefix="/announcements", tags=["Announcements"])


@router.get("/active", response_model=ActiveAnnouncementResponse)
def get_active_announcement(_: UserModel = Depends(get_current_user)) -> dict[str, object]:
    return AnnouncementService().get_active()


@router.get("", response_model=AnnouncementListResponse)
def list_announcements(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return AnnouncementService().list_admin()


@router.post("", response_model=AnnouncementItem, status_code=status.HTTP_201_CREATED)
def create_announcement(
    payload: AnnouncementCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    result = AnnouncementService().create(payload, current_user)
    audit_service.record_request(
        db, http_request, action="announcement.create", actor=current_user,
        resource_type="announcement", resource_id=result.get("id"),
        detail={"title": result.get("title"), "status": result.get("status")},
    )
    return result


@router.post("/generate", response_model=AnnouncementGeneratedDraft)
async def generate_announcement(
    payload: AnnouncementGenerateRequest,
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    # 纯生成草稿、不落库，不写审计（避免把用户提示词全文留档）
    return await AnnouncementAIService().generate_draft(payload)


@router.patch("/{announcement_id}", response_model=AnnouncementItem)
def update_announcement(
    announcement_id: int,
    payload: AnnouncementUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = AnnouncementService().update(announcement_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="announcement.update", actor=current_user,
        resource_type="announcement", resource_id=announcement_id,
        detail={"fields": sorted(payload.model_dump(exclude_none=True).keys())},
    )
    return result


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(
    announcement_id: int,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> None:
    try:
        AnnouncementService().delete(announcement_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    audit_service.record_request(
        db, http_request, action="announcement.delete", actor=current_user,
        resource_type="announcement", resource_id=announcement_id,
    )
