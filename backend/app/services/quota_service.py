"""用量配额：按用户每日 Token 上限（默认关闭）。

背景：上游 Trae CN 配额被烧光的事件 —— usage_events 已完整记录每次
调用的 token，但没有任何限制，单个用户可以无声耗尽全站配额。

设计取舍：
- **日配额**（而非月/总）：好理解、好重置，天然防止单用户长期独占。
- **管理员不受限**：管理员做的是运维与验证，限额会挡住自己的工作。
- **默认 0 = 关闭**：不改变现有部署行为；启用只需一个环境变量。
- **检查点在请求入口**：拒绝发生在 LLM 调用之前，超限请求零上游成本。
- 错误信息带「已用/上限」—— 用户需要知道是配额问题而非故障。
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select

from app.core.timezone import app_now
from app.db.models import AgentUsageEventModel
from app.db.session import create_db_session

logger = logging.getLogger("agenticos.quota")


class DailyQuotaExceeded(PermissionError):
    """用户当日 Token 配额已用尽。"""

    def __init__(self, used: int, quota: int) -> None:
        self.used = used
        self.quota = quota
        super().__init__(
            f"今日 Token 配额已用尽（{used:,}/{quota:,}）。"
            "配额每日重置；如需调整请联系管理员。"
        )


def used_tokens_today(user_id: int) -> int:
    """该用户今日（平台时区）消耗的 token 总量。"""
    today = app_now().date()
    with create_db_session() as db:
        total = db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(AgentUsageEventModel.input_tokens, 0)
                        + func.coalesce(AgentUsageEventModel.output_tokens, 0)
                    ),
                    0,
                )
            ).where(
                AgentUsageEventModel.user_id == user_id,
                func.date(AgentUsageEventModel.created_at) == today,
            )
        )
    return int(total or 0)


def check_daily_quota(user_id: int, *, role: str = "user") -> dict[str, Any]:
    """入口配额检查。返回当前用量信息；超限抛 DailyQuotaExceeded。

    管理员与未启用配额（quota=0）时直接放行。
    """
    from app.core.config import get_settings

    quota = get_settings().user_daily_token_quota
    if quota <= 0 or role == "admin":
        return {"quota": quota, "used": None}

    used = used_tokens_today(user_id)
    if used >= quota:
        logger.warning("daily quota exceeded: user=%s used=%d quota=%d", user_id, used, quota)
        raise DailyQuotaExceeded(used, quota)
    return {"quota": quota, "used": used}
