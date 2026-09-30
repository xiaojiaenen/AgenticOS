from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import AgentProfileModel, AgentProfileToolModel, AgentToolConfigModel, Base
from app.prompts import WEBSITE_ROUTER_PROMPT
from app.services.agent_profile_service import AgentProfileService
from app.services.tool_config_service import DEFAULT_MODE_TOOLS, ToolConfigService


def test_website_prompt_contains_directory_and_build_rules() -> None:
    # 路由提示已改为通过 build_website/check_website_project 工具编排，不再硬编码 npm 命令
    assert "data/websites/" in WEBSITE_ROUTER_PROMPT or "check_website_project" in WEBSITE_ROUTER_PROMPT
    assert "build_website" in WEBSITE_ROUTER_PROMPT or "npm" in WEBSITE_ROUTER_PROMPT


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

    # ensure_defaults 有 5 分钟进程级缓存，测试前强制失效，确保对本临时库执行升级
    import app.services.agent_profile_service as profile_svc
    profile_svc._ensure_defaults_last_run = 0.0
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
        # 升级后应写入当前 WEBSITE_ROUTER_PROMPT（以工具编排为核心，不再硬编码绝对路径片段）
        assert "copy_template" in profile.system_prompt or "check_website_project" in profile.system_prompt
        assert "build_website" in profile.system_prompt

        profile_tool = db.scalar(
            select(AgentProfileToolModel).where(
                AgentProfileToolModel.profile_id == profile.id,
                AgentProfileToolModel.tool_name == "npm",
            )
        )
        assert profile_tool is not None
        assert profile_tool.enabled is True
