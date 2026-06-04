from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_admin
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
    request: AnnouncementCreateRequest,
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    return AnnouncementService().create(request, current_user)


@router.post("/generate", response_model=AnnouncementGeneratedDraft)
async def generate_announcement(
    request: AnnouncementGenerateRequest,
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    return await AnnouncementAIService().generate_draft(request)


@router.patch("/{announcement_id}", response_model=AnnouncementItem)
def update_announcement(
    announcement_id: int,
    request: AnnouncementUpdateRequest,
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        return AnnouncementService().update(announcement_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(
    announcement_id: int,
    _: UserModel = Depends(require_admin),
) -> None:
    try:
        AnnouncementService().delete(announcement_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
