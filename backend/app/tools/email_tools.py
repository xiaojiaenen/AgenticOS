"""邮件工具 - 提供邮件读取、搜索、发送功能"""

import contextvars
import imaplib
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


def register_email_tools(registry: ToolRegistry):
    """注册邮件工具到 ToolRegistry"""

    @registry.tool(display_name="设置邮箱")
    async def setup_email(
        email_address: str,
        password: str,
        imap_host: str = "imap.exmail.qq.com",
        imap_port: int = 993,
        imap_ssl: bool = True,
        smtp_host: str = "smtp.exmail.qq.com",
        smtp_port: int = 465,
        smtp_ssl: bool = True,
    ) -> str:
        """
        设置邮箱凭据（首次使用时调用，后续可更新）

        Args:
            email_address: 公司邮箱地址
            password: 应用专用密码（不是登录密码，在邮箱设置中生成）
            imap_host: IMAP 服务器地址（默认腾讯企业邮箱）
            imap_port: IMAP 端口（默认 993）
            imap_ssl: IMAP 是否使用 SSL（默认 true）
            smtp_host: SMTP 服务器地址（默认腾讯企业邮箱）
            smtp_port: SMTP 端口（默认 465）
            smtp_ssl: SMTP 是否使用 SSL（默认 true）
        """
        session_id = _current_session_id.get()
        if not session_id:
            return "❌ 找不到当前会话信息"

        try:
            imap = _imap_connect(imap_host, imap_port, imap_ssl)
            imap.login(email_address, password)
            imap.logout()
        except imaplib.IMAP4.error as e:
            return f"❌ 登录失败: 邮箱地址或密码错误\n{str(e)}"
        except Exception as e:
            return f"❌ 连接失败: {str(e)}\n请检查网络连接、服务器地址和端口"

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

            existing = db.scalar(
                select(UserEmailCredentialsModel).where(
                    UserEmailCredentialsModel.user_id == user_id
                )
            )
            if existing:
                existing.email_address = email_address
                existing.password = password
                existing.imap_host = imap_host
                existing.imap_port = imap_port
                existing.imap_ssl = imap_ssl
                existing.smtp_host = smtp_host
                existing.smtp_port = smtp_port
                existing.smtp_ssl = smtp_ssl
                action = "更新"
            else:
                db.add(UserEmailCredentialsModel(
                    user_id=user_id,
                    email_address=email_address,
                    password=password,
                    imap_host=imap_host,
                    imap_port=imap_port,
                    imap_ssl=imap_ssl,
                    smtp_host=smtp_host,
                    smtp_port=smtp_port,
                    smtp_ssl=smtp_ssl,
                ))
                action = "保存"

            db.commit()
        finally:
            db.close()

        imap_label = "SSL" if imap_ssl else "明文"
        smtp_label = "SSL" if smtp_ssl else "明文"
        return (
            f"✅ 邮箱配置{action}成功！已连接到 {email_address}\n"
            f"IMAP: {imap_host}:{imap_port} ({imap_label})\n"
            f"SMTP: {smtp_host}:{smtp_port} ({smtp_label})\n"
            f"现在可以使用 read_emails、search_emails 等工具了。"
        )

    @registry.tool(display_name="读取邮件")
    async def read_emails(
        folder: str = "inbox",
        limit: int = 10,
        unread_only: bool = False,
    ) -> str:
        """
        读取邮件列表

        Args:
            folder: 邮箱文件夹，可选值: inbox(收件箱), sent(已发送), draft(草稿箱)
            limit: 返回邮件数量，默认10
            unread_only: 是否只显示未读邮件，默认false
        """
        creds = _get_credentials()
        if not creds:
            return "❌ 请先调用 setup_email 设置邮箱凭据"

        try:
            imap = _imap_connect(
                str(creds["imap_host"]), int(creds["imap_port"]), bool(creds["imap_ssl"])
            )
            imap.login(str(creds["email"]), str(creds["password"]))

            folder_map = {"inbox": "INBOX", "sent": "SENT", "draft": "DRAFTS"}
            imap.select(folder_map.get(folder, "INBOX"))

            criteria = "UNSEEN" if unread_only else "ALL"
            status, message_ids = imap.search(None, criteria)

            if not message_ids[0]:
                imap.logout()
                return "📭 没有找到邮件"

            emails = []
            for msg_id in message_ids[0].split()[-limit:]:
                status, msg_data = imap.fetch(msg_id, "(RFC822 FLAGS)")
                msg = email.message_from_bytes(msg_data[0][1])
                flags = msg_data[0][0].decode()

                subject = _decode_mime_header(msg["Subject"])
                from_addr = parseaddr(msg["From"])[1]
                date_str = msg["Date"]
                is_read = "\\Seen" in flags

                emails.append({
                    "id": msg_id.decode(),
                    "subject": subject[:50] + ("..." if len(subject) > 50 else ""),
                    "from": from_addr,
                    "date": date_str,
                    "is_read": is_read,
                })

            imap.logout()

            folder_names = {"inbox": "收件箱", "sent": "已发送", "draft": "草稿箱"}
            result = f"📬 {folder_names.get(folder, folder)} 共 {len(emails)} 封邮件\n\n"
            for i, mail in enumerate(emails, 1):
                status_icon = "●" if not mail["is_read"] else "○"
                result += f"{status_icon} {i}. {mail['subject']}\n"
                result += f"   发件人: {mail['from']}\n"
                result += f"   时间: {mail['date']}\n"
                result += f"   ID: {mail['id']}\n\n"

            return result

        except Exception as e:
            return f"❌ 读取邮件失败: {str(e)}"

    @registry.tool(display_name="搜索邮件")
    async def search_emails(
        query: str,
        since: str = None,
        from_address: str = None,
    ) -> str:
        """
        搜索邮件

        Args:
            query: 搜索关键词（搜索主题和正文）
            since: 起始日期，格式 YYYY-MM-DD
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

            criteria_parts = []
            if since:
                criteria_parts.append(f'SINCE "{since}"')
            if from_address:
                criteria_parts.append(f'FROM "{from_address}"')

            if criteria_parts:
                criteria = "(" + " ".join(criteria_parts) + ")"
            else:
                criteria = "ALL"

            status, message_ids = imap.search(None, criteria)

            if not message_ids[0]:
                imap.logout()
                return f"📭 没有找到包含 '{query}' 的邮件"

            results = []
            query_lower = query.lower()

            for msg_id in message_ids[0].split()[-50:]:
                status, msg_data = imap.fetch(msg_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])

                subject = _decode_mime_header(msg["Subject"])
                from_addr = parseaddr(msg["From"])[1]
                body = _get_email_body(msg)[:1000]

                if query_lower in subject.lower() or query_lower in body.lower():
                    results.append({
                        "id": msg_id.decode(),
                        "subject": subject[:50],
                        "from": from_addr,
                        "date": msg["Date"],
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

            status, msg_data = imap.fetch(message_id.encode(), "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

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

    @registry.tool(display_name="发送邮件")
    async def send_email(
        to: str,
        subject: str,
        body: str,
        cc: str = None,
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
