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
    sqlite_path = _sqlite_path_from_url(settings.database_url)
    if sqlite_path and sqlite_path.parent != Path("."):
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_compatible_schema()
    from app.services.tool_config_service import seed_tool_configs

    seed_tool_configs()


def _ensure_compatible_schema() -> None:
    inspector = inspect(engine)
    if "agent_sessions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("agent_sessions")}
    if "user_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_sessions ADD COLUMN user_id INTEGER"))


def create_db_session() -> Session:
    return SessionLocal()
