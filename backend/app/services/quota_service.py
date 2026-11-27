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

from app.core.roles import is_admin_like
from app.core.timezone import app_now
from app.db.models import AgentUsageEventModel, SystemSettingModel
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


QUOTA_KEY = "quota.daily_token_quota"
IMAGE_QUOTA_KEY = "quota.daily_image_quota"  # 每日 AI 生图张数（0 = 关闭）

# 发布作品奖励额度（token）：按产物类型。发布时一次性加到当日可用额度。
PUBLISH_REWARD_TOKENS: dict[str, int] = {
    "ppt": 20_000,
    "website": 20_000,
    "document": 10_000,   # word/文档
    "sheet": 10_000,
    "image": 5_000,
}


def _user_quota_key(user_id: int, kind: str) -> str:
    """用户个人额度覆盖键（未设置时走全局默认）。"""
    return f"quota.user.{user_id}.{kind}"


def _bonus_key(user_id: int, day: str) -> str:
    """用户某日通过发布作品获得的奖励 token 累计键。"""
    return f"quota.bonus.{user_id}.{day}"


def get_eff_quota(db: Any, user_id: int, kind: str) -> int:
    """有效额度：用户个人覆盖优先，其次全局默认，均 0 表示不限。

    kind: 'token' | 'image'
    """
    global_key = QUOTA_KEY if kind == "token" else IMAGE_QUOTA_KEY
    for key in (_user_quota_key(user_id, kind), global_key):
        row = db.get(SystemSettingModel, key)
        if row is not None and row.value.strip():
            try:
                return max(0, int(row.value))
            except ValueError:
                logger.warning("quota 键 %s 非法值 %r，跳过", key, row.value)
    return 0


def image_generations_today(user_id: int) -> int:
    """该用户今日 AI 生图张数（从画布产物文件计数不现实，改查审计表）。

    复用 agent_usage_events 的 tool_names_json 记录 'generate_image' 次数；
    画布生图由 canvas 端点单独记 usage（见 canvas.py）。
    """
    today = app_now().date()
    with create_db_session() as db:
        rows = db.execute(
            select(AgentUsageEventModel.tool_names_json).where(
                AgentUsageEventModel.user_id == user_id,
                func.date(AgentUsageEventModel.created_at) == today,
            )
        ).scalars()
        count = 0
        for raw in rows:
            if not raw:
                continue
            try:
                import json
                names = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(names, list) and any(
                    "image" in str(n).lower() for n in names
                ):
                    count += 1
            except (ValueError, TypeError):
                continue
    return count


def check_image_quota(user_id: int, *, role: str) -> dict[str, Any]:
    """画布生图额度检查：超限抛 DailyQuotaExceeded（复用异常类）。"""
    with create_db_session() as db:
        quota = get_eff_quota(db, user_id, "image")
    if quota <= 0 or is_admin_like(role):
        return {"quota": quota, "used": None}
    used = image_generations_today(user_id)
    if used >= quota:
        raise DailyQuotaExceeded(used, quota)
    return {"quota": quota, "used": used}


def grant_publish_reward(user_id: int, artifact_kind: str) -> int:
    """发布作品奖励 token 额度：记入当日 bonus 键，返回奖励值。

    由作品发布端点调用；同一用户同类作品多次发布也累计（鼓励创作）。
    """
    reward = int(PUBLISH_REWARD_TOKENS.get(artifact_kind, 0))
    if reward <= 0:
        return 0
    day = app_now().date().isoformat()
    with create_db_session() as db:
        key = _bonus_key(user_id, day)
        row = db.get(SystemSettingModel, key)
        current = int(row.value) if row and row.value.strip() and row.value.isdigit() else 0
        if row is None:
            db.add(SystemSettingModel(key=key, value=str(current + reward)))
        else:
            row.value = str(current + reward)
            row.updated_at = app_now()
        db.commit()
    return reward


def get_user_quota_status(user_id: int, *, role: str) -> dict[str, Any]:
    """用户侧额度总览：token/image 的 额度/已用/剩余（管理员不限显示 -1）。"""
    with create_db_session() as db:
        token_quota = get_eff_quota(db, user_id, "token")
        image_quota = get_eff_quota(db, user_id, "image")
        day = app_now().date().isoformat()
        bonus_row = db.get(SystemSettingModel, _bonus_key(user_id, day))
        bonus = int(bonus_row.value) if bonus_row and bonus_row.value.strip() and bonus_row.value.isdigit() else 0
    admin = is_admin_like(role)
    token_used = used_tokens_today(user_id)
    image_used = image_generations_today(user_id)
    return {
        "token": {
            "quota": -1 if admin else token_quota,
            "used": token_used,
            "bonus_today": bonus if not admin else 0,
            "remaining": -1 if admin or token_quota <= 0 else max(0, token_quota + bonus - token_used),
        },
        "image": {
            "quota": -1 if admin else image_quota,
            "used": image_used,
            "remaining": -1 if admin or image_quota <= 0 else max(0, image_quota - image_used),
        },
        "rewards": PUBLISH_REWARD_TOKENS,
    }


def get_daily_quota_config(db: Any) -> dict[str, Any]:
    """当前配额配置：system_settings 的 DB 配置优先（后台可调，战线 E-P1），
    回退环境变量默认。端点层（admin_ops）复用本函数，避免服务层反向依赖路由层。
    """
    row = db.get(SystemSettingModel, QUOTA_KEY)
    if row is not None and row.value.strip():
        try:
            return {"source": "database", "daily_token_quota": int(row.value), "updated_at": row.updated_at}
        except ValueError:
            logger.warning("system_settings 配额键非法值 %r，回退环境变量", row.value)
    from app.core.config import get_settings

    return {"source": "env", "daily_token_quota": get_settings().user_daily_token_quota, "updated_at": None}


def check_daily_quota(user_id: int, *, role: str = "user") -> dict[str, Any]:
    """入口配额检查。返回当前用量信息；超限抛 DailyQuotaExceeded。

    管理员与未启用配额（quota=0）时直接放行。
    配额值：system_settings 的 DB 配置优先（后台可调），回退环境变量。
    """
    from app.core.config import get_settings

    quota = get_settings().user_daily_token_quota
    try:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            quota = int(get_daily_quota_config(db)["daily_token_quota"])
    except Exception:  # noqa: BLE001 —— 配置读取失败回退环境变量
        logger.warning("配额 DB 配置读取失败，回退环境变量", exc_info=True)
    # 管理员豁免统一走 is_admin_like（admin + superadmin，3H 档 A）
    if quota <= 0 or is_admin_like(role):
        return {"quota": quota, "used": None}

    used = used_tokens_today(user_id)
    if used >= quota:
        logger.warning("daily quota exceeded: user=%s used=%d quota=%d", user_id, used, quota)
        raise DailyQuotaExceeded(used, quota)
    return {"quota": quota, "used": used}
