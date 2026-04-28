from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.timezone import isoformat_app_timezone
from app.db.models import AgentProfileSkillModel, SkillModel, UserModel
from app.db.session import create_db_session
from app.schemas.skills import SkillCreateRequest, SkillUpdateRequest


@dataclass(frozen=True)
class RuntimeSkill:
    id: int
    name: str
    slug: str
    root_dir: str
    updated_at: str


class SkillService:
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

    def list_admin(self) -> dict[str, object]:
        with self.session_factory() as db:
            rows = db.scalars(select(SkillModel).order_by(SkillModel.created_at.asc())).all()
            return {"items": [self._serialize(row) for row in rows]}

    def list_references(self, *, enabled_only: bool = True) -> list[dict[str, object]]:
        with self.session_factory() as db:
            rows = self._load_skill_rows(db, enabled_only=enabled_only)
            return [self._serialize_reference(row) for row in rows]

    def create(self, request: SkillCreateRequest, creator: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            slug = self._unique_slug(db, request.slug or request.name)
            skill_dir = self._storage_entry_dir(slug)
            skill_dir.mkdir(parents=True, exist_ok=False)
            skill_path = skill_dir / "SKILL.md"
            skill_path.write_text(
                self._render_skill_markdown(
                    name=request.name,
                    description=request.description,
                    instruction=request.instruction,
                ),
                encoding="utf-8",
            )

            row = SkillModel(
                name=request.name,
                slug=slug,
                description=request.description,
                enabled=request.enabled,
                root_dir=str(skill_dir),
                created_by=creator.id,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._serialize(row)

    def update(self, skill_id: int, request: SkillUpdateRequest) -> dict[str, object]:
        with self.session_factory() as db:
            row = db.get(SkillModel, skill_id)
            if row is None:
                raise KeyError("Skill not found")

            old_slug = row.slug
            old_entry_dir = self._storage_entry_dir(old_slug)
            old_root_dir = Path(row.root_dir)

            if request.slug is not None:
                row.slug = self._unique_slug(db, request.slug, ignore_id=row.id)

            if request.slug is not None and row.slug != old_slug:
                new_entry_dir = self._storage_entry_dir(row.slug)
                if new_entry_dir.exists():
                    raise ValueError(f"Skill directory already exists: {row.slug}")
                if old_entry_dir.exists():
                    shutil.move(str(old_entry_dir), str(new_entry_dir))
                else:
                    new_entry_dir.mkdir(parents=True, exist_ok=True)

                try:
                    relative_root = old_root_dir.relative_to(old_entry_dir)
                except ValueError:
                    relative_root = Path()
                row.root_dir = str(new_entry_dir / relative_root)

            if request.name is not None:
                row.name = request.name
            if request.description is not None:
                row.description = request.description
            if request.enabled is not None:
                row.enabled = request.enabled

            if (
                request.name is not None
                or request.description is not None
                or request.instruction is not None
                or request.slug is not None
            ):
                current_meta, current_instruction = self._read_skill_file(Path(row.root_dir) / "SKILL.md")
                skill_path = Path(row.root_dir) / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                skill_path.write_text(
                    self._render_skill_markdown(
                        name=row.name,
                        description=row.description,
                        instruction=request.instruction or current_instruction or current_meta.get("instruction", ""),
                    ),
                    encoding="utf-8",
                )

            db.add(row)
            db.commit()
            db.refresh(row)
            return self._serialize(row)

    def upload_zip(
        self,
        *,
        filename: str,
        content: bytes,
        creator: UserModel,
        slug: str | None = None,
        enabled: bool = True,
    ) -> dict[str, object]:
        if not filename.lower().endswith(".zip"):
            raise ValueError("Only .zip skill packages are supported")

        with tempfile.TemporaryDirectory(prefix="agenticos-skill-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            archive_path = temp_dir / filename
            archive_path.write_bytes(content)

            with zipfile.ZipFile(archive_path) as archive:
                self._validate_zip_members(archive)
                archive.extractall(temp_dir / "src")

            extract_root = temp_dir / "src"
            skill_files = sorted(extract_root.rglob("SKILL.md"))
            if len(skill_files) != 1:
                raise ValueError("Uploaded package must contain exactly one SKILL.md")

            skill_file = skill_files[0]
            meta, instruction = self._read_skill_file(skill_file)
            requested_slug = slug or str(meta.get("slug") or meta.get("name") or Path(filename).stem)

            with self.session_factory() as db:
                unique_slug = self._unique_slug(db, requested_slug)
                entry_dir = self._storage_entry_dir(unique_slug)
                entry_dir.mkdir(parents=True, exist_ok=False)

                for child in extract_root.iterdir():
                    shutil.move(str(child), str(entry_dir / child.name))

                relative_root = skill_file.parent.relative_to(extract_root)
                stored_root = entry_dir / relative_root

                row = SkillModel(
                    name=str(meta.get("name") or unique_slug),
                    slug=unique_slug,
                    description=str(meta.get("description") or ""),
                    enabled=enabled,
                    root_dir=str(stored_root),
                    created_by=creator.id,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return self._serialize(row)

    def delete(self, skill_id: int) -> None:
        with self.session_factory() as db:
            row = db.get(SkillModel, skill_id)
            if row is None:
                raise KeyError("Skill not found")

            entry_dir = self._storage_entry_dir(row.slug)
            db.execute(delete(AgentProfileSkillModel).where(AgentProfileSkillModel.skill_id == row.id))
            db.delete(row)
            db.commit()

        if entry_dir.exists():
            shutil.rmtree(entry_dir, ignore_errors=True)

    def get_runtime_skills(self, skill_ids: list[int]) -> tuple[RuntimeSkill, ...]:
        if not skill_ids:
            return ()
        with self.session_factory() as db:
            rows = (
                db.scalars(
                    select(SkillModel)
                    .where(SkillModel.id.in_(skill_ids), SkillModel.enabled.is_(True))
                    .order_by(SkillModel.id.asc())
                ).all()
            )
            return tuple(
                RuntimeSkill(
                    id=row.id,
                    name=row.name,
                    slug=row.slug,
                    root_dir=row.root_dir,
                    updated_at=isoformat_app_timezone(row.updated_at) or "",
                )
                for row in rows
            )

    def _load_skill_rows(self, db: Session, *, enabled_only: bool) -> list[SkillModel]:
        statement = select(SkillModel).order_by(SkillModel.name.asc())
        if enabled_only:
            statement = statement.where(SkillModel.enabled.is_(True))
        return db.scalars(statement).all()

    def _serialize_reference(self, row: SkillModel) -> dict[str, object]:
        scripts = self._list_scripts(Path(row.root_dir))
        return {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "enabled": row.enabled,
            "has_python_scripts": bool(scripts),
            "script_paths": scripts,
        }

    def _serialize(self, row: SkillModel) -> dict[str, object]:
        skill_path = Path(row.root_dir) / "SKILL.md"
        _, instruction = self._read_skill_file(skill_path)
        scripts = self._list_scripts(Path(row.root_dir))
        return {
            "id": row.id,
            "name": row.name,
            "slug": row.slug,
            "description": row.description,
            "enabled": row.enabled,
            "instruction": instruction,
            "root_dir": row.root_dir,
            "has_python_scripts": bool(scripts),
            "script_paths": scripts,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _storage_entry_dir(self, slug: str) -> Path:
        return self.storage_dir / slug

    @staticmethod
    def _list_scripts(root_dir: Path) -> list[str]:
        scripts_dir = root_dir / "scripts"
        if not scripts_dir.is_dir():
            return []
        return sorted(path.relative_to(root_dir).as_posix() for path in scripts_dir.rglob("*.py"))

    @staticmethod
    def _validate_zip_members(archive: zipfile.ZipFile) -> None:
        for member in archive.infolist():
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe file path in archive: {member.filename}")

    @staticmethod
    def _render_skill_markdown(*, name: str, description: str, instruction: str) -> str:
        frontmatter = yaml.safe_dump(
            {"name": name, "description": description},
            allow_unicode=True,
            sort_keys=False,
        ).strip()
        body = instruction.strip()
        return f"---\n{frontmatter}\n---\n\n{body}\n"

    @staticmethod
    def _read_skill_file(path: Path) -> tuple[dict[str, object], str]:
        if not path.is_file():
            return {}, ""

        content = path.read_text(encoding="utf-8")
        stripped = content.strip()
        if not stripped.startswith("---"):
            return {}, stripped

        parts = stripped.split("---", 2)
        if len(parts) < 3:
            return {}, stripped

        try:
            metadata = yaml.safe_load(parts[1].strip()) or {}
        except yaml.YAMLError:
            metadata = {}

        if not isinstance(metadata, dict):
            metadata = {}
        return metadata, parts[2].strip()

    def _unique_slug(self, db: Session, base: str, *, ignore_id: int | None = None) -> str:
        base_slug = self._slugify(base)
        slug = base_slug
        index = 2
        while True:
            existing = db.scalar(select(SkillModel).where(SkillModel.slug == slug))
            if existing is None or existing.id == ignore_id:
                return slug
            slug = f"{base_slug}-{index}"
            index += 1

    @staticmethod
    def _slugify(value: str) -> str:
        cleaned = value.strip().lower().replace("_", "-").replace(" ", "-")
        parts = [char for char in cleaned if char.isalnum() or char == "-"]
        slug = "".join(parts).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug or "skill"
