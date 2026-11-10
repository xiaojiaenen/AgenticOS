"""把 cron 定义写入 taskiq 的 schedule source（幂等）。

arq 的 cron 是代码里的 ``cron_jobs`` 列表，worker 启动自动生效。
taskiq 的定时任务存在 schedule source（Redis）里，需要一个种子步骤。

用法：
    python -m app.services.task_queue_seed

在部署脚本里跑一次即可（重复跑安全 —— 按 schedule_id upsert）。
scheduler 容器（``taskiq scheduler``）会周期性从 source 读 cron 并投递。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def seed() -> int:
    """写入/更新所有 cron 定义，返回处理条数。"""
    from taskiq.scheduler.scheduled_task import ScheduledTask

    from app.services.task_queue import CRON_SCHEDULES, build_schedule_source

    source = build_schedule_source()
    written = 0
    for task_name, cron_expr in CRON_SCHEDULES:
        task = ScheduledTask(
            task_name=task_name,
            labels={},
            args=[],
            kwargs={},
            schedule_id=f"agenticos:{task_name}",
            cron=cron_expr,
        )
        try:
            await source.add_schedule(task)
            written += 1
            logger.info("已写入定时任务 %s (%s)", task_name, cron_expr)
        except Exception:  # noqa: BLE001
            logger.exception("写入定时任务失败: %s", task_name)
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    n = asyncio.run(seed())
    print(f"完成：{n}/{len(__import__('app.services.task_queue', fromlist=['CRON_SCHEDULES']).CRON_SCHEDULES)} 个定时任务已写入")


if __name__ == "__main__":
    main()
