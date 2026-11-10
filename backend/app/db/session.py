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
        # M6-A1 连接池分级：常驻 10 + 溢出 20 = 单实例最多 30 条连接；
        # pool_recycle 1800s 短于 MySQL wait_timeout 默认值，避免拿到已被
        # 服务端断开的陈旧连接（仍由 pool_pre_ping 兜底双保险）。
        engine_kwargs["pool_recycle"] = settings.db_pool_recycle
        engine_kwargs["pool_size"] = settings.db_pool_size
        engine_kwargs["max_overflow"] = settings.db_max_overflow

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
    # create_all 只建缺失的表，**不会给已存在的表加列**；因此启动时必须把
    # 待应用的迁移跑掉，否则「代码加了字段、库没加列」→ 查询直接 500
    # （内网 website gallery 的 visibility/access_token 缺失就是这么来的）。
    _apply_pending_migrations()

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


def _apply_pending_migrations() -> None:
    """启动时应用 alembic 迁移，消除「代码加了字段、库没跑迁移」的漂移。

    - 库里还没有 ``alembic_version``（全新库，create_all 已建全量 schema）
      → ``stamp head`` 做基线对齐；
    - 已有版本表 → ``upgrade head``，把缺失的列/索引补上。

    失败只记错误日志、不阻断启动：迁移是运维动作，晚一步补也比整个服务起不来强。
    """
    try:
        from alembic import command
        from alembic.config import Config

        backend_root = Path(__file__).resolve().parents[2]
        cfg = Config()
        cfg.set_main_option("script_location", str(backend_root / "alembic"))
        # 不读 alembic.ini：env.py 在 sqlalchemy.url 为空时会复用应用 engine
        # （同一 DATABASE_URL），避免两套连接配置漂移。
        has_version = "alembic_version" in inspect(engine).get_table_names()
        if has_version:
            command.upgrade(cfg, "head")
            logger.info("alembic: upgrade head applied")
        else:
            command.stamp(cfg, "head")
            logger.info("alembic: stamped head on fresh database")
    except Exception:  # noqa: BLE001 -- 迁移失败不阻断启动
        logger.error(
            "启动自动迁移失败，库结构可能与代码不一致；"
            "请手动执行 `python -m alembic upgrade head`",
            exc_info=True,
        )


def _seed_ldap_enabled() -> None:
    """LDAP 开关的引导种子化。

    新配置以 ``ldap.enabled`` 键为准（管理后台维护完整配置）；
    历史库里的旧键 ``ldap_enabled`` 会被迁移到新键，避免升级后开关丢失。
    """
    from sqlalchemy import select
    from app.db.models import SystemSettingModel
    inspector = inspect(engine)
    if "system_settings" not in inspector.get_table_names():
        return
    with SessionLocal() as session:
        new_row = session.scalar(
            select(SystemSettingModel).where(SystemSettingModel.key == "ldap.enabled")
        )
        if new_row is not None:
            return
        old_row = session.scalar(
            select(SystemSettingModel).where(SystemSettingModel.key == "ldap_enabled")
        )
        if old_row is not None:
            # 迁移旧键 → 新键（保留旧键无害，读取侧只认新键）
            session.add(SystemSettingModel(key="ldap.enabled", value=old_row.value))
            session.commit()
            return
        settings = get_settings()
        value = "true" if settings.ldap_enabled else "false"
        session.add(SystemSettingModel(key="ldap.enabled", value=value))
        session.commit()


def create_db_session() -> Session:
    return SessionLocal()
