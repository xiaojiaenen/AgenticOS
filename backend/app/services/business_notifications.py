"""业务通知邮件：部署审批结果、反馈回复。

与 ``notification_service`` 里的任务完成通知共用系统邮箱配置
（``NOTIFY_*``），但各有自己的模板与收件逻辑。全部失败静默：
通知是锦上添花，不能因为它影响主流程。
"""
from __future__ import annotations

import logging
from typing import Any

_logger = logging.getLogger("notify.business")


def _creds() -> dict[str, Any] | None:
    from app.core.config import get_settings

    s = get_settings()
    if not s.notify_email_address or not s.notify_smtp_host:
        return None
    return {
        "email": s.notify_email_address,
        "password": s.notify_email_password,
        "smtp_host": s.notify_smtp_host,
        "smtp_port": s.notify_smtp_port,
        "smtp_ssl": s.notify_smtp_ssl,
    }


def _frontend_base() -> str:
    try:
        from app.core.config import get_settings

        origins = get_settings().get_cors_allow_origins()
        return origins[0].rstrip("/") if origins else ""
    except Exception:  # noqa: BLE001
        return ""


def _read_cover(project_slug: str) -> tuple[str, bytes, str] | None:
    """读封面图用于内嵌（cid 固定 cover）。"""
    from app.core.data_path import DATA_DIR

    for name, mime in ((f"{project_slug}.webp", "image/webp"), (f"{project_slug}.png", "image/png")):
        path = DATA_DIR / "website-covers" / name
        if path.is_file():
            try:
                data = path.read_bytes()
                if len(data) <= 3_000_000:  # 超过 3MB 不内嵌（邮件网关常拒收）
                    return ("cover", data, mime)
            except OSError:
                return None
    return None


def _spawn(coro) -> None:
    """安全地丢一个 coroutine 到后台跑。

    没有运行中的事件循环时（同步上下文 / 测试）不能 create_task ——
    coroutine 既没 await 也没 close → RuntimeWarning "never awaited"，
    还会让 pytest 输出变脏。那里直接 close 掉（邮件发不出去可以接受，
    审批结果不能被它带崩）。
    """
    import asyncio as _aio

    try:
        _aio.get_running_loop()
    except RuntimeError:
        close = getattr(coro, "close", None)
        if close is not None:
            close()
        return
    _aio.create_task(coro)


async def notify_deploy_approved(
    *,
    user_email: str | None,
    user_name: str | None,
    title: str,
    project_slug: str,
    visibility: str,
    short_url: str | None,
    description: str | None = None,
) -> bool:
    """部署审批通过：告诉用户已上线，附封面与访问地址。"""
    creds = _creds()
    if creds is None or not user_email:
        return False

    from app.tools.email_tools import send_notification_email

    base = _frontend_base()
    public_link = f"{base}{short_url}" if short_url and base else (short_url or "")
    cover = _read_cover(project_slug)
    cover_block = (
        '<img src="cid:cover" alt="网站封面" '
        'style="width:100%;max-width:560px;border-radius:12px;border:1px solid #e4e4e7;margin:0 0 18px" />'
        if cover
        else ""
    )
    vis_label = "公开" if visibility == "public" else "私密（链接带签名，可随时重置）"
    html = f"""<div style="font-family:-apple-system,'Segoe UI','Noto Sans SC',sans-serif;color:#18181b;line-height:1.7">
  <h2 style="font-size:18px;margin:0 0 12px">网站已上线</h2>
  <p style="margin:0 0 16px;color:#3f3f46">你部署的「{title}」已通过审批并发布。</p>
  {cover_block}
  <table style="font-size:13px;color:#3f3f46;border-collapse:collapse">
    <tr><td style="padding:4px 12px 4px 0;color:#71717a">可见性</td><td>{vis_label}</td></tr>
    <tr><td style="padding:4px 12px 4px 0;color:#71717a">访问地址</td><td><a href="{public_link}" style="color:#2563eb">{public_link or "（见作品库）"}</a></td></tr>
    {f'<tr><td style="padding:4px 12px 4px 0;color:#71717a">说明</td><td>{description}</td></tr>' if description else ''}
  </table>
  <p style="margin:18px 0 0;font-size:12px;color:#a1a1aa">后续可在作品库管理访问统计、重置访问链接或取消部署（源码保留）。</p>
</div>"""
    try:
        return await send_notification_email(
            creds, user_email, f"网站已上线：{title}", html, is_html=True, inline_image=cover
        )
    except Exception:  # noqa: BLE001
        _logger.warning("部署通过通知发送失败: slug=%s", project_slug, exc_info=True)
        return False


