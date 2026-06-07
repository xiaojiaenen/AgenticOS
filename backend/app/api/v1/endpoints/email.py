"""Email credentials API — direct form submission, never through LLM."""

from __future__ import annotations

import imaplib
import smtplib

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import get_current_user
from app.db.models import UserEmailCredentialsModel, UserModel
from app.db.session import create_db_session

router = APIRouter(prefix="/email", tags=["email"])


class EmailCredentialsRequest(BaseModel):
    email_address: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)
    imap_host: str = Field(default="imap.exmail.qq.com", max_length=255)
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_ssl: bool = True
    smtp_host: str = Field(default="smtp.exmail.qq.com", max_length=255)
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_ssl: bool = True


class EmailStatusResponse(BaseModel):
    configured: bool
    email_address: str | None = None
    imap_host: str | None = None
    smtp_host: str | None = None


@router.get("/credentials/status", response_model=EmailStatusResponse)
def get_email_status(current_user: UserModel = Depends(get_current_user)):
    """Check if current user has configured email credentials."""
    db = create_db_session()
    try:
        cred = db.scalar(
            select(UserEmailCredentialsModel).where(
                UserEmailCredentialsModel.user_id == current_user.id
            )
        )
        if not cred:
            return EmailStatusResponse(configured=False)
        return EmailStatusResponse(
            configured=True,
            email_address=cred.email_address,
            imap_host=cred.imap_host,
            smtp_host=cred.smtp_host,
        )
    finally:
        db.close()


@router.post("/credentials")
def save_email_credentials(
    body: EmailCredentialsRequest,
    current_user: UserModel = Depends(get_current_user),
):
    """Save email credentials. Validates connection before saving."""
    # Test IMAP connection
    try:
        if body.imap_ssl:
            imap = imaplib.IMAP4_SSL(body.imap_host, body.imap_port)
        else:
            imap = imaplib.IMAP4(body.imap_host, body.imap_port)
        imap.login(body.email_address, body.password)
        imap.logout()
    except imaplib.IMAP4.error:
        return {"error": "IMAP 登录失败，请检查邮箱地址和密码"}
    except Exception as e:
        return {"error": f"IMAP 连接失败: {e}"}

    # Test SMTP connection
    try:
        if body.smtp_ssl:
            smtp = smtplib.SMTP_SSL(body.smtp_host, body.smtp_port)
        else:
            smtp = smtplib.SMTP(body.smtp_host, body.smtp_port)
        smtp.login(body.email_address, body.password)
        smtp.quit()
    except smtplib.SMTPAuthenticationError:
        return {"error": "SMTP 登录失败，请检查邮箱地址和密码"}
    except Exception as e:
        return {"error": f"SMTP 连接失败: {e}"}

    # Save to DB
    db = create_db_session()
    try:
        existing = db.scalar(
            select(UserEmailCredentialsModel).where(
                UserEmailCredentialsModel.user_id == current_user.id
            )
        )
        if existing:
            existing.email_address = body.email_address
            existing.password = body.password
            existing.imap_host = body.imap_host
            existing.imap_port = body.imap_port
            existing.imap_ssl = body.imap_ssl
            existing.smtp_host = body.smtp_host
            existing.smtp_port = body.smtp_port
            existing.smtp_ssl = body.smtp_ssl
        else:
            db.add(UserEmailCredentialsModel(
                user_id=current_user.id,
                email_address=body.email_address,
                password=body.password,
                imap_host=body.imap_host,
                imap_port=body.imap_port,
                imap_ssl=body.imap_ssl,
                smtp_host=body.smtp_host,
                smtp_port=body.smtp_port,
                smtp_ssl=body.smtp_ssl,
            ))
        db.commit()
        return {"success": True, "message": "邮箱配置已保存"}
    finally:
        db.close()


@router.delete("/credentials")
def delete_email_credentials(current_user: UserModel = Depends(get_current_user)):
    """Remove email credentials."""
    db = create_db_session()
    try:
        cred = db.scalar(
            select(UserEmailCredentialsModel).where(
                UserEmailCredentialsModel.user_id == current_user.id
            )
        )
        if cred:
            db.delete(cred)
            db.commit()
        return {"success": True, "message": "邮箱配置已删除"}
    finally:
        db.close()
