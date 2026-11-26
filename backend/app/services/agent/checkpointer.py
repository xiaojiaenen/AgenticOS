"""LangGraph checkpointer 单例（DeepAgents 官方持久化方式）。

阶段 2A：图接 AsyncSqliteSaver（本地）/ 生产可切 AsyncPostgresSaver，
config 传 thread_id=session_id。此时仍每轮传全量历史（自研 session 是产品历史源），
checkpointer 只承担图级状态持久化：HITL 暂停恢复、time-travel、崩溃恢复。
阶段 2B 才会把历史改为增量、由 checkpointer 重放。

注意：AsyncSqliteSaver 构造时必须处于事件循环中（内部 get_running_loop()），
所以延迟到首次 async 调用时构造；每 event loop 一个实例（LangGraph 的
checkpointer 绑定 loop，跨 loop 复用会报错）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.data_path import DATA_DIR

_logger = logging.getLogger(__name__)

# key = loop 对象，value = checkpointer（每个事件循环独立）
_instances: dict[Any, Any] = {}


async def get_async_checkpointer() -> Any | None:
    """在当前事件循环里取/建 checkpointer；配置关闭或依赖缺失返回 None。"""
    import asyncio

    settings = get_settings()
    if not getattr(settings, "langgraph_checkpointer_enabled", True):
        return None
    loop = asyncio.get_running_loop()
    if loop in _instances:
        return _instances[loop]
    try:
        # 测试环境（pytest 每个用例新建 event loop）用 InMemorySaver：
        # AsyncSqliteSaver 的 aiosqlite 连接绑定 loop 且持有 db 锁，跨多个
        # asyncio.run 会死锁；测试本来也不需要跨进程持久化。
        env = (getattr(settings, "environment", "") or "").lower()
        if env == "test":
            from langgraph.checkpoint.memory import InMemorySaver

            cp = InMemorySaver()
            _instances[loop] = cp
            return cp

        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        import aiosqlite

        db_path = (getattr(settings, "langgraph_checkpoint_db", "") or "").strip()
        path = Path(db_path) if db_path else DATA_DIR / "checkpoints.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(path), check_same_thread=False)
        cp = AsyncSqliteSaver(conn)
        await cp.setup()  # 建 checkpoint 表（幂等）
        _instances[loop] = cp
        _logger.info("LangGraph checkpointer 已启用（AsyncSqliteSaver）: %s", path)
        return cp
    except Exception as exc:  # noqa: BLE001 - checkpointer 是增强，失败不阻断 agent
        _logger.warning("LangGraph checkpointer 初始化失败，降级为无 checkpointer: %s", exc)
        _instances[loop] = None
        return None
