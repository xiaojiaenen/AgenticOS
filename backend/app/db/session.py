from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base


def _sqlite_path_from_url(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///"):
        return None
    raw_path = database_url.removeprefix("sqlite:///")
    if raw_path in {":memory:", ""}:
        return None
    return Path(raw_path)


def _create_engine() -> Engine:
    settings = get_settings()
    database_url = settings.database_url

    sqlite_path = _sqlite_path_from_url(database_url)
    if sqlite_path and sqlite_path.parent != Path("."):
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    is_sqlite = database_url.startswith("sqlite")
    # SQLite: 增加超时到 30 秒，启用 WAL 模式提升并发性能
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}

    engine_kwargs: dict = {
        "pool_pre_ping": True,
    }
    if not is_sqlite:
        engine_kwargs["pool_recycle"] = 3600
        engine_kwargs["pool_size"] = 5
        engine_kwargs["max_overflow"] = 10

    engine = create_engine(database_url, connect_args=connect_args, **engine_kwargs)

    # SQLite 启用 WAL 模式，减少锁冲突
    if is_sqlite:
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    return engine


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    get_settings().get_skill_storage_dir().mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_schema()
    from app.services.tool_config_service import seed_tool_configs
    from app.services.agent_profile_service import seed_agent_profiles

    seed_tool_configs()
    seed_agent_profiles()
    from app.services.local_skill_import_service import LocalSkillImportService
    LocalSkillImportService().import_from_storage()


def _ensure_compatible_schema() -> None:
    inspector = inspect(engine)
    if "agent_sessions" not in inspector.get_table_names():
        return

    session_columns = {column["name"] for column in inspector.get_columns("agent_sessions")}
    if "user_id" not in session_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_sessions ADD COLUMN user_id INTEGER"))
    if "agent_profile_id" not in session_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_sessions ADD COLUMN agent_profile_id INTEGER"))

    if "agent_usage_events" in inspector.get_table_names():
        usage_columns = {column["name"] for column in inspector.get_columns("agent_usage_events")}
        if "agent_profile_id" not in usage_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agent_usage_events ADD COLUMN agent_profile_id INTEGER"))
        if "user_id" not in usage_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agent_usage_events ADD COLUMN user_id INTEGER"))

    if "agent_tool_configs" in inspector.get_table_names():
        tc_columns = {column["name"] for column in inspector.get_columns("agent_tool_configs")}
        if "approval_sub_tools_json" not in tc_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agent_tool_configs ADD COLUMN approval_sub_tools_json TEXT DEFAULT '[]'"))

    if "agent_profile_tools" in inspector.get_table_names():
        pt_columns = {column["name"] for column in inspector.get_columns("agent_profile_tools")}
        if "approval_sub_tools_json" not in pt_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agent_profile_tools ADD COLUMN approval_sub_tools_json TEXT DEFAULT '[]'"))

    if "announcements" in inspector.get_table_names():
        announcement_columns = {column["name"] for column in inspector.get_columns("announcements")}
        if "content_format" not in announcement_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE announcements ADD COLUMN content_format VARCHAR(16) DEFAULT 'markdown'"))
        if "image_url" not in announcement_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE announcements ADD COLUMN image_url TEXT"))


def create_db_session() -> Session:
    return SessionLocal()
