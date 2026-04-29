from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.models import SkillModel
from app.db.session import create_db_session
from app.services.skill_service import SkillService


@dataclass(frozen=True)
class ImportedSkillResult:
    slug: str
    status: str
    name: str


class LocalSkillImportService:
    def __init__(
        self,
        settings: Settings | None = None,
        session_factory=create_db_session,
    ) -> None:
        self.settings = settings or get_settings()
        self.session_factory = session_factory

    @property
    def storage_dir(self) -> Path:
        path = self.settings.get_skill_storage_dir()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def import_from_storage(self) -> dict[str, object]:
        results: list[ImportedSkillResult] = []
        created = 0
        updated = 0
        skipped = 0

        with self.session_factory() as db:
            for entry in sorted(self.storage_dir.iterdir(), key=lambda item: item.name):
                if not entry.is_dir():
                    continue

                skill_file = entry / "SKILL.md"
                if not skill_file.is_file():
                    skipped += 1
                    results.append(
                        ImportedSkillResult(
                            slug=entry.name,
                            status="skipped",
                            name=entry.name,
                        )
                    )
                    continue

                metadata, _ = SkillService._read_skill_file(skill_file)
                name = str(metadata.get("name") or entry.name)
                description = str(metadata.get("description") or "")
                root_dir = str(entry.resolve())

                row = db.scalar(select(SkillModel).where(SkillModel.slug == entry.name))
                if row is None:
                    db.add(
                        SkillModel(
                            name=name,
                            slug=entry.name,
                            description=description,
                            root_dir=root_dir,
                            enabled=True,
                            created_by=None,
                        )
                    )
                    created += 1
                    results.append(
                        ImportedSkillResult(
                            slug=entry.name,
                            status="created",
                            name=name,
                        )
                    )
                    continue

                changed = False
                if row.name != name:
                    row.name = name
                    changed = True
                if row.description != description:
                    row.description = description
                    changed = True
                if row.root_dir != root_dir:
                    row.root_dir = root_dir
                    changed = True

                if changed:
                    db.add(row)
                    updated += 1
                    results.append(
                        ImportedSkillResult(
                            slug=entry.name,
                            status="updated",
                            name=name,
                        )
                    )
                else:
                    skipped += 1
                    results.append(
                        ImportedSkillResult(
                            slug=entry.name,
                            status="unchanged",
                            name=name,
                        )
                    )

            db.commit()

        return {
            "storage_dir": str(self.storage_dir),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "items": [
                {
                    "slug": item.slug,
                    "status": item.status,
                    "name": item.name,
                }
                for item in results
            ],
        }
