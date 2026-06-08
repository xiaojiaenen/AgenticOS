"""邮件工具 - 提供邮件读取、搜索、发送功能"""

import contextvars
import imaplib
import logging
import smtplib
import email
from email.mime.text import MIMEText
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from sqlalchemy import select

from wuwei.tools import ToolRegistry

from app.db.models import AgentSessionModel, UserEmailCredentialsModel
from app.db.session import create_db_session

logger = logging.getLogger(__name__)

_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "email_session_id", default=""
)


def set_current_session_id(session_id: str) -> None:
    _current_session_id.set(session_id)


def _get_credentials() -> dict[str, object] | None:
    """从数据库查询当前会话对应的邮箱凭据"""
    session_id = _current_session_id.get()
    if not session_id:
        return None
    db = create_db_session()
    try:
        row = db.scalar(
            select(AgentSessionModel.user_id).where(
                AgentSessionModel.session_id == session_id
            )
        )
        if row is None:
            return None
        user_id = row
        creds = db.scalar(
            select(UserEmailCredentialsModel).where(
                UserEmailCredentialsModel.user_id == user_id
            )
        )
        if creds is None:
            return None
        return {
            "email": creds.email_address,
            "password": creds.password,
            "imap_host": creds.imap_host,
            "imap_port": creds.imap_port,
            "imap_ssl": creds.imap_ssl,
            "smtp_host": creds.smtp_host,
            "smtp_port": creds.smtp_port,
            "smtp_ssl": creds.smtp_ssl,
        }
    finally:
        db.close()


def _imap_connect(host: str, port: int, ssl: bool) -> imaplib.IMAP4:
    if ssl:
        return imaplib.IMAP4_SSL(host, port)
    else:
        return imaplib.IMAP4(host, port)


def _smtp_connect(host: str, port: int, ssl: bool) -> smtplib.SMTP:
    if ssl:
        return smtplib.SMTP_SSL(host, port)
    else:
        return smtplib.SMTP(host, port)


async def send_notification_email(
    creds: dict[str, object],
    to: str,
    subject: str,
    body: str,
    is_html: bool = False,
) -> bool:
    """
    发送通知邮件（公共函数，供 notification_service 等外部模块调用）

    Args:
        creds: 邮箱凭据字典，包含 email, password, smtp_host, smtp_port, smtp_ssl
        to: 收件人邮箱地址
        subject: 邮件主题
        body: 邮件正文
        is_html: 正文是否为 HTML 格式

    Returns:
        True if sent successfully, False otherwise
    """
    email_addr = str(creds["email"])
    password = str(creds["password"])
    smtp_host = str(creds["smtp_host"])
    smtp_port = int(creds["smtp_port"])
    smtp_ssl = bool(creds["smtp_ssl"])

    try:
        subtype = "html" if is_html else "plain"
        msg = MIMEText(body, subtype, "utf-8")
        msg["From"] = email_addr
        msg["To"] = to
        msg["Subject"] = subject

        recipients = [addr.strip() for addr in to.split(",")]

        with _smtp_connect(smtp_host, smtp_port, smtp_ssl) as server:
            server.login(email_addr, password)
            server.send_message(msg, email_addr, recipients)

        return True
    except Exception as e:
        logger.error(f"Failed to send notification email: {e}")
        return False


def _decode_mime_header(header: str | None) -> str:
    """解码邮件头"""
    if not header:
        return ""
    decoded_parts = decode_header(header)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _get_email_body(msg: email.message.Message) -> str:
    """提取邮件正文"""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = f"[HTML 内容]\n{payload.decode(charset, errors='replace')[:500]}..."
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body


def _safe_fetch_message(imap: imaplib.IMAP4, msg_id: bytes | str) -> email.message.Message | None:
    """安全获取单封邮件，失败返回 None"""
    try:
        mid = msg_id if isinstance(msg_id, bytes) else msg_id.encode()
        status, msg_data = imap.fetch(mid, "(RFC822 FLAGS)")
        if status != "OK" or not msg_data:
            return None
        for item in msg_data:
            if isinstance(item, tuple) and len(item) >= 2:
                return email.message_from_bytes(item[1])
        # Fallback: msg_data[0] might be the raw response
        if msg_data[0] is not None and not isinstance(msg_data[0], bytes):
            return None
        return None
    except Exception:
        logger.warning("Failed to fetch email message", exc_info=True)
        return None


