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

    if "agent_profiles" in inspector.get_table_names():
        ap_columns = {column["name"] for column in inspector.get_columns("agent_profiles")}
        if "max_steps" not in ap_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE agent_profiles ADD COLUMN max_steps INTEGER"))

    if "announcements" in inspector.get_table_names():
        announcement_columns = {column["name"] for column in inspector.get_columns("announcements")}
        if "content_format" not in announcement_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE announcements ADD COLUMN content_format VARCHAR(16) DEFAULT 'markdown'"))
        if "image_url" not in announcement_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE announcements ADD COLUMN image_url TEXT"))

    if "external_systems" in inspector.get_table_names():
        es_columns = {column["name"] for column in inspector.get_columns("external_systems")}
        for col_name, col_def in [
            ("credential_template_json", "TEXT DEFAULT '{}'"),
            ("oauth_client_id_encrypted", "TEXT"),
            ("oauth_client_secret_encrypted", "TEXT"),
            ("oauth_auth_url", "TEXT"),
            ("oauth_scope", "TEXT"),
            ("oauth_refresh_token_url", "TEXT"),
            ("published", "BOOLEAN DEFAULT 1"),
            ("jwt_login_url", "TEXT"),
            ("jwt_refresh_url", "TEXT"),
            ("jwt_refresh_body_template", "TEXT"),
            ("jwt_refresh_token_path", "TEXT"),
            ("advanced_auth_json", "TEXT DEFAULT '{}'"),
            ("jwt_request_body_template", "TEXT"),
            ("jwt_response_token_path", "TEXT"),
            ("jwt_response_expires_path", "TEXT"),
        ]:
            if col_name not in es_columns:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE external_systems ADD COLUMN {col_name} {col_def}"))

    if "external_user_credentials" in inspector.get_table_names():
        uc_columns = {column["name"] for column in inspector.get_columns("external_user_credentials")}
        for col_name, col_def in [
            ("cached_jwt_encrypted", "TEXT"),
            ("jwt_expires_at", "DATETIME"),
        ]:
            if col_name not in uc_columns:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE external_user_credentials ADD COLUMN {col_name} {col_def}"))


def create_db_session() -> Session:
    return SessionLocal()
