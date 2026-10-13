"""LDAP 认证服务 — 通过内网 LDAP 网关 HTTP API 验证用户身份。"""

from __future__ import annotations

import logging

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


class LdapDirectoryService:
    """LDAP 目录/部门同步（M6-C）。

    ⚠️ 关于属性映射的重要说明
    ------------------------
    本仓库的 LDAP 网关（``/v2/ldap/auth`` + ``/v2/ldap/user``）**没有**暴露部门接口，
    而不同 IdP（AD / OpenLDAP / 内部网关）返回的部门字段差异极大。本实现因此：

    1. 全部字段名都做成可配置（``LDAP_DIRECTORY_USER_PATH`` /
       ``LDAP_DEPARTMENT_DN_ATTRIBUTE`` / ``LDAP_DEPARTMENT_NAME_ATTRIBUTE`` …），
       不在代码里硬编码任何 DN 语法；
    2. 未配置 ``LDAP_DEPARTMENT_SYNC_ENABLED`` 时**整体跳过**（不猜、不报错），
       登录流程完全不受影响；
    3. gateway 返回结构不认识时，只打 warning 并原样记录 payload 的类型，
       便于对接真实 IdP 后按实际结构调整（不抛异常打断登录）。

    对接时需要向 LDAP 网关确认的事项（TODO）：
      - 部门所在字段名（``department`` / ``distinguishedName`` / ``ou`` ?）
      - 部门 DN 是完整 DN 还是相对 RDN，是否与 ``departments.ldap_dn`` 同源
      - 多部门用户（``memberOf`` 多值）取哪一个 —— 目前取第一个并在日志中提示
    """

    def __init__(self, settings: Settings) -> None:
        self.gateway_url = settings.ldap_gateway_url.rstrip("/")
        self.email_domain = settings.ldap_email_domain
        self.enabled = settings.ldap_department_sync_enabled
        self.user_path = settings.ldap_directory_user_path
        self.dn_attribute = settings.ldap_department_dn_attribute
        self.name_attribute = settings.ldap_department_name_attribute
        self.search_base = settings.ldap_directory_search_base

    # -- 原始调用 ---------------------------------------------------------
    async def fetch_directory_entry(self, mail_no: str) -> dict[str, object] | None:
        """拉取单个用户的目录条目。未启用或网关无此接口时返回 None。"""
        if not self.enabled or not self.gateway_url or not self.user_path:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(
                    f"{self.gateway_url}{self.user_path}",
                    params={"mailNo": mail_no, "base": self.search_base} if self.search_base else {"mailNo": mail_no},
                )
                body = resp.json()
            except (httpx.RequestError, ValueError) as exc:
                logger.warning("LDAP directory lookup failed for %s: %s", mail_no, exc)
                return None
        if body.get("status") != 100:
            logger.info("LDAP directory returned no entry for %s: %s", mail_no, body.get("message"))
            return None
        data = body.get("data")
        if not isinstance(data, dict):
            logger.warning("Unexpected LDAP directory payload for %s: %r", mail_no, data)
            return None
        return data

    # -- 归一化 -----------------------------------------------------------
    def extract_department(self, entry: dict[str, object]) -> tuple[str | None, str | None]:
        """从目录条目抽出 (ldap_dn, 部门名)。

        纯函数，便于单测。DN 与名称都取自**可配置的属性名**，不做任何语法改写 ——
        归一化（例如把 ``cn=Finance,ou=Groups,dc=corp`` 压成 ``Finance``）留给
        ``departments.ldap_dn`` 的精确匹配或后续显式规则，不在这里猜。
        """
        raw_dn = entry.get(self.dn_attribute)
        if isinstance(raw_dn, (list, tuple)):
            if not raw_dn:
                return None, None
            if len(raw_dn) > 1:
                logger.warning("LDAP entry has %d department values, using the first: %r", len(raw_dn), raw_dn)
            raw_dn = raw_dn[0]
        dn = str(raw_dn).strip() if raw_dn else None

        raw_name = entry.get(self.name_attribute)
        if isinstance(raw_name, (list, tuple)):
            raw_name = raw_name[0] if raw_name else None
        name = str(raw_name).strip() if raw_name else None
        return (dn or None), (name or None)

    # -- 同步 -------------------------------------------------------------
    async def sync_user_department(self, db: Session, user, mail_no: str) -> bool:
        """登录时同步**本人**部门。返回是否发生了变更。"""
        if not self.enabled:
            return False
        entry = await self.fetch_directory_entry(mail_no)
        if not entry:
            return False
        return self.apply_department(db, user, entry)

    def apply_department(self, db: Session, user, entry: dict[str, object]) -> bool:
        """把目录条目应用到用户（按 ldap_dn 匹配已有部门，否则按名创建）。返回是否变更。

        同步路径（不依赖网络），供登录同步与管理员全量同步共用。
        """
        from sqlalchemy import select

        from app.db.models import DepartmentModel
        from app.services.department_service import (
            DepartmentError,
            create_department,
            get_department_by_name,
        )

        dn, name = self.extract_department(entry)
        if not dn and not name:
            return False

        dept: DepartmentModel | None = None
        if dn:
            dept = db.scalar(select(DepartmentModel).where(DepartmentModel.ldap_dn == dn))
        if dept is None and name:
            dept = get_department_by_name(db, name)
            if dept is not None and not dept.ldap_dn:
                dept.ldap_dn = dn
                db.add(dept)

        if dept is None:
            if not name:
                logger.info("LDAP department DN %s has no local counterpart and no name; skipped", dn)
                return False
            try:
                dept = create_department(db, name=name, ldap_dn=dn)
                logger.info("Auto-created department %s from LDAP (dn=%s)", dept.name, dn)
            except DepartmentError:
                return False

        if user.department_id == dept.id:
            return False

        from app.services.department_service import assign_user_department

        assign_user_department(db, user, dept.id)
        logger.info("Synced user %s into department %s (%s)", user.id, dept.name, dept.path)
        return True