def _parse_imap_date(date_str: str, delta_days: int = 0) -> str:
    """将 YYYY-MM-DD 转为 IMAP DD-Mon-YYYY 格式，支持天数偏移"""
    import datetime
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        adjusted = dt + datetime.timedelta(days=delta_days)
        return adjusted.strftime("%d-%b-%Y")
    except ValueError:
        return ""


# Cache: host:port → UTC offset in hours
_server_tz_cache: dict[str, float] = {}

# IMAP folder name → Chinese display name
_FOLDER_DISPLAY_NAMES: dict[str, str] = {
    "inbox": "收件箱",
    "sent": "已发送",
    "draft": "草稿箱",
    "trash": "已删除",
    "junk": "垃圾邮件",
    "spam": "垃圾邮件",
    "archive": "归档",
    "templates": "模板",
}

# User-facing folder name → IMAP SELECT target (try common providers)
_FOLDER_IMAP_TARGETS: dict[str, list[str]] = {
    "inbox": ["INBOX"],
    "sent": ["SENT", "Sent", "Sent Items", "[Gmail]/Sent Mail"],
    "draft": ["DRAFTS", "Draft", "Drafts", "[Gmail]/Drafts"],
    "trash": ["TRASH", "Trash", "Deleted Items", "[Gmail]/Trash"],
    "junk": ["Junk", "Junk E-mail", "[Gmail]/Spam"],
    "spam": ["Junk", "Junk E-mail", "[Gmail]/Spam"],
    "archive": ["Archive", "[Gmail]/All Mail"],
    "templates": ["Templates"],
}


def _resolve_imap_folder(imap: imaplib.IMAP4, folder: str) -> str:
    """Resolve a user-facing folder name to an actual IMAP mailbox name."""
    candidates = _FOLDER_IMAP_TARGETS.get(folder.lower(), [folder])
    for candidate in candidates:
        status, _ = imap.select(candidate)
        if status == "OK":
            return candidate
    # Last resort: try the folder name as-is
    return folder


def _folder_display_name(folder: str) -> str:
    """Get Chinese display name for a folder, falling back to raw name."""
    return _FOLDER_DISPLAY_NAMES.get(folder.lower(), folder)


def _detect_server_utc_offset(imap: imaplib.IMAP4, host: str, port: int) -> float:
    """探测 IMAP 服务器的时区偏移（小时），结果会被缓存。"""
    import datetime
    import re
    cache_key = f"{host}:{port}"
    if cache_key in _server_tz_cache:
        return _server_tz_cache[cache_key]
    try:
        status, ids = imap.search(None, "ALL")
        if status != "OK" or not ids or not ids[0]:
            return 0.0
        # 取最新一封邮件的 INTERNALDATE
        latest_id = ids[0].split()[-1]
        status, data = imap.fetch(latest_id, "(INTERNALDATE)")
        if status != "OK" or not data or not isinstance(data[0], bytes):
            return 0.0
        match = re.search(rb'"([^"]+)"', data[0])
        if not match:
            return 0.0
        from email.utils import parsedate_to_datetime
        internal_dt = parsedate_to_datetime(match.group(1).decode())
        if internal_dt is None or internal_dt.tzinfo is None or internal_dt.utcoffset() is None:
            return 0.0
        offset = internal_dt.utcoffset().total_seconds() / 3600
        _server_tz_cache[cache_key] = offset
        return offset
    except Exception:
        logger.warning("Failed to detect server UTC offset", exc_info=True)
        return 0.0


def _user_date_to_server_date(date_str: str, server_offset: float) -> str:
    """将用户日期（假定 UTC+8）转为服务器本地日期，用于 IMAP SINCE/BEFORE。

    用户在中国（UTC+8），服务器可能在任意时区。
    算出用户日期零点对应的服务器区日期，返回 DD-Mon-YYYY 格式。
    """
    import datetime
    try:
        user_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        # 用户日期零点 → UTC
        user_tz = datetime.timezone(datetime.timedelta(hours=8))
        user_midnight = user_dt.replace(tzinfo=user_tz)
        # UTC 对应时刻
        utc_moment = user_midnight.astimezone(datetime.timezone.utc)
        # 服务器时区对应日期
        server_tz = datetime.timezone(datetime.timedelta(hours=server_offset))
        server_moment = utc_moment.astimezone(server_tz)
        return server_moment.strftime("%d-%b-%Y")
    except ValueError:
        return ""


