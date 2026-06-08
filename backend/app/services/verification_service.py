"""验证码服务 — 基于 Redis 的验证码生成、发送、验证"""

import logging
import random
import string

from app.tools.email_tools import send_notification_email

logger = logging.getLogger(__name__)

# 验证码有效期（秒）
CODE_EXPIRE_SECONDS = 300  # 5 分钟
# 验证码长度
CODE_LENGTH = 6
# 验证码最大尝试次数（存 Redis hash 记录）
MAX_VERIFY_ATTEMPTS = 5


def _generate_code() -> str:
    """生成 6 位数字验证码"""
    return "".join(random.choices(string.digits, k=CODE_LENGTH))


def _build_code_email_html(code: str, purpose: str) -> str:
    """构建验证码邮件 HTML"""
    purpose_text = "登录" if purpose == "login" else "注册"

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
              验证码
            </div>
          </td>
        </tr>

        <!-- Code -->
        <tr>
          <td style="padding:32px 40px;text-align:center">
            <div style="font-size:14px;color:#64748b;margin-bottom:16px">
              您正在进行{purpose_text}操作，验证码为：
            </div>
            <div style="display:inline-block;background:#f0f7fc;border:2px dashed #2b87c2;border-radius:12px;padding:20px 40px;margin-bottom:16px">
              <span style="font-size:36px;font-weight:700;color:#2b87c2;letter-spacing:0.2em">{code}</span>
            </div>
            <div style="font-size:13px;color:#94a3b8;line-height:1.6">
              验证码 5 分钟内有效，请勿泄露给他人。
            </div>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="padding:16px 40px 28px;border-top:1px solid #f1f5f9">
            <div style="font-size:12px;color:#94a3b8;line-height:1.6">
              如果您没有进行此操作，请忽略此邮件。
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


async def send_verification_code(email: str, purpose: str) -> dict:
    """
    发送验证码

    Args:
        email: 邮箱地址
        purpose: "login" 或 "register"

    Returns:
        {"success": True} 或 {"error": "错误信息"}
    """
    from app.core.config import get_settings
    from app.services.cache_service import get_cache_service

    settings = get_settings()
    cache = get_cache_service()

    # 检查系统邮箱是否配置
    if not settings.notify_email_address or not settings.notify_smtp_host:
        return {"error": "系统邮箱未配置，无法发送验证码"}

    # 检查发送频率限制
    can_send = await cache.check_verify_send_rate(email, purpose)
    if not can_send:
        return {"error": "发送太频繁，请稍后再试"}

    try:
        # 生成并存储验证码
        code = _generate_code()
        await cache.set_verify_code(email, purpose, code, ttl=CODE_EXPIRE_SECONDS)

        # 发送邮件
        creds = {
            "email": settings.notify_email_address,
            "password": settings.notify_email_password,
            "smtp_host": settings.notify_smtp_host,
            "smtp_port": settings.notify_smtp_port,
            "smtp_ssl": settings.notify_smtp_ssl,
        }

        import asyncio
        purpose_text = "登录" if purpose == "login" else "注册"
        subject = f"验证码 — AgenticOS {purpose_text}"
        html_body = _build_code_email_html(code, purpose)

        loop = asyncio.get_running_loop()
        success = await loop.run_in_executor(
            None,
            _send_code_email_sync,
            creds,
            email,
            subject,
            html_body,
        )

        if success:
            logger.info(f"Verification code sent to {email} for {purpose}")
            return {"success": True}
        else:
            return {"error": "发送验证码失败，请稍后重试"}

    except Exception as e:
        logger.error(f"Error sending verification code: {e}", exc_info=True)
        return {"error": "发送验证码失败"}


def _send_code_email_sync(creds: dict, to: str, subject: str, html_body: str) -> bool:
    """同步发送验证码邮件"""
    import asyncio as _asyncio
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(
            send_notification_email(creds, to, subject, html_body, is_html=True)
        )
    finally:
        loop.close()


async def verify_code(email: str, code: str, purpose: str) -> bool:
    """
    验证验证码

    Args:
        email: 邮箱地址
        code: 用户输入的验证码
        purpose: "login" 或 "register"

    Returns:
        True 验证成功，False 验证失败
    """
    from app.services.cache_service import get_cache_service

    cache = get_cache_service()

    try:
        stored_code = await cache.get_verify_code(email, purpose)

        if not stored_code:
            return False

        # 验证码匹配
        if stored_code == code:
            # 验证成功，删除验证码
            await cache.delete_verify_code(email, purpose)
            return True

        return False

    except Exception as e:
        logger.error(f"Error verifying code: {e}", exc_info=True)
        return False
