from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timezone import app_now, to_app_timezone
from app.db.models import AnnouncementModel, UserModel
from app.db.session import create_db_session
from app.schemas.announcements import AnnouncementCreateRequest, AnnouncementUpdateRequest


class AnnouncementService:
    def __init__(self, session_factory: Callable[[], Session] = create_db_session) -> None:
        self.session_factory = session_factory

    def list_admin(self) -> dict[str, object]:
        with self.session_factory() as db:
            rows = db.scalars(
                select(AnnouncementModel).order_by(
                    AnnouncementModel.updated_at.desc(),
                    AnnouncementModel.id.desc(),
                )
            ).all()
            return {"items": [self._serialize(row) for row in rows]}

    def get_active(self) -> dict[str, object]:
        with self.session_factory() as db:
            row = self._get_active_row(db)
            return {"item": self._serialize(row) if row is not None else None}

    def create(self, request: AnnouncementCreateRequest, creator: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            payload = request.model_dump()
            self._validate_payload(payload)
            row = AnnouncementModel(
                eyebrow=payload["eyebrow"],
                title=payload["title"],
                subtitle=payload["subtitle"],
                body=payload["body"],
                image_url=payload.get("image_url"),
                content_format=payload["content_format"],
                theme=payload["theme"],
                cta_label=payload["cta_label"],
                cta_link=payload["cta_link"],
                is_published=payload["is_published"],
                dismissible=payload["dismissible"],
                show_once=payload["show_once"],
                starts_at=to_app_timezone(payload["starts_at"]),
                ends_at=to_app_timezone(payload["ends_at"]),
                created_by=creator.id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._serialize(row)

    def update(self, announcement_id: int, request: AnnouncementUpdateRequest) -> dict[str, object]:
        with self.session_factory() as db:
            row = db.get(AnnouncementModel, announcement_id)
            if row is None:
                raise KeyError("Announcement not found")

            payload = request.model_dump(exclude_unset=True)
            if not payload:
                return self._serialize(row)

            merged = {
                "eyebrow": row.eyebrow,
                "title": row.title,
                "subtitle": row.subtitle,
                "body": row.body,
                "image_url": row.image_url,
                "content_format": row.content_format,
                "theme": row.theme,
                "cta_label": row.cta_label,
                "cta_link": row.cta_link,
                "is_published": row.is_published,
                "dismissible": row.dismissible,
                "show_once": row.show_once,
                "starts_at": row.starts_at,
                "ends_at": row.ends_at,
            }
            merged.update(payload)
            self._validate_payload(merged)

            for key, value in payload.items():
                if key in {"starts_at", "ends_at"}:
                    setattr(row, key, to_app_timezone(value))
                else:
                    setattr(row, key, value)

            db.commit()
            db.refresh(row)
            return self._serialize(row)

    def delete(self, announcement_id: int) -> None:
        with self.session_factory() as db:
            row = db.get(AnnouncementModel, announcement_id)
            if row is None:
                raise KeyError("Announcement not found")
            db.delete(row)
            db.commit()

    @staticmethod
    def _validate_payload(payload: dict[str, object]) -> None:
        starts_at = payload.get("starts_at")
        ends_at = payload.get("ends_at")
        if starts_at is not None and ends_at is not None and starts_at > ends_at:
            raise ValueError("Announcement end time must be later than start time")

        cta_label = payload.get("cta_label")
        cta_link = payload.get("cta_link")
        if bool(cta_label) ^ bool(cta_link):
            raise ValueError("CTA label and CTA link must be configured together")

    def _get_active_row(self, db: Session) -> AnnouncementModel | None:
        rows = db.scalars(
            select(AnnouncementModel).where(AnnouncementModel.is_published.is_(True)).order_by(
                AnnouncementModel.updated_at.desc(),
                AnnouncementModel.id.desc(),
            )
        ).all()
        for row in rows:
            if self._is_active(row):
                return row
        return None

    @staticmethod
    def _is_active(row: AnnouncementModel) -> bool:
        now = app_now()
        if not row.is_published:
            return False
        if row.starts_at is not None and row.starts_at > now:
            return False
        if row.ends_at is not None and row.ends_at < now:
            return False
        return True

    def _serialize(self, row: AnnouncementModel | None) -> dict[str, object]:
        if row is None:
            raise KeyError("Announcement not found")
        return {
            "id": row.id,
            "eyebrow": row.eyebrow,
            "title": row.title,
            "subtitle": row.subtitle,
            "body": row.body,
            "image_url": row.image_url,
            "content_format": row.content_format,
            "theme": row.theme,
            "cta_label": row.cta_label,
            "cta_link": row.cta_link,
            "is_published": row.is_published,
            "dismissible": row.dismissible,
            "show_once": row.show_once,
            "starts_at": row.starts_at,
            "ends_at": row.ends_at,
            "active_now": self._is_active(row),
            "created_by": row.created_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
