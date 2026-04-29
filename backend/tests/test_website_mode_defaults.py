from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import AgentProfileModel, AgentProfileToolModel, AgentToolConfigModel, Base
from app.prompts import WEBSITE_SYSTEM_PROMPT
from app.services.agent_profile_service import AgentProfileService
from app.services.tool_config_service import DEFAULT_MODE_TOOLS, ToolConfigService


def test_website_prompt_contains_directory_and_build_rules() -> None:
    assert "data/websites/<project_slug>/" in WEBSITE_SYSTEM_PROMPT
    assert "npm install" in WEBSITE_SYSTEM_PROMPT
    assert "npm run build" in WEBSITE_SYSTEM_PROMPT
    assert "不要随便引入依赖" in WEBSITE_SYSTEM_PROMPT


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
            name="网站工程师",
            slug="website",
            description="旧描述",
            system_prompt="你是 AgenticOS 的网站与前端助手，请优先提供页面结构、交互说明和可运行代码。",
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
        assert "data/websites/<project_slug>/" in profile.system_prompt

        profile_tool = db.scalar(
            select(AgentProfileToolModel).where(
                AgentProfileToolModel.profile_id == profile.id,
                AgentProfileToolModel.tool_name == "npm",
            )
        )
        assert profile_tool is not None
        assert profile_tool.enabled is True