async def notify_feedback_reply(
    *,
    user_email: str | None,
    issue_title: str,
    reply_text: str,
    status_label: str,
    issue_id: int,
    actor_name: str | None = None,
) -> bool:
    """反馈有新回复/状态变更：通知提交者。"""
    creds = _creds()
    if creds is None or not user_email:
        return False

    from app.tools.email_tools import send_notification_email

    base = _frontend_base()
    link = f"{base}/feedback" if base else "/feedback"
    html = f"""<div style="font-family:-apple-system,'Segoe UI','Noto Sans SC',sans-serif;color:#18181b;line-height:1.7">
  <h2 style="font-size:18px;margin:0 0 12px">你的反馈有更新</h2>
  <p style="margin:0 0 6px;color:#3f3f46">「{issue_title}」</p>
  <p style="margin:0 0 16px;font-size:13px;color:#71717a">当前状态：{status_label}</p>
  <blockquote style="margin:0 0 18px;padding:12px 16px;background:#f4f4f5;border-left:3px solid #a1a1aa;border-radius:6px;color:#3f3f46;font-size:14px">
    {reply_text}
  </blockquote>
  <p style="margin:0;font-size:13px"><a href="{link}" style="color:#2563eb">查看详情 →</a></p>
  <p style="margin:16px 0 0;font-size:12px;color:#a1a1aa">#{issue_id}{f' · {actor_name}' if actor_name else ''}</p>
</div>"""
    try:
        return await send_notification_email(
            creds, user_email, f"反馈有更新：{issue_title}", html, is_html=True
        )
    except Exception:  # noqa: BLE001
        _logger.warning("反馈通知发送失败: issue=%s", issue_id, exc_info=True)
        return False


async def notify_published_item_approved(
    *,
    user_email: str | None,
    title: str,
    kind_label: str,
    short_url: str | None,
    description: str | None = None,
) -> bool:
    """文件型作品（PPT / 文档 / 表格）审批通过：告诉用户已上架。"""
    creds = _creds()
    if creds is None or not user_email:
        return False

    from app.tools.email_tools import send_notification_email

    base = _frontend_base()
    link = f"{base}{short_url}" if short_url and base else (short_url or "")
    desc_block = (
        f'<p style="margin:0 0 16px;color:#3f3f46">{description}</p>'
        if description
        else ""
    )
    html = f"""<div style="font-family:-apple-system,'Segoe UI','Noto Sans SC',sans-serif;color:#18181b;line-height:1.7">
  <h2 style="font-size:18px;margin:0 0 12px">作品已发布</h2>
  <p style="margin:0 0 6px;color:#3f3f46">你发布的「{title}」已通过审核，现已出现在作品库。</p>
  <p style="margin:0 0 16px;font-size:13px;color:#71717a">类型：{kind_label}</p>
  {desc_block}
  <p style="margin:0;font-size:13px"><a href="{link}" style="color:#2563eb">查看作品 →</a></p>
</div>"""
    try:
        return await send_notification_email(
            creds, user_email, f"作品已发布：{title}", html, is_html=True
        )
    except Exception:  # noqa: BLE001 —— 通知失败不影响审批结果
        _logger.warning("文件型作品发布邮件发送失败: %s", user_email, exc_info=True)
        return False
