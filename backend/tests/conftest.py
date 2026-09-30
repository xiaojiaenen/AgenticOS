"""Pytest 全局夹具。

关键约束：**本文件顶层的环境变量注入必须早于任何 ``app.*`` 的 import**。
``app.db.session`` 在模块导入期就会创建 engine 与会话工厂，``get_settings``
是 ``lru_cache``；一旦它们在真实 ``DATABASE_URL`` 下被初始化，测试就会直连
生产库 ``data/agenticos.db`` 并污染其中的数据。

pytest 会先导入 conftest.py、再收集测试模块，因此这里的顶层代码是唯一的
安全注入点 —— session 级 fixture 太晚，autouse fixture 也已来不及重建
��经 import 的 engine。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# 1. 在任何 app.* import 之前重定向到一次性测试环境
# ---------------------------------------------------------------------------

# resolve()：Windows 的 TEMP 可能是 8.3 短路径（ADMINI~1），而 app.core.data_path
# 会 resolve 成长路径，两边必须一致否则隔离守卫断言会误报。
_TMP_ROOT = Path(tempfile.gettempdir()).resolve() / "agenticos_pytest"
if _TMP_ROOT.exists():
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)
_TMP_ROOT.mkdir(parents=True, exist_ok=True)

_TEST_DB = _TMP_ROOT / "test.db"
_TEST_DATA_DIR = _TMP_ROOT / "data"

# pydantic-settings 优先级为 os.environ > .env 文件，故此处可覆盖 backend/.env
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ["SKILL_STORAGE_DIR"] = str(_TEST_DATA_DIR / "skills")
os.environ["AGENT_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["APP_ENV"] = "test"
os.environ["ENVIRONMENT"] = "test"
# 固定测试密钥：避免读写 data/.auth_secret，也不依赖开发机上的 .env
os.environ["AUTH_SECRET_KEY"] = "test-only-secret-key-not-valid-in-production"
# 外部集成在测试中不应发起真实网络请求
os.environ.setdefault("UPSTREAM_AUTO_LOGIN_ENABLED", "false")

import pytest  # noqa: E402  —— 必须晚于上面的 os.environ 注入


# ---------------------------------------------------------------------------
# 2. 通用夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def _init_test_db():
    """会话级建表：很多测试文件在模块级直接 TestClient(app)（不进 with），
    lifespan 不会执行，init_db 从未跑过，导致 "no such table" 失败。
    这里统一建表 + 跑种子，与 lifespan 行为对齐。"""
    from app.db.session import init_db

    init_db()


@pytest.fixture(scope="session", autouse=True)
def _isolated_test_env():
    """会话级守卫：确保 engine 建在临时库上，并禁止测试触碰真实数据目录。

    这里的断言是最后一道防线 —— 若后续重构导致上面的环境变量注入失效，
    会立刻得到一个可读的失败，而不是静默污染生产库。
    """
    from app.core.config import get_settings
    from app.core.data_path import DATA_DIR
    from app.db.session import engine

    settings = get_settings()
    url = settings.database_url

    # Windows 下 str(Path) 是反斜杠，而 DATABASE_URL 以 as_posix() 注入，需归一化后比较
    assert _TEST_DB.as_posix() in url.replace("\\", "/"), (
        f"测试未隔离数据库：DATABASE_URL={url!r}，期望包含 {_TEST_DB!r}。"
        "请检查 tests/conftest.py 顶层的环境变量注入是否被绕过。"
    )
    assert url.startswith("sqlite"), f"测试库必须是 SQLite，实际为 {url!r}"
    assert str(_TEST_DATA_DIR) in str(DATA_DIR), (
        f"测试未隔离数据目录：DATA_DIR={DATA_DIR}，期望包含 {_TEST_DATA_DIR}。"
    )

    yield

    engine.dispose()
    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


# ---------------------------------------------------------------------------
# 3. 测试数据清理工具
# ---------------------------------------------------------------------------

# 这些表均以 user_id 关联，统一在删除 User 之前清理
_USER_SCOPED_TABLES = (
    "user_installed_agents",
    "agent_usage_events",
    "memories",
    "memory_conversations",
    "auth_sessions",
    "agent_sessions",
    "user_email_credentials",
    "upstream_credentials",
    "upstream_api_keys",
)


def safe_delete_users(*emails: str) -> None:
    """按外键安全顺序删除测试用户及其从属行。

    与历史实现的差异：不再吞掉异常。原先的 ``except Exception: pass`` 会把
    "表结构不匹配" 这类真实问题一并隐藏，排查时只能看到"清理似乎没生效"。
    """
    from sqlalchemy import bindparam, delete, select, text, update

    from app.db.models import AgentProfileModel, AuthSessionModel, SkillModel, UserModel
    from app.db.session import create_db_session

    if not emails:
        return

    with create_db_session() as db:
        ids = list(db.scalars(select(UserModel.id).where(UserModel.email.in_(emails))).all())
        if not ids:
            return

        db.execute(
            update(AgentProfileModel)
            .where(AgentProfileModel.created_by.in_(ids))
            .values(created_by=None)
        )
        db.execute(
            update(SkillModel).where(SkillModel.created_by.in_(ids)).values(created_by=None)
        )

        for table in _USER_SCOPED_TABLES:
            db.execute(
                text(f"DELETE FROM {table} WHERE user_id IN :uids").bindparams(
                    bindparam("uids", expanding=True)
                ),
                {"uids": ids},
            )

        # 限流表无 user_id 归属，测试直接整表清空
        db.execute(text("DELETE FROM auth_rate_limits"))

        db.execute(delete(AuthSessionModel).where(AuthSessionModel.user_id.in_(ids)))
        db.execute(delete(UserModel).where(UserModel.id.in_(ids)))
        db.commit()


@pytest.fixture(autouse=True)
def _reset_global_singletons():
    """每个用例前后重置跨用例污染的模块级状态。

    ``get_settings`` 与 ``AgentService``（内含 Agent + ToolRegistry 的 TTLCache）
    都是进程级单例；不清理会导致用例间的配置与 Agent 缓存互相渗透。
    """
    yield

    try:
        from app.services.agent_service import clear_agent_service_cache

        clear_agent_service_cache()
    except Exception:  # noqa: BLE001,S110 —— 清理属尽力而为，不应让用例失败

        pass

    try:
        from app.core.config import get_settings

        get_settings.cache_clear()
    except Exception:  # noqa: BLE001,S110

        pass
