"""任务完成通知服务 — 长任务完成后通过系统邮箱通知用户"""

import asyncio
import logging

from sqlalchemy import select

from app.db.models import UserModel
from app.db.session import create_db_session
from app.tools.email_tools import send_notification_email

logger = logging.getLogger(__name__)


def _format_duration(seconds: float) -> str:
    """将秒数格式化为人类可读的时长"""
    if seconds < 60:
        return f"{int(seconds)} 秒"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes} 分 {secs} 秒" if secs else f"{minutes} 分钟"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} 小时 {mins} 分钟" if mins else f"{hours} 小时"


def _send_email_sync(creds: dict, to: str, subject: str, html_body: str) -> bool:
    """同步发送邮件（在线程池中执行）"""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            send_notification_email(creds, to, subject, html_body, is_html=True)
        )
    finally:
        loop.close()


async def send_task_complete_notification(
    user_id: int,
    session_id: str,
    task_summary: str,
    duration_seconds: float,
    frontend_base_url: str = "",
    is_error: bool = False,
) -> None:
    """
    发送任务完成/失败通知邮件

    使用系统邮箱（.env 中配置的 NOTIFY_* 变量）发送通知到用户注册邮箱。
    在 agent_service produce_events 的 finally 块中通过 asyncio.create_task 调用。
    失败只记录日志，不影响主流程。
    """
    from app.core.config import get_settings
    settings = get_settings()

    # 1. 检查系统邮箱是否配置
    if not settings.notify_email_address or not settings.notify_smtp_host:
        return

    # 2. 检查是否达到阈值（失败任务不受阈值限制，总是通知）
    min_seconds = settings.notify_task_min_seconds
    if not is_error and duration_seconds < min_seconds:
        return

    db = create_db_session()
    try:
        # 3. 获取用户注册邮箱
        user = db.scalar(select(UserModel).where(UserModel.id == user_id))
        if not user or not user.email:
            return

        creds = {
            "email": settings.notify_email_address,
            "password": settings.notify_email_password,
            "smtp_host": settings.notify_smtp_host,
            "smtp_port": settings.notify_smtp_port,
            "smtp_ssl": settings.notify_smtp_ssl,
        }

        duration_str = _format_duration(duration_seconds)
        from app.services import email_templates

        html_body = email_templates.build_task_notification(
            task_summary, duration_str, session_id, frontend_base_url, is_error=is_error
        )

        if is_error:
            subject = f"❌ 任务失败 · {duration_str} — AgenticOS"
        else:
            subject = f"✅ 任务已完成 · {duration_str} — AgenticOS"

        # 4. 在线程池中执行同步 SMTP 操作，避免阻塞事件循环
        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(
            None,
            _send_email_sync,
            creds,
            user.email,
            subject,
            html_body,
        )

        if success:
            logger.info(f"Task notification sent to user {user_id} ({user.email}), is_error={is_error}")
        else:
            logger.warning(f"Failed to send task notification to user {user_id}")

    except Exception as e:
        logger.error(f"Error in send_task_complete_notification: {e}", exc_info=True)
    finally:
        db.close()


async def send_welcome_email(
    user_email: str,
    user_name: str,
    frontend_base_url: str = "",
) -> None:
    """
    发送欢迎邮件

    在用户注册成功或管理员创建用户后调用。
    """
    from app.core.config import get_settings
    settings = get_settings()

    # 检查系统邮箱是否配置
    if not settings.notify_email_address or not settings.notify_smtp_host:
        return

    try:
        creds = {
            "email": settings.notify_email_address,
            "password": settings.notify_email_password,
            "smtp_host": settings.notify_smtp_host,
            "smtp_port": settings.notify_smtp_port,
            "smtp_ssl": settings.notify_smtp_ssl,
        }

        from app.services import email_templates

        html_body = email_templates.build_welcome(user_name, frontend_base_url)
        subject = "🎉 欢迎加入 AgenticOS"

        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(
            None,
            _send_welcome_email_sync,
            creds,
            user_email,
            subject,
            html_body,
        )

        if success:
            logger.info(f"Welcome email sent to {user_email}")
        else:
            logger.warning(f"Failed to send welcome email to {user_email}")

    except Exception as e:
        logger.error(f"Error sending welcome email: {e}", exc_info=True)


def _send_welcome_email_sync(creds: dict, to: str, subject: str, html_body: str) -> bool:
    """同步发送欢迎邮件"""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            send_notification_email(creds, to, subject, html_body, is_html=True)
        )
    finally:
        loop.close()


def _notify_creds() -> dict | None:
    """系统通知邮箱凭据；未配置返回 None。"""
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.notify_email_address or not settings.notify_smtp_host:
        return None
    return {
        "email": settings.notify_email_address,
        "password": settings.notify_email_password,
        "smtp_host": settings.notify_smtp_host,
        "smtp_port": settings.notify_smtp_port,
        "smtp_ssl": settings.notify_smtp_ssl,
    }


def _frontend_base() -> str:
    from app.core.config import get_settings
    origins = get_settings().get_cors_allow_origins()
    return origins[0] if origins else ""


async def send_wrapped_email(user: UserModel, stats: dict, frontend_base: str = "") -> bool:
    """给单个用户发送年度报告邮件。失败只记日志，返回是否成功。"""
    creds = _notify_creds()
    if not creds or not user.email:
        return False
    from app.services import email_templates

    html_body = email_templates.build_wrapped(stats, frontend_base)
    subject = f"🎁 {user.name}，你的 {stats.get('year')} 年度 AI 报告 — AgenticOS"
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(
            None, _send_email_sync, creds, user.email, subject, html_body
        )
    except Exception as e:  # noqa: BLE001
        logger.error("send_wrapped_email failed for %s: %s", user.id, e)
        return False


async def dispatch_annual_wrapped(year: int, user_id: int | None = None) -> dict:
    """群发（或单发）年度报告邮件。

    由 1 月 1 日 cron 调用（year=上一年），也可由管理员端点手动触发验证。
    只给「该年有用量数据 + 有邮箱 + 账号启用」的用户发；逐个发送，单个失败
    不影响其余。返回 sent/skipped/failed 计数。
    """
    from app.services.wrapped_service import compute_wrapped

    creds = _notify_creds()
    if not creds:
        logger.warning("Wrapped 邮件跳过：系统通知邮箱未配置（NOTIFY_*）")
        return {"sent": 0, "skipped": 0, "failed": 0, "reason": "notify_email_not_configured"}

    frontend_base = _frontend_base()
    db = create_db_session()
    sent = skipped = failed = 0
    try:
        stmt = select(UserModel).where(UserModel.is_active == True)  # noqa: E712
        if user_id is not None:
            stmt = stmt.where(UserModel.id == user_id)
        users = db.scalars(stmt).all()
        for user in users:
            if not user.email:
                skipped += 1
                continue
            stats = compute_wrapped(db, user.id, year)
            if not stats.get("has_data"):
                skipped += 1
                continue
            ok = await send_wrapped_email(user, stats, frontend_base)
            if ok:
                sent += 1
            else:
                failed += 1
        logger.info("Wrapped %s dispatched: sent=%d skipped=%d failed=%d", year, sent, skipped, failed)
        return {"sent": sent, "skipped": skipped, "failed": failed}
    finally:
        db.close()
