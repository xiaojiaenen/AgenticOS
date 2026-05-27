from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import AgentProfileModel, AgentProfileToolModel, AgentToolConfigModel, Base
from app.prompts import WEBSITE_ROUTER_PROMPT
from app.services.agent_profile_service import AgentProfileService
from app.services.tool_config_service import DEFAULT_MODE_TOOLS, ToolConfigService


def test_website_prompt_contains_directory_and_build_rules() -> None:
    assert "copy_template(stack)" in WEBSITE_ROUTER_PROMPT
    assert "check_website_project()" in WEBSITE_ROUTER_PROMPT
    assert "build_website(" in WEBSITE_ROUTER_PROMPT


def test_website_mode_enables_npm_by_default() -> None:
    assert DEFAULT_MODE_TOOLS["website"]["npm"]["enabled"] is True
    assert DEFAULT_MODE_TOOLS["website"]["npm"]["requires_approval"] is True


def test_existing_website_defaults_are_upgraded(tmp_path: Path) -> None:
    database_path = tmp_path / "website-mode.db"
    engine = create_engine(f"sqlite:///{database_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with SessionLocal() as db:
        profile = AgentProfileModel(
            name="\u7f51\u7ad9\u5de5\u7a0b\u5e08",
            slug="website",
            description="\u65e7\u63cf\u8ff0",
            system_prompt="\u4f60\u662f AgenticOS \u7684\u7f51\u7ad9\u4e0e\u524d\u7aef\u52a9\u624b\uff0c\u8bf7\u4f18\u5148\u63d0\u4f9b\u9875\u9762\u7ed3\u6784\u3001\u4ea4\u4e92\u8bf4\u660e\u548c\u53ef\u8fd0\u884c\u4ee3\u7801\u3002",
            response_mode="website",
            avatar="globe",
            enabled=True,
            listed=True,
            is_builtin=True,
        )
        db.add(profile)
        db.flush()
        db.add(
            AgentProfileToolModel(
                profile_id=profile.id,
                tool_name="npm",
                enabled=False,
                requires_approval=True,
            )
        )
        db.add(
            AgentToolConfigModel(
                mode="website",
                tool_name="npm",
                enabled=False,
                requires_approval=True,
            )
        )
        db.commit()

    ToolConfigService(session_factory=SessionLocal).list_configs()
    AgentProfileService(session_factory=SessionLocal).list_admin()

    with SessionLocal() as db:
        mode_row = db.scalar(
            select(AgentToolConfigModel).where(
                AgentToolConfigModel.mode == "website",
                AgentToolConfigModel.tool_name == "npm",
            )
        )
        assert mode_row is not None
        assert mode_row.enabled is True

        profile = db.scalar(select(AgentProfileModel).where(AgentProfileModel.slug == "website"))
        assert profile is not None
        assert "copy_template(stack)" in profile.system_prompt

        profile_tool = db.scalar(
            select(AgentProfileToolModel).where(
                AgentProfileToolModel.profile_id == profile.id,
                AgentProfileToolModel.tool_name == "npm",
            )
        )
        assert profile_tool is not None
        assert profile_tool.enabled is True
