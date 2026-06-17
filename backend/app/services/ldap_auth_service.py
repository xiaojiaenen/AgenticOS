"""LDAP 认证服务 — 通过内网 LDAP 网关 HTTP API 验证用户身份。"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import encrypt_credential
from app.db.models import UserEmailCredentialsModel

logger = logging.getLogger(__name__)


class LdapAuthError(Exception):
    """LDAP 认证失败（网关返回非 0 状态或网络错误）。"""


class LdapAuthService:
    """调 LDAP 网关验证身份，自动配置用户邮箱凭据。"""

    def __init__(self, settings: Settings) -> None:
        self.gateway_url = settings.ldap_gateway_url.rstrip("/")
        self.email_domain = settings.ldap_email_domain
        self.imap_host = settings.ldap_email_imap_host
        self.imap_port = settings.ldap_email_imap_port
        self.smtp_host = settings.ldap_email_smtp_host
        self.smtp_port = settings.ldap_email_smtp_port
        self.secret = settings.auth_secret_key

    async def authenticate(self, mail_no: str, password: str) -> dict[str, str]:
        """调用网关验证用户身份，成功返回用户信息。

        Returns:
            {"mail_no": str, "email": str, "name": str}

        Raises:
            LdapAuthError: 认证失败或网络错误。
        """
        async with httpx.AsyncClient(timeout=10) as client:
            # Step 1: 登录认证
            try:
                resp = await client.post(
                    f"{self.gateway_url}/v2/ldap/auth",
                    json={"mailNo": mail_no, "password": password},
                )
                body = resp.json()
            except (httpx.RequestError, ValueError) as exc:
                logger.warning("LDAP gateway connection failed: %s", exc)
                raise LdapAuthError(f"LDAP 网关连接失败: {exc}") from exc

            if body.get("status") != 100:
                msg = body.get("message", "LDAP 认证失败")
                status_code = body.get("status", "?")
                logger.info("LDAP auth failed for %s (status=%s): %s", mail_no, status_code, msg)
                raise LdapAuthError(f"LDAP 认证失败（状态码: {status_code}），请检查工号或密码是否正确")

            # Step 2: 获取用户信息
            email = f"{mail_no}@{self.email_domain}"
            name = mail_no  # fallback
            try:
                user_resp = await client.get(f"{self.gateway_url}/v2/ldap/user")
                user_body = user_resp.json()
                if user_body.get("status") == 100:
                    user_data = user_body.get("data", {}) or {}
                    name = user_data.get("name") or user_data.get("displayName") or mail_no
            except (httpx.RequestError, ValueError) as exc:
                logger.warning("Failed to fetch LDAP user info for %s: %s", mail_no, exc)

            return {
                "mail_no": mail_no,
                "email": email,
                "name": str(name),
            }

    def auto_configure_email(
        self,
        db: Session,
        user_id: int,
        mail_no: str,
        password: str,
    ) -> None:
        """LDAP 登录成功后，自动写入/更新用户的邮箱 IMAP/SMTP 凭据。

        前提：配置了 LDAP_EMAIL_IMAP_HOST 和 LDAP_EMAIL_SMTP_HOST。
        """
        if not self.imap_host or not self.smtp_host:
            # 未配置公司邮箱服务器，跳过自动设置
            return

        email_addr = f"{mail_no}@{self.email_domain}"
        encrypted_pw = encrypt_credential(password, secret=self.secret)

        existing = db.scalar(
            select(UserEmailCredentialsModel).where(
                UserEmailCredentialsModel.user_id == user_id,
            )
        )

        if existing:
            existing.email_address = email_addr
            existing.password = ""
            existing.password_encrypted = encrypted_pw
            existing.imap_host = self.imap_host
            existing.imap_port = self.imap_port
            existing.imap_ssl = True
            existing.smtp_host = self.smtp_host
            existing.smtp_port = self.smtp_port
            existing.smtp_ssl = True
        else:
            db.add(
                UserEmailCredentialsModel(
                    user_id=user_id,
                    email_address=email_addr,
                    password="",
                    password_encrypted=encrypted_pw,
                    imap_host=self.imap_host,
                    imap_port=self.imap_port,
                    imap_ssl=True,
                    smtp_host=self.smtp_host,
                    smtp_port=self.smtp_port,
                    smtp_ssl=True,
                )
            )
        db.commit()
        logger.info("Auto-configured email credentials for user %d (%s)", user_id, email_addr)
