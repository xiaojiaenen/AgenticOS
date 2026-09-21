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
    # checkfirst=True（默认）在 Index 已存在时仍可能报错（MySQL 方言 bug），
    # 用 try/ignore 兜底，让已有索引不阻塞启动。
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:  # noqa: BLE001
        if "Duplicate key name" in str(exc) or "already exists" in str(exc):
            logger.warning("create_all skipped existing index/table: %s", exc)
        else:
            raise
    _ensure_compatible_schema()
    from app.services.tool_config_service import seed_tool_configs
    from app.services.agent_profile_service import seed_agent_profiles
    from app.services.external_system_service import seed_preset_external_systems

    seed_tool_configs()
    seed_agent_profiles()
    seed_preset_external_systems()
    from app.services.local_skill_import_service import LocalSkillImportService
    LocalSkillImportService().import_from_storage()

    # 从环境变量种子化 ldap_enabled（仅首次启动时写入）
    _seed_ldap_enabled()


def _seed_ldap_enabled() -> None:
    """若 DB 中无 ldap_enabled 记录，从环境变量同步初始值。"""
    from sqlalchemy import select, text
    from app.db.models import SystemSettingModel
    inspector = inspect(engine)
    if "system_settings" not in inspector.get_table_names():
        return
    with SessionLocal() as session:
        row = session.scalar(
            select(SystemSettingModel).where(SystemSettingModel.key == "ldap_enabled")
        )
        if row is None:
            settings = get_settings()
            value = "true" if settings.ldap_enabled else "false"
            session.add(SystemSettingModel(key="ldap_enabled", value=value))
            session.commit()


