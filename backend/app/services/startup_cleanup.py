"""进程重启时的后台任务收尸（ASCII stdout safe, utf-8 file）。"""
from __future__ import annotations

import logging

from sqlalchemy import update

from app.core.timezone import app_now
from app.db.models import AgentRunTraceModel, EvalRunModel

_logger = logging.getLogger("startup_cleanup")


def mark_interrupted_runs() -> dict[str, int]:
    """把上次进程中断时还在 running 的后台任务标记为 error。

    评测在 asyncio.create_task 里跑、追踪在 run 的 finally 里落库 ——
    进程被杀（发版/OOM/崩溃）时两者都会永远卡在 running，页面上
    「执行中」没有终态。启动时统一收尸。
    """
    from app.db.session import create_db_session

    now = app_now()
    with create_db_session() as db:
        eval_result = db.execute(
            update(EvalRunModel)
            .where(EvalRunModel.status == "running")
            .values(status="error", error="interrupted by process restart", finished_at=now)
        )
        trace_result = db.execute(
            update(AgentRunTraceModel)
            .where(AgentRunTraceModel.status == "running")
            .values(status="error", error="interrupted by process restart", finished_at=now)
        )
        db.commit()
        counts = {"eval_runs": eval_result.rowcount or 0, "traces": trace_result.rowcount or 0}
    if counts["eval_runs"] or counts["traces"]:
        _logger.warning("marked interrupted runs: %s", counts)
    return counts
