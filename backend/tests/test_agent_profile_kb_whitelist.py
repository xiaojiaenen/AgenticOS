"""智能体 KB 白名单一致性回归（create/update/restore_defaults/版本快照回滚）。

统一口径：存在 + is_active + 对当前用户可见。四个入口必须一致。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.models import (
    AgentProfileModel,
    AgentProfileVersionModel,
    Base,
    KnowledgeBaseModel,
    UserModel,
)
from app.schemas.agent_profiles import AgentProfileCreateRequest, AgentProfileUpdateRequest
from app.services.agent_profile_service import AgentProfileService


def _setup(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path/'profiles.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    service = AgentProfileService(session_factory=SessionLocal)
    with SessionLocal() as db:
        owner = UserModel(
            email="owner@example.com", name="Owner", password_hash="x",
            role="user", is_active=True,
        )
        outsider = UserModel(
            email="outsider@example.com", name="Outsider", password_hash="x",
            role="user", is_active=True,
        )
        db.add_all([owner, outsider])
        db.commit()
        db.refresh(owner)
        db.refresh(outsider)
        # kb ids: 1 public+active, 2 private+active(owner), 3 inactive, 4 private(other owner)
        db.add_all([
            KnowledgeBaseModel(id=1, name="Pub", slug="pub", owner_id=owner.id,
                               scope="org", visibility="public", is_active=True),
            KnowledgeBaseModel(id=2, name="Priv", slug="priv", owner_id=owner.id,
                               scope="personal", visibility="private", is_active=True),
            KnowledgeBaseModel(id=3, name="Inactive", slug="inactive", owner_id=owner.id,
                               scope="org", visibility="public", is_active=False),
            KnowledgeBaseModel(id=4, name="Other", slug="other", owner_id=outsider.id,
                               scope="personal", visibility="private", is_active=True),
        ])
        db.commit()
        owner_id, outsider_id = owner.id, outsider.id
    return service, SessionLocal, owner_id, outsider_id


def _owner(SessionLocal, uid):
    with SessionLocal() as db:
        return db.get(UserModel, uid)


def test_create_validates_kb_ids(tmp_path):
    svc, SessionLocal, owner_id, _ = _setup(tmp_path)
    with pytest.raises(KeyError):
        svc.create(
            AgentProfileCreateRequest(
                name="Bad", response_mode="general", enabled=True, system_prompt="p",
                knowledge_base_ids=[3],  # inactive
            ),
            _owner(SessionLocal, owner_id),
        )
    with SessionLocal() as db:
        assert db.scalars(select(AgentProfileModel)).all() == []

    result = svc.create(
        AgentProfileCreateRequest(
            name="Good", response_mode="general", enabled=True, system_prompt="p",
            knowledge_base_ids=[1, 2],  # public + owner-private
        ),
        _owner(SessionLocal, owner_id),
    )
    assert set(result["knowledge_base_ids"]) == {1, 2}


def test_update_rejects_inactive_and_invisible(tmp_path):
    svc, SessionLocal, owner_id, outsider_id = _setup(tmp_path)
    profile = svc.create(
        AgentProfileCreateRequest(name="P", response_mode="general", enabled=True, system_prompt="p"),
        _owner(SessionLocal, owner_id),
    )
    pid = profile["id"]
    with pytest.raises(KeyError):
        svc.update(pid, AgentProfileUpdateRequest(knowledge_base_ids=[3]),
                   _owner(SessionLocal, owner_id))
    with pytest.raises(KeyError):
        svc.update(pid, AgentProfileUpdateRequest(knowledge_base_ids=[4]),
                   _owner(SessionLocal, owner_id))
    # 合法：public + 自己的 private
    updated = svc.update(pid, AgentProfileUpdateRequest(knowledge_base_ids=[1, 2]),
                         _owner(SessionLocal, owner_id))
    assert set(updated["knowledge_base_ids"]) == {1, 2}


def test_restore_defaults_clears_kb_whitelist(tmp_path):
    svc, SessionLocal, owner_id, _ = _setup(tmp_path)
    # 造一个内置 profile 并绑定 KB
    with SessionLocal() as db:
        db.add(AgentProfileModel(
            name="General", slug="general", response_mode="general",
            system_prompt="p", is_builtin=True, enabled=True, created_by=owner_id, owner_id=owner_id,
            visibility="private", knowledge_base_ids_json="[1, 2]",
        ))
        db.commit()
        pid = db.scalar(select(AgentProfileModel.id).where(AgentProfileModel.slug == "general"))
    restored = svc.restore_defaults(pid, _owner(SessionLocal, owner_id))
    assert restored["knowledge_base_ids"] == []


def test_version_snapshot_and_rollback_include_kb_ids(tmp_path):
    svc, SessionLocal, owner_id, _ = _setup(tmp_path)
    profile = svc.create(
        AgentProfileCreateRequest(
            name="P", response_mode="general", enabled=True, system_prompt="p",
            knowledge_base_ids=[1],
        ),
        _owner(SessionLocal, owner_id),
    )
    pid = profile["id"]
    v1 = svc.save_profile_version(pid, created_by=owner_id)
    # 改成另一个白名单
    svc.update(pid, AgentProfileUpdateRequest(knowledge_base_ids=[2]),
               _owner(SessionLocal, owner_id))
    snapshot = svc.get_profile_version(pid, v1)
    assert set(snapshot["config"]["knowledge_base_ids"]) == {1}
    assert svc.restore_profile_version(pid, v1) is True
    with SessionLocal() as db:
        row = db.get(AgentProfileModel, pid)
        assert set(__import__("json").loads(row.knowledge_base_ids_json)) == {1}