def _ensure_compatible_schema() -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "agent_sessions" not in tables:
        return

    def _add_columns(table: str, columns: list[tuple[str, str]]) -> None:
        """Add missing columns to a table."""
        if table not in tables:
            return
        existing = {c["name"] for c in inspector.get_columns(table)}
        with engine.begin() as conn:
            for col_name, col_def in columns:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}"))

    # ── users ──
    _add_columns("users", [
        ("auth_source", "VARCHAR(32) DEFAULT 'local'"),
    ])

    # ── agent_sessions ──
    _add_columns("agent_sessions", [
        ("user_id", "INTEGER"),
        ("agent_profile_id", "INTEGER"),
        ("parallel_tool_calls", "BOOLEAN DEFAULT 0"),
        ("summary", "TEXT"),
        ("metadata_json", "TEXT DEFAULT '{}'"),
        ("last_usage_json", "TEXT DEFAULT '{}'"),
        ("last_latency_ms", "INTEGER DEFAULT 0"),
        ("last_llm_calls", "INTEGER DEFAULT 0"),
    ])

    # ── agent_usage_events ──
    _add_columns("agent_usage_events", [
        ("agent_profile_id", "INTEGER"),
        ("user_id", "INTEGER"),
        ("response_mode", "VARCHAR(32) DEFAULT 'general'"),
        ("tool_calls", "INTEGER DEFAULT 0"),
        ("tool_names_json", "TEXT DEFAULT '[]'"),
    ])

    # ── agent_tool_configs ──
    _add_columns("agent_tool_configs", [
        ("approval_sub_tools_json", "TEXT DEFAULT '[]'"),
    ])

    # ── agent_profile_tools ──
    _add_columns("agent_profile_tools", [
        ("approval_sub_tools_json", "TEXT DEFAULT '[]'"),
    ])

    # ── agent_profiles ──
    _add_columns("agent_profiles", [
        ("max_steps", "INTEGER"),
        ("response_mode", "VARCHAR(32) DEFAULT 'general'"),
        ("avatar", "VARCHAR(64)"),
        ("listed", "BOOLEAN DEFAULT 0"),
        ("is_builtin", "BOOLEAN DEFAULT 0"),
        ("created_by", "INTEGER"),
    ])

    # ── announcements ──
    _add_columns("announcements", [
        ("content_format", "VARCHAR(16) DEFAULT 'markdown'"),
        ("image_url", "TEXT"),
        ("eyebrow", "VARCHAR(80) DEFAULT '系统公告'"),
        ("subtitle", "TEXT DEFAULT ''"),
        ("theme", "VARCHAR(32) DEFAULT 'aurora'"),
        ("cta_label", "VARCHAR(64)"),
        ("cta_link", "VARCHAR(512)"),
        ("dismissible", "BOOLEAN DEFAULT 1"),
        ("show_once", "BOOLEAN DEFAULT 1"),
        ("starts_at", "DATETIME"),
        ("ends_at", "DATETIME"),
        ("created_by", "INTEGER"),
    ])

    # ── user_email_credentials ──
    _add_columns("user_email_credentials", [
        ("password_encrypted", "VARCHAR(1024)"),
    ])

    # ── auth_sessions ──
    _add_columns("auth_sessions", [
        ("revoked_at", "DATETIME"),
    ])

    # ── agent_approvals ──
    _add_columns("agent_approvals", [
        ("tool_call_id", "VARCHAR(128)"),
        ("metadata_json", "TEXT DEFAULT '{}'"),
    ])

    # ── memories（L1 扩展：分层蒸馏字段）──
    _add_columns("memories", [
        ("tags_json", "TEXT"),
        ("source", "VARCHAR(32) DEFAULT 'auto'"),
        ("layer", "VARCHAR(8) DEFAULT 'L1'"),
        ("scenario_id", "INTEGER"),
        ("embedding_model", "VARCHAR(64)"),
        ("embedding_updated_at", "DATETIME"),
        ("last_accessed_at", "DATETIME"),
        ("access_count", "INTEGER DEFAULT 0"),
        ("visibility", "VARCHAR(16) DEFAULT 'private'"),
    ])

    # ── skills（资产化扩展）──
    _add_columns("skills", [
        ("version", "INTEGER DEFAULT 1"),
        ("trigger_patterns_json", "TEXT"),
        ("validation_rules_json", "TEXT"),
        ("usage_count", "INTEGER DEFAULT 0"),
        ("last_used_at", "DATETIME"),
        ("visibility", "VARCHAR(16) DEFAULT 'private'"),
    ])

    # ── video_artifacts ──
    _add_columns("video_artifacts", [
        ("thumbnail_path", "TEXT"),
        ("template_id", "VARCHAR(64)"),
        ("has_soundtrack", "BOOLEAN DEFAULT 0"),
        ("file_size_bytes", "INTEGER DEFAULT 0"),
    ])

    # ── external_systems ──
    _add_columns("external_systems", [
        ("credential_template_json", "TEXT DEFAULT '{}'"),
        ("oauth_client_id_encrypted", "TEXT"),
        ("oauth_client_secret_encrypted", "TEXT"),
        ("oauth_auth_url", "TEXT"),
        ("oauth_token_url", "VARCHAR(512)"),
        ("oauth_scope", "TEXT"),
        ("oauth_refresh_token_url", "TEXT"),
        ("published", "BOOLEAN DEFAULT 1"),
        ("enabled", "BOOLEAN DEFAULT 1"),
        ("default_credential_data_encrypted", "TEXT"),
        ("headers_json", "TEXT DEFAULT '{}'"),
        ("jwt_login_url", "TEXT"),
        ("jwt_refresh_url", "TEXT"),
        ("jwt_refresh_body_template", "TEXT"),
        ("jwt_refresh_token_path", "TEXT"),
        ("advanced_auth_json", "TEXT DEFAULT '{}'"),
        ("jwt_request_body_template", "TEXT"),
        ("jwt_response_token_path", "TEXT"),
        ("jwt_response_expires_path", "TEXT"),
        ("jwt_response_token_header", "VARCHAR(128)"),
        ("login_token_source", "VARCHAR(16)"),
        ("login_inject_mode", "VARCHAR(16)"),
        ("login_inject_header_name", "VARCHAR(128)"),
        ("category", "VARCHAR(32) DEFAULT 'other'"),
    ])

    # ── external_user_credentials ──
    _add_columns("external_user_credentials", [
        ("cached_jwt_encrypted", "TEXT"),
        ("jwt_expires_at", "DATETIME"),
        ("oauth_access_token_encrypted", "TEXT"),
        ("oauth_refresh_token_encrypted", "TEXT"),
        ("oauth_expires_at", "DATETIME"),
        ("connection_status", "VARCHAR(32) DEFAULT 'connected'"),
        ("last_checked_at", "DATETIME"),
    ])

    # ── external_apis ──
    _add_columns("external_apis", [
        ("requires_approval", "BOOLEAN DEFAULT 0"),
        ("timeout_seconds", "INTEGER DEFAULT 30"),
        ("enabled", "BOOLEAN DEFAULT 1"),
        ("request_body_schema", "TEXT"),
        ("response_example", "TEXT"),
        ("body_wrapper_key", "VARCHAR(64)"),
    ])

    # ── external_api_params ──
    _add_columns("external_api_params", [
        ("param_source", "VARCHAR(16) DEFAULT 'static'"),
        ("label", "VARCHAR(64)"),
    ])

    # ── agent_messages: message_json 升级为 LONGTEXT（工具返回数据可能很大）──
    if "agent_messages" in tables:
        try:
            cols = {c["name"]: c for c in inspector.get_columns("agent_messages")}
            col = cols.get("message_json")
            if col and "TEXT" in str(col.get("type", "")).upper() and "LONG" not in str(col.get("type", "")).upper():
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE agent_messages MODIFY COLUMN message_json LONGTEXT"))
        except Exception:
            pass  # SQLite 不支持 ALTER COLUMN，忽略

    # ── ppt_artifacts: deck_json / preview_html 升级为 LONGTEXT（SVG deck 可能远超 TEXT 64KB 上限）──
    if "ppt_artifacts" in tables:
        for col_name in ("deck_json", "preview_html"):
            try:
                cols = {c["name"]: c for c in inspector.get_columns("ppt_artifacts")}
                col = cols.get(col_name)
                if col and "TEXT" in str(col.get("type", "")).upper() and "LONG" not in str(col.get("type", "")).upper():
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE ppt_artifacts MODIFY COLUMN {col_name} LONGTEXT"))
            except Exception:
                pass  # SQLite 不支持 ALTER COLUMN，忽略


def create_db_session() -> Session:
    return SessionLocal()