def _email_date_utc(date_header: str | None) -> "datetime.datetime | None":
    """解析邮件 Date 头并转为 UTC datetime"""
    import datetime
    if not date_header:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_header)
    except Exception:
        logger.warning("Failed to parse email date header", exc_info=True)
        return None


def _is_date_in_range(date_header: str | None, since: str, before: str) -> bool:
    """检查邮件 Date 头是否在用户指定的时间范围内（归一化到 UTC 比较，不受服务器时区影响）"""
    import datetime
    if not since and not before:
        return True
    utc_dt = _email_date_utc(date_header)
    if utc_dt is None:
        return True  # 无法解析日期则保留
    # Normalize to UTC for apples-to-apples comparison
    if utc_dt.tzinfo is not None:
        utc_dt = utc_dt.astimezone(datetime.timezone.utc)
    utc_date = utc_dt.date()
    if since:
        try:
            since_date = datetime.datetime.strptime(since, "%Y-%m-%d").date()
            if utc_date < since_date:
                return False
        except ValueError:
            pass
    if before:
        try:
            before_date = datetime.datetime.strptime(before, "%Y-%m-%d").date()
            if utc_date > before_date:
                return False
        except ValueError:
            pass
    return True


def register_email_tools(registry: ToolRegistry):
    """注册邮件工具到 ToolRegistry"""

    @registry.tool(display_name="检查邮箱配置")
    async def setup_email() -> str:
        """
        检查当前用户的邮箱是否已配置。
        邮箱凭据需在侧边栏「邮箱设置」中配置，不在对话中输入密码。
        """
        session_id = _current_session_id.get()
        if not session_id:
            return "❌ 找不到当前会话信息"

        db = create_db_session()
        try:
            row = db.scalar(
                select(AgentSessionModel.user_id).where(
                    AgentSessionModel.session_id == session_id
                )
            )
            if row is None:
                return "❌ 找不到当前会话的用户信息"

            cred = db.scalar(
                select(UserEmailCredentialsModel).where(
                    UserEmailCredentialsModel.user_id == row
                )
            )
            if not cred:
                return "❌ 尚未配置邮箱。请在侧边栏点击「邮箱设置」配置邮箱凭据，配置完成后即可使用邮件功能。"

            return (
                f"✅ 邮箱已配置：{cred.email_address}\n"
                f"IMAP: {cred.imap_host}:{cred.imap_port}\n"
                f"SMTP: {cred.smtp_host}:{cred.smtp_port}\n"
                f"现在可以使用 read_emails、search_emails、send_emails 等工具。"
            )
        finally:
            db.close()

    @registry.tool(display_name="读取邮件")
    async def read_emails(
        folder: str = "inbox",
        limit: int = 10,
        offset: int = 0,
        unread_only: bool = False,
        since: str = "",
        before: str = "",
    ) -> str:
        """
        读取邮件列表，支持分页、时间范围和未读筛选

        Args:
            folder: 邮箱文件夹，常见值: inbox, sent, draft, trash, junk, archive
            limit: 返回邮件数量，默认10
            offset: 跳过前N封邮件，默认0（用于分页）
            unread_only: 是否只显示未读邮件，默认false
            since: 起始日期，格式 YYYY-MM-DD，只返回该日期之后的邮件
            before: 结束日期，格式 YYYY-MM-DD，只返回该日期之前的邮件
        """
        creds = _get_credentials()
        if not creds:
            return "❌ 请先调用 setup_email 设置邮箱凭据"

        try:
            imap = _imap_connect(
                str(creds["imap_host"]), int(creds["imap_port"]), bool(creds["imap_ssl"])
            )
            imap.login(str(creds["email"]), str(creds["password"]))

            imap.select(_resolve_imap_folder(imap, folder))

            # Detect server timezone offset for precise date conversion
            server_offset = _detect_server_utc_offset(
                imap, str(creds["imap_host"]), int(creds["imap_port"])
            )

            # Build IMAP search criteria with timezone-aware date conversion
            criteria_parts = []
            if unread_only:
                criteria_parts.append("UNSEEN")
            if since:
                server_since = _user_date_to_server_date(since, server_offset)
                if server_since:
                    criteria_parts.append(f'SINCE "{server_since}"')
            if before:
                # BEFORE is strict less-than, so query the day after user's target
                import datetime as _dt
                _next = _dt.datetime.strptime(before, "%Y-%m-%d") + _dt.timedelta(days=1)
                server_before = _user_date_to_server_date(_next.strftime("%Y-%m-%d"), server_offset)
                if server_before:
                    criteria_parts.append(f'BEFORE "{server_before}"')

            if criteria_parts:
                criteria = "(" + " ".join(criteria_parts) + ")"
            else:
                criteria = "ALL"

            status, message_ids = imap.search(None, criteria)

            if status != "OK" or not message_ids or not message_ids[0]:
                imap.logout()
                return f"📭 {_folder_display_name(folder)} 没有找到匹配的邮件"

            all_ids = message_ids[0].split()
            total_count = len(all_ids)

            # Apply offset and limit
            paged_ids = all_ids[offset:offset + limit] if offset > 0 else all_ids[-limit:]

            if not paged_ids:
                imap.logout()
                return f"📭 offset={offset} 超出范围，共 {total_count} 封邮件"

            emails = []
            for msg_id in paged_ids:
                msg = _safe_fetch_message(imap, msg_id)
                if msg is None:
                    continue

                subject = _decode_mime_header(msg["Subject"])
                from_addr = parseaddr(msg["From"])[1]
                date_str = msg["Date"]
                # Determine read status from flags (approximate)
                is_read = True  # default
                try:
                    mid = msg_id if isinstance(msg_id, bytes) else msg_id.encode()
                    s, d = imap.fetch(mid, "(FLAGS)")
                    if s == "OK" and d and d[0]:
                        flags_str = d[0].decode() if isinstance(d[0], bytes) else str(d[0])
                        is_read = "\\Seen" in flags_str
                except Exception:
                    logger.debug("Failed to determine read status for message", exc_info=True)

                emails.append({
                    "id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                    "subject": subject[:50] + ("..." if len(subject) > 50 else ""),
                    "from": from_addr,
                    "date": date_str,
                    "is_read": is_read,
                })

            imap.logout()

            # Client-side date filtering (UTC-based, immune to server timezone)
            if since or before:
                emails = [m for m in emails if _is_date_in_range(m.get("date", ""), since, before)]

            range_info = f"第 {offset + 1}-{offset + len(emails)} 封" if offset > 0 else f"最新 {len(emails)} 封"
            result = f"📬 {_folder_display_name(folder)} 共 {total_count} 封邮件（{range_info}）\n\n"
            for i, mail in enumerate(emails, offset + 1 if offset > 0 else 1):
                status_icon = "●" if not mail["is_read"] else "○"
                result += f"{status_icon} {i}. {mail['subject']}\n"
                result += f"   发件人: {mail['from']}\n"
                result += f"   时间: {mail['date']}\n"
                result += f"   ID: {mail['id']}\n\n"

            return result

        except Exception as e:
            return f"❌ 读取邮件失败: {str(e)}"

    @registry.tool(display_name="统计邮件数")
    async def count_emails(
        folder: str = "inbox",
        unread_only: bool = False,
        since: str = "",
        before: str = "",
    ) -> str:
        """
        统计邮件数量

        Args:
            folder: 邮箱文件夹，常见值: inbox, sent, draft, trash, junk, archive
            unread_only: 是否只统计未读邮件，默认false
            since: 起始日期，格式 YYYY-MM-DD
            before: 结束日期，格式 YYYY-MM-DD
        """
        creds = _get_credentials()
        if not creds:
            return "❌ 请先调用 setup_email 设置邮箱凭据"

        try:
            imap = _imap_connect(
                str(creds["imap_host"]), int(creds["imap_port"]), bool(creds["imap_ssl"])
            )
            imap.login(str(creds["email"]), str(creds["password"]))

            imap.select(_resolve_imap_folder(imap, folder))

            # Detect server timezone offset for precise date conversion
            server_offset = _detect_server_utc_offset(
                imap, str(creds["imap_host"]), int(creds["imap_port"])
            )

            # Build criteria with timezone-aware date conversion
            criteria_parts = []
            if unread_only:
                criteria_parts.append("UNSEEN")
            if since:
                server_since = _user_date_to_server_date(since, server_offset)
                if server_since:
                    criteria_parts.append(f'SINCE "{server_since}"')
            if before:
                # BEFORE is strict less-than, so query the day after user's target
                import datetime as _dt
                _next = _dt.datetime.strptime(before, "%Y-%m-%d") + _dt.timedelta(days=1)
                server_before = _user_date_to_server_date(_next.strftime("%Y-%m-%d"), server_offset)
                if server_before:
                    criteria_parts.append(f'BEFORE "{server_before}"')

            if criteria_parts:
                criteria = "(" + " ".join(criteria_parts) + ")"
            else:
                criteria = "ALL"

            status, message_ids = imap.search(None, criteria)
            imap.logout()

            if status != "OK" or not message_ids or not message_ids[0]:
                total = 0
            else:
                total = len(message_ids[0].split())

            # Also get total and unread counts for inbox
            result = f"📊 {_folder_display_name(folder)} 统计\n"
            result += f"   当前筛选: {criteria}\n"
            result += f"   邮件数量: {total} 封\n"

            return result

        except Exception as e:
            return f"❌ 统计邮件失败: {str(e)}"

    @registry.tool(display_name="搜索邮件")
    async def search_emails(
        query: str,
        since: str = "",
        before: str = "",
        from_address: str = "",
    ) -> str:
        """
        搜索邮件（按关键词搜索主题和正文）

        Args:
            query: 搜索关键词（搜索主题和正文）
            since: 起始日期，格式 YYYY-MM-DD
            before: 结束日期，格式 YYYY-MM-DD
            from_address: 发件人地址筛选
        """
        creds = _get_credentials()
        if not creds:
            return "❌ 请先调用 setup_email 设置邮箱凭据"

        try:
            imap = _imap_connect(
                str(creds["imap_host"]), int(creds["imap_port"]), bool(creds["imap_ssl"])
            )
            imap.login(str(creds["email"]), str(creds["password"]))
            imap.select("INBOX")

            # Detect server timezone offset for precise date conversion
            server_offset = _detect_server_utc_offset(
                imap, str(creds["imap_host"]), int(creds["imap_port"])
            )

            # Build IMAP search criteria with timezone-aware date conversion
            criteria_parts = []
            if since:
                server_since = _user_date_to_server_date(since, server_offset)
                if server_since:
                    criteria_parts.append(f'SINCE "{server_since}"')
            if before:
                # BEFORE is strict less-than, so query the day after user's target
                import datetime as _dt
                _next = _dt.datetime.strptime(before, "%Y-%m-%d") + _dt.timedelta(days=1)
                server_before = _user_date_to_server_date(_next.strftime("%Y-%m-%d"), server_offset)
                if server_before:
                    criteria_parts.append(f'BEFORE "{server_before}"')
            if from_address:
                criteria_parts.append(f'FROM "{from_address}"')

            if criteria_parts:
                criteria = "(" + " ".join(criteria_parts) + ")"
            else:
                criteria = "ALL"

            status, message_ids = imap.search(None, criteria)

            if status != "OK" or not message_ids or not message_ids[0]:
                imap.logout()
                return f"📭 没有找到包含 '{query}' 的邮件"

            results = []
            query_lower = query.lower()

            for msg_id in reversed(message_ids[0].split()[-100:]):
                msg = _safe_fetch_message(imap, msg_id)
                if msg is None:
                    continue

                subject = _decode_mime_header(msg["Subject"])
                from_addr = parseaddr(msg["From"])[1]
                date_str = msg["Date"]
                body = _get_email_body(msg)[:1000]

                # Apply UTC-based date filter (immune to server timezone)
                if not _is_date_in_range(date_str, since, before):
                    continue

                if query_lower in subject.lower() or query_lower in body.lower():
                    results.append({
                        "id": msg_id.decode() if isinstance(msg_id, bytes) else msg_id,
                        "subject": subject[:50],
                        "from": from_addr,
                        "date": date_str,
                        "snippet": body[:100].replace("\n", " "),
                    })

                if len(results) >= 10:
                    break

            imap.logout()

            if not results:
                return f"📭 没有找到包含 '{query}' 的邮件"

            result = f"🔍 搜索 '{query}' 找到 {len(results)} 封邮件\n\n"
            for i, mail in enumerate(results, 1):
                result += f"{i}. {mail['subject']}\n"
                result += f"   发件人: {mail['from']}\n"
                result += f"   时间: {mail['date']}\n"
                result += f"   摘要: {mail['snippet']}...\n"
                result += f"   ID: {mail['id']}\n\n"

            return result

        except Exception as e:
            return f"❌ 搜索邮件失败: {str(e)}"

    @registry.tool(display_name="查看邮件")
    async def get_email(message_id: str) -> str:
        """
        读取邮件完整内容

        Args:
            message_id: 邮件ID（从 read_emails 或 search_emails 返回）
        """
        creds = _get_credentials()
        if not creds:
            return "❌ 请先调用 setup_email 设置邮箱凭据"

        try:
            imap = _imap_connect(
                str(creds["imap_host"]), int(creds["imap_port"]), bool(creds["imap_ssl"])
            )
            imap.login(str(creds["email"]), str(creds["password"]))
            imap.select("INBOX")

            msg = _safe_fetch_message(imap, message_id)
            if msg is None:
                imap.logout()
                return f"❌ 找不到邮件 {message_id}，可能已被删除或 ID 不正确"

            subject = _decode_mime_header(msg["Subject"])
            from_addr = parseaddr(msg["From"])[1]
            to_addr = parseaddr(msg["To"])[1]
            date_str = msg["Date"]
            body = _get_email_body(msg)

            attachments = []
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_disposition() == "attachment":
                        filename = part.get_filename()
                        if filename:
                            attachments.append(_decode_mime_header(filename))

            imap.logout()

            result = f"📧 邮件详情\n\n"
            result += f"主题: {subject}\n"
            result += f"发件人: {from_addr}\n"
            result += f"收件人: {to_addr}\n"
            result += f"时间: {date_str}\n"

            if attachments:
                result += f"附件: {', '.join(attachments)}\n"

            result += f"\n{'='*50}\n\n"
            result += body

            return result

        except Exception as e:
            return f"❌ 读取邮件失败: {str(e)}"

    @registry.tool(display_name="发送邮件", requires_approval=True)
    async def send_email(
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        is_html: bool = False,
    ) -> str:
        """
        发送邮件（需要用户确认后才能发送）

        Args:
            to: 收件人邮箱地址，多个用逗号分隔
            subject: 邮件主题
            body: 邮件正文
            cc: 抄送邮箱地址，多个用逗号分隔（可选）
            is_html: 正文是否为 HTML 格式（默认 false，纯文本）
        """
        creds = _get_credentials()
        if not creds:
            return "❌ 请先调用 setup_email 设置邮箱凭据"

        email_addr = str(creds["email"])
        password = str(creds["password"])
        smtp_host = str(creds["smtp_host"])
        smtp_port = int(creds["smtp_port"])
        smtp_ssl = bool(creds["smtp_ssl"])

        try:
            subtype = "html" if is_html else "plain"
            msg = MIMEText(body, subtype, "utf-8")
            msg["From"] = email_addr
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            recipients = [addr.strip() for addr in to.split(",")]
            if cc:
                recipients.extend([addr.strip() for addr in cc.split(",")])

            with _smtp_connect(smtp_host, smtp_port, smtp_ssl) as server:
                server.login(email_addr, password)
                server.send_message(msg, email_addr, recipients)

            format_label = "HTML" if is_html else "纯文本"
            result = f"✅ 邮件发送成功！（{format_label}）\n收件人: {to}\n主题: {subject}"
            if cc:
                result += f"\n抄送: {cc}"
            return result

        except Exception as e:
            return f"❌ 发送邮件失败: {str(e)}"

    @registry.tool(display_name="清除邮箱凭据")
    async def clear_email_credentials() -> str:
        """
        清除邮箱凭据
        """
        session_id = _current_session_id.get()
        if not session_id:
            return "❌ 找不到当前会话信息"
        db = create_db_session()
        try:
            row = db.scalar(
                select(AgentSessionModel.user_id).where(
                    AgentSessionModel.session_id == session_id
                )
            )
            if row is None:
                return "❌ 找不到当前会话的用户信息"
            user_id = row

            creds = db.scalar(
                select(UserEmailCredentialsModel).where(
                    UserEmailCredentialsModel.user_id == user_id
                )
            )
            if creds:
                db.delete(creds)
                db.commit()
                return "✅ 邮箱凭据已清除"
            return "ℹ️ 当前用户没有存储邮箱凭据"
        finally:
            db.close()
