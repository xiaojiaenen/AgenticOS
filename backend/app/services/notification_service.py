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


def _build_email_html(task_summary: str, duration_str: str, session_id: str, frontend_base: str = "", is_error: bool = False) -> str:
    """构建符合系统风格的通知邮件 HTML"""
    chat_url = f"{frontend_base}/chat?session={session_id}" if frontend_base else ""

    # 截取摘要，避免过长
    summary = task_summary.strip()
    if len(summary) > 300:
        summary = summary[:297] + "..."

    # 转义 HTML
    summary = (
        summary.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )

    # 根据状态设置颜色和文案
    if is_error:
        header_gradient = "linear-gradient(135deg,#dc2626 0%,#b91c1c 100%)"
        status_icon = "❌"
        status_text = "任务执行失败"
        badge_bg = "rgba(255,255,255,0.18)"
    else:
        header_gradient = "linear-gradient(135deg,#2b87c2 0%,#1a6fa0 100%)"
        status_icon = "✅"
        status_text = "任务已完成"
        badge_bg = "rgba(255,255,255,0.18)"

    link_section = ""
    if chat_url:
        link_section = f"""
            <tr>
              <td style="padding:0 40px 32px">
                <a href="{chat_url}"
                   style="display:inline-block;background:#2b87c2;color:#ffffff;
                          font-size:14px;font-weight:600;text-decoration:none;
                          padding:12px 28px;border-radius:8px;letter-spacing:0.02em">
                  查看详情
                </a>
              </td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans SC',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:32px 16px">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06),0 4px 16px rgba(0,0,0,0.04)">

        <!-- Header -->
        <tr>
          <td style="background:{header_gradient};padding:32px 40px">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td>
                  <div style="font-size:13px;font-weight:600;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px">
                    AgenticOS
                  </div>
                  <div style="font-size:22px;font-weight:700;color:#ffffff;line-height:1.3">
                    {status_icon} {status_text}
                  </div>
                </td>
                <td align="right" valign="top" style="padding-top:4px">
                  <div style="display:inline-block;background:{badge_bg};border-radius:20px;padding:6px 14px;font-size:12px;font-weight:600;color:#ffffff">
                    {duration_str}
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Duration badge -->
        <tr>
          <td style="padding:28px 40px 0">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#f0f7fc;border:1px solid #d0e6f5;border-radius:12px;padding:16px 20px">
                  <table width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td width="40" valign="top">
                        <div style="width:36px;height:36px;background:#e8f2fa;border-radius:10px;text-align:center;line-height:36px;font-size:18px">
                          ⏱️
                        </div>
                      </td>
                      <td style="padding-left:14px">
                        <div style="font-size:11px;font-weight:600;color:#6b8aab;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:2px">
                          耗时
                        </div>
                        <div style="font-size:16px;font-weight:700;color:#1a5276">
                          {duration_str}
                        </div>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Task summary -->
        <tr>
          <td style="padding:20px 40px 0">
            <div style="font-size:11px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:10px">
              任务摘要
            </div>
            <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:16px 20px;font-size:14px;line-height:1.7;color:#334155;max-height:200px;overflow:hidden">
              {summary}
            </div>
          </td>
        </tr>

        <!-- Link button -->
        {link_section}

        <!-- Footer -->
        <tr>
          <td style="padding:16px 40px 28px;border-top:1px solid #f1f5f9">
            <div style="font-size:12px;color:#94a3b8;line-height:1.6">
              此邮件由 AgenticOS 自动发送。
            </div>
          </td>
        </tr>

      </table>

      <!-- Bottom text -->
      <div style="text-align:center;padding:20px 0;font-size:11px;color:#94a3b8">
        AgenticOS · AI Agent Platform
      </div>
    </td></tr>
  </table>
</body>
</html>"""


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
        html_body = _build_email_html(task_summary, duration_str, session_id, frontend_base_url, is_error=is_error)

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


def _build_welcome_email_html(user_name: str, frontend_base: str = "") -> str:
    """构建欢迎邮件 HTML"""
    login_url = f"{frontend_base}/login" if frontend_base else ""

    link_section = ""
    if login_url:
        link_section = f"""
            <tr>
              <td style="padding:0 40px 32px">
                <a href="{login_url}"
                   style="display:inline-block;background:#2b87c2;color:#ffffff;
                          font-size:14px;font-weight:600;text-decoration:none;
                          padding:12px 28px;border-radius:8px;letter-spacing:0.02em">
                  开始使用
                </a>
              </td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans SC',sans-serif">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:32px 16px">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.06),0 4px 16px rgba(0,0,0,0.04)">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#2b87c2 0%,#1a6fa0 100%);padding:32px 40px">
            <div style="font-size:13px;font-weight:600;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:0.12em;margin-bottom:8px">
              AgenticOS
            </div>
            <div style="font-size:22px;font-weight:700;color:#ffffff;line-height:1.3">
              🎉 欢迎加入
            </div>
          </td>
        </tr>

        <!-- Welcome message -->
        <tr>
          <td style="padding:32px 40px">
            <div style="font-size:16px;font-weight:600;color:#1e293b;margin-bottom:12px">
              {user_name}，你好！
            </div>
            <div style="font-size:14px;line-height:1.7;color:#475569;margin-bottom:24px">
              欢迎注册 AgenticOS — 您的 AI 智能助手平台。在这里，您可以：
            </div>

            <!-- Feature list -->
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px">
              <tr>
                <td style="padding:12px 16px;background:#f8fafc;border-radius:10px;margin-bottom:8px">
                  <div style="font-size:14px;color:#334155">
                    💬 <strong>智能对话</strong> — 与 AI 助手进行自然语言交互
                  </div>
                </td>
              </tr>
              <tr><td style="height:8px"></td></tr>
              <tr>
                <td style="padding:12px 16px;background:#f8fafc;border-radius:10px">
                  <div style="font-size:14px;color:#334155">
                    📊 <strong>PPT 生成</strong> — 一键创建精美演示文稿
                  </div>
                </td>
              </tr>
              <tr><td style="height:8px"></td></tr>
              <tr>
                <td style="padding:12px 16px;background:#f8fafc;border-radius:10px">
                  <div style="font-size:14px;color:#334155">
                    🌐 <strong>网站开发</strong> — AI 辅助构建 Web 应用
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Link button -->
        {link_section}

        <!-- Footer -->
        <tr>
          <td style="padding:16px 40px 28px;border-top:1px solid #f1f5f9">
            <div style="font-size:12px;color:#94a3b8;line-height:1.6">
              如有任何问题，请随时联系我们。
            </div>
          </td>
        </tr>

      </table>

      <div style="text-align:center;padding:20px 0;font-size:11px;color:#94a3b8">
        AgenticOS · AI Agent Platform
      </div>
    </td></tr>
  </table>
</body>
</html>"""


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

        html_body = _build_welcome_email_html(user_name, frontend_base_url)
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
