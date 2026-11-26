"""SkillService 数据一致性回归。

- 多 skill zip：每个 skill 必须拿到自己的子树（原实现第二个落空目录）；
  任一失败整体回滚；
- FS/DB 漂移：delete 先 commit 再删目录；create commit 失败回滚目录；
  _unique_slug 同时检查文件系统孤儿目录。
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import Base, SkillModel, UserModel
from app.services.skill_service import SkillService


def _make_service(tmp_path: Path):
    db_path = tmp_path / "skills.db"
    storage_dir = tmp_path / "skills"
    storage_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    # 用真实 sessionmaker，但把 commit 定义在子类上以便 mock.patch.object
    from sqlalchemy.orm import Session as _SASession
    class PatchableSession(_SASession):
        pass

    SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False,
        expire_on_commit=False, class_=PatchableSession,
    )
    settings = Settings(
        DATABASE_URL=f"sqlite:///{db_path}",
        SKILL_STORAGE_DIR=str(storage_dir),
    )
    with SessionLocal() as db:
        creator = UserModel(
            email="creator@example.com", name="Creator",
            password_hash="x", role="admin", is_active=True,
        )
        db.add(creator)
        db.commit()
        db.refresh(creator)
        creator_id = creator.id
    return SkillService(settings=settings, session_factory=SessionLocal), SessionLocal, storage_dir, creator_id, PatchableSession


def _creator_stub(creator_id: int):
    return MagicMock(id=creator_id)


def test_multi_skill_zip_installs_both_instructions(tmp_path):
    svc, SessionLocal, storage_dir, creator_id, PatchableSession = _make_service(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "alpha/SKILL.md",
            "---\nname: Alpha\ndescription: First\n---\n\nAlpha instructions.\n",
        )
        archive.writestr("alpha/scripts/run.py", "print('alpha')\n")
        archive.writestr(
            "beta/SKILL.md",
            "---\nname: Beta\ndescription: Second\n---\n\nBeta instructions.\n",
        )
        archive.writestr("beta/references/notes.md", "# Beta notes\n")

    results = svc.upload_zip(
        filename="bundle.zip", content=buffer.getvalue(),
        creator=_creator_stub(creator_id),
    )
    assert isinstance(results, list)
    assert len(results) == 2
    instructions = {r["name"]: r["instruction"] for r in results}
    assert instructions["Alpha"].strip() == "Alpha instructions."
    assert instructions["Beta"].strip() == "Beta instructions."

    with SessionLocal() as db:
        rows = db.scalars(select(SkillModel)).all()
        assert len(rows) == 2
        for row in rows:
            assert (Path(row.root_dir) / "SKILL.md").is_file(), (
                f"{row.slug} 的 SKILL.md 不存在（落到了空目录）"
            )


def test_multi_skill_zip_rolls_back_on_partial_failure(tmp_path):
    svc, SessionLocal, storage_dir, creator_id, PatchableSession = _make_service(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("alpha/SKILL.md", "---\nname: Alpha\n---\n\nA.\n")
        archive.writestr("beta/SKILL.md", "---\nname: Beta\n---\n\nB.\n")

    # 让第二个安装失败
    original = svc._install_single_skill
    calls = {"n": 0}

    def flaky(skill_file, extract_root, creator, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated failure")
        return original(skill_file, extract_root, creator, **kwargs)

    with patch.object(svc, "_install_single_skill", side_effect=flaky):
        with pytest.raises(ValueError, match="执行失败"):
            svc.upload_zip(
                filename="bundle.zip", content=buffer.getvalue(),
                creator=_creator_stub(creator_id),
            )

    with SessionLocal() as db:
        assert db.scalars(select(SkillModel)).all() == [], "部分失败未回滚 DB 行"
    assert list(storage_dir.iterdir()) == [], "部分失败未回滚目录"


def test_create_rolls_back_directory_on_commit_failure(tmp_path):
    svc, SessionLocal, storage_dir, creator_id, PatchableSession = _make_service(tmp_path)
    from app.schemas.skills import SkillCreateRequest

    request = SkillCreateRequest(
        name="Broken", slug="broken", description="", enabled=True,
        instruction="hello",
    )
    with patch.object(PatchableSession, "commit", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError, match="db down"):
            svc.create(request, _creator_stub(creator_id))
    assert not (storage_dir / "broken").exists(), "commit 失败留下孤儿目录"


def test_delete_keeps_directory_when_commit_fails(tmp_path):
    svc, SessionLocal, storage_dir, creator_id, PatchableSession = _make_service(tmp_path)
    skill_dir = storage_dir / "kept"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: Kept\n---\n\nX.\n", encoding="utf-8")
    with SessionLocal() as db:
        db.add(SkillModel(
            name="Kept", slug="kept", description="", enabled=True,
            root_dir=str(skill_dir), created_by=creator_id,
        ))
        db.commit()

    with patch.object(PatchableSession, "commit", side_effect=RuntimeError("db down")):
        with pytest.raises(RuntimeError, match="db down"):
            svc.delete(1)
    assert skill_dir.exists(), "commit 失败时目录不应被删"


def test_unique_slug_skips_orphan_directory(tmp_path):
    svc, SessionLocal, storage_dir, creator_id, PatchableSession = _make_service(tmp_path)
    (storage_dir / "taken").mkdir()
    with SessionLocal() as db:
        slug = svc._unique_slug(db, "taken")
    assert slug != "taken"
    assert slug.startswith("taken-")
