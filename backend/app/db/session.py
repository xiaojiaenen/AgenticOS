import logging
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base

logger = logging.getLogger(__name__)


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
    # Schema 演进自 TECH-DEBT-2026-09 起由 alembic 负责（backend/alembic/）：
    # - 存量库：`alembic stamp head` 完成基线对齐（历史补列由旧版
    #   _ensure_compatible_schema 完成，该函数已删除）。
    # - 新库（开发 SQLite）：create_all 建全量 schema 后同样 `alembic stamp head`。
    # - 生产 MySQL：启动一次让 create_all 建表后执行 `alembic upgrade head`
    #   （0002 迁移会把 message_json/deck_json/preview_html 拉长为 LONGTEXT）。
    #   详见 backend/alembic/README.md。
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
    from sqlalchemy import select
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


def create_db_session() -> Session:
    return SessionLocal()
