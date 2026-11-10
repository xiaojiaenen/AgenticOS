"""内置智能体可被管理员改写 + 一键还原；启动播种不覆盖人工修改。

历史行为：``_assert_can_manage`` 对 ``is_builtin`` 一律 403，管理员
连改个错别字都做不到。现在改为：内置智能体只有管理员能改，改过的
行打 ``customized_at`` 标记，启动播种不再用代码默认值覆盖它。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import AgentProfileModel, AgentProfileSkillModel, Base, SkillModel, UserModel
from app.schemas.agent_profiles import AgentProfileUpdateRequest
from app.services import agent_profile_service as aps
from app.services.agent_profile_service import BUILTIN_AGENT_SKILLS, AgentProfileService


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _admin(db: Session) -> UserModel:
    user = UserModel(
        email="admin@example.com",
        name="admin",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _service(db: Session) -> AgentProfileService:
    return AgentProfileService(session_factory=lambda: db)


def reset_seed_cache() -> None:
    aps._ensure_defaults_last_run = 0.0


def _seed_skills(db: Session, slugs: list[str]) -> None:
    for slug in slugs:
        db.add(SkillModel(name=slug, slug=slug, root_dir="/tmp/" + slug, description="", enabled=True))
    db.commit()


def test_builtin_profile_is_editable_by_admin(session):
    admin = _admin(session)
    service = _service(session)
    reset_seed_cache()
    service.ensure_defaults(session)

    profile = session.query(AgentProfileModel).filter_by(slug="ppt").one()
    assert profile.is_builtin is True

    request = AgentProfileUpdateRequest(name="PPT 设计专家（改）")
    service.update(profile.id, request, admin)

    profile = session.get(AgentProfileModel, profile.id)
    assert profile.name == "PPT 设计专家（改）"
    # 改过就落标记，否则下次启动会被默认值覆盖回「PPT 设计师」
    assert profile.customized_at is not None


def test_restore_defaults_resets_name_and_clears_marker(session):
    admin = _admin(session)
    service = _service(session)
    reset_seed_cache()
    service.ensure_defaults(session)

    profile = session.query(AgentProfileModel).filter_by(slug="ppt").one()
    original_name = profile.name
    service.update(profile.id, AgentProfileUpdateRequest(name="临时改名"), admin)

    restored = service.restore_defaults(profile.id, admin)

    assert restored["name"] == original_name
    profile = session.get(AgentProfileModel, profile.id)
    assert profile.customized_at is None


def test_seed_does_not_overwrite_customized_builtin(session):
    _admin(session)
    service = _service(session)
    reset_seed_cache()
    service.ensure_defaults(session)

    profile = session.query(AgentProfileModel).filter_by(slug="general").one()
    profile.name = "被我改过的名字"
    profile.customized_at = aps.app_now()
    session.commit()

    reset_seed_cache()
    service.ensure_defaults(session)

    profile = session.get(AgentProfileModel, profile.id)
    assert profile.name == "被我改过的名字"


def test_builtin_agent_skills_are_wired(session):
    """内置智能体此前一个 Skill 都没绑：PPT 设计师不知道设计规范。"""
    _admin(session)
    wanted = set()
    for slugs in BUILTIN_AGENT_SKILLS.values():
        wanted.update(slugs)
    _seed_skills(session, sorted(wanted))

    service = _service(session)
    reset_seed_cache()
    service.ensure_defaults(session)

    ppt = session.query(AgentProfileModel).filter_by(slug="ppt").one()
    bound = {
        row.slug
        for row in session.query(SkillModel)
        .join(AgentProfileSkillModel, AgentProfileSkillModel.skill_id == SkillModel.id)
        .filter(AgentProfileSkillModel.profile_id == ppt.id)
    }
    assert bound, "PPT 设计师一个 Skill 都没绑上"
