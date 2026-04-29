from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import Base, SkillModel
from app.services.local_skill_import_service import LocalSkillImportService


def test_import_from_storage_creates_and_updates_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    storage_dir = tmp_path / "skills"
    storage_dir.mkdir(parents=True, exist_ok=True)

    skill_dir = storage_dir / "dinky-sql-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Dinky SQL Skill\ndescription: Generate Dinky SQL.\n---\n\nUse it.\n",
        encoding="utf-8",
    )

    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    settings = Settings(
        DATABASE_URL=f"sqlite:///{database_path}",
        SKILL_STORAGE_DIR=str(storage_dir),
    )

    service = LocalSkillImportService(
        settings=settings,
        session_factory=SessionLocal,
    )
    first_result = service.import_from_storage()
    assert first_result["created"] == 1

    with SessionLocal() as db:
        row = db.scalar(select(SkillModel).where(SkillModel.slug == "dinky-sql-skill"))
        assert row is not None
        assert row.name == "Dinky SQL Skill"
        assert row.description == "Generate Dinky SQL."

    (skill_dir / "SKILL.md").write_text(
        "---\nname: Dinky SQL Skill\ndescription: Updated description.\n---\n\nUse it.\n",
        encoding="utf-8",
    )
    second_result = service.import_from_storage()
    assert second_result["updated"] == 1

    with SessionLocal() as db:
        row = db.scalar(select(SkillModel).where(SkillModel.slug == "dinky-sql-skill"))
        assert row is not None
        assert row.description == "Updated description."
