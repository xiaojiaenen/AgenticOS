"""凭据代理 API - 供内部系统（如爬虫平台）安全获取用户凭据。

安全措施：
1. 内部令牌验证（X-Internal-Token）
2. 凭据解密后返回
3. 访问日志记录
4. 仅限内部网络调用
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import ExternalUserCredentialModel, ExternalSystemModel
from app.services.external_system_service import ExternalSystemService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credential-proxy", tags=["Credential Proxy"])


# ── 请求/响应模型 ────────────────────────────────────────────────────────────

class CredentialRequest(BaseModel):
    """凭据请求"""
    system_id: int = Field(..., description="集成系统 ID")
    user_id: Optional[int] = Field(None, description="用户 ID（不传则返回系统级凭据）")


class CredentialResponse(BaseModel):
    """凭据响应"""
    system_id: int
    system_name: str
    credential_data: dict
    connection_status: str
    expires_at: Optional[str] = None


class BatchCredentialRequest(BaseModel):
    """批量凭据请求"""
    requests: list[CredentialRequest] = Field(..., max_length=50)


class BatchCredentialResponse(BaseModel):
    """批量凭据响应"""
    results: list[CredentialResponse]
    errors: list[dict] = []


# ── 内部令牌验证 ─────────────────────────────────────────────────────────────

def _verify_internal_token(request: Request) -> bool:
    """验证内部令牌"""
    settings = get_settings()
    internal_token = settings.credential_proxy_token

    # 如果未配置内部令牌，拒绝所有请求
    if not internal_token:
        logger.warning("credential_proxy_token not configured, rejecting request")
        return False

    # 从请求头获取令牌
    token = request.headers.get("X-Internal-Token")
    if not token:
        return False

    # 常量时间比较，防止时序攻击
    import hmac
    return hmac.compare_digest(token, internal_token)


def _get_client_info(request: Request) -> dict:
    """获取客户端信息用于日志"""
    return {
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── API 端点 ─────────────────────────────────────────────────────────────────

@router.post("/get", response_model=CredentialResponse)
async def get_credential(
    body: CredentialRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    获取单个凭据（解密后）

    仅限内部系统调用，需要 X-Internal-Token 头部。
    """
    # 验证内部令牌
    if not _verify_internal_token(request):
        logger.warning(f"Credential proxy access denied: {_get_client_info(request)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing internal token"
        )

    # 获取凭据
    svc = ExternalSystemService(db)

    try:
        # 查询用户凭据
        query = db.query(ExternalUserCredentialModel).filter(
            ExternalUserCredentialModel.system_id == body.system_id
        )

        if body.user_id:
            query = query.filter(ExternalUserCredentialModel.user_id == body.user_id)

        credential = query.first()

        if not credential:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Credential not found"
            )

        # 获取系统信息
        system = db.query(ExternalSystemModel).filter(
            ExternalSystemModel.id == body.system_id
        ).first()

        if not system:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System not found"
            )

        # 解密凭据
        credential_data = svc.decrypt_credential_data(credential)

        # 记录访问日志
        logger.info(
            f"Credential accessed: system_id={body.system_id}, "
            f"user_id={body.user_id}, {_get_client_info(request)}"
        )

        return CredentialResponse(
            system_id=system.id,
            system_name=system.name,
            credential_data=credential_data,
            connection_status=credential.connection_status,
            expires_at=credential.jwt_expires_at.isoformat() if credential.jwt_expires_at else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get credential: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve credential"
        )


@router.post("/batch", response_model=BatchCredentialResponse)
async def get_credentials_batch(
    body: BatchCredentialRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    批量获取凭据（解密后）

    仅限内部系统调用，需要 X-Internal-Token 头部。
    最多支持 50 个请求。
    """
    # 验证内部令牌
    if not _verify_internal_token(request):
        logger.warning(f"Credential proxy batch access denied: {_get_client_info(request)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing internal token"
        )

    svc = ExternalSystemService(db)
    results = []
    errors = []

    for i, req in enumerate(body.requests):
        try:
            # 查询用户凭据
            query = db.query(ExternalUserCredentialModel).filter(
                ExternalUserCredentialModel.system_id == req.system_id
            )

            if req.user_id:
                query = query.filter(ExternalUserCredentialModel.user_id == req.user_id)

            credential = query.first()

            if not credential:
                errors.append({"index": i, "error": "Credential not found"})
                continue

            # 获取系统信息
            system = db.query(ExternalSystemModel).filter(
                ExternalSystemModel.id == req.system_id
            ).first()

            if not system:
                errors.append({"index": i, "error": "System not found"})
                continue

            # 解密凭据
            credential_data = svc.decrypt_credential_data(credential)

            results.append(CredentialResponse(
                system_id=system.id,
                system_name=system.name,
                credential_data=credential_data,
                connection_status=credential.connection_status,
                expires_at=credential.jwt_expires_at.isoformat() if credential.jwt_expires_at else None,
            ))

        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    # 记录访问日志
    logger.info(
        f"Credential batch accessed: {len(results)} success, {len(errors)} errors, "
        f"{_get_client_info(request)}"
    )

    return BatchCredentialResponse(results=results, errors=errors)


@router.post("/validate")
async def validate_credential(
    body: CredentialRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    验证凭据是否有效（不解密）

    仅限内部系统调用，需要 X-Internal-Token 头部。
    """
    # 验证内部令牌
    if not _verify_internal_token(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing internal token"
        )

    # 查询凭据
    query = db.query(ExternalUserCredentialModel).filter(
        ExternalUserCredentialModel.system_id == body.system_id
    )

    if body.user_id:
        query = query.filter(ExternalUserCredentialModel.user_id == body.user_id)

    credential = query.first()

    if not credential:
        return {"valid": False, "reason": "Credential not found"}

    return {
        "valid": credential.connection_status == "connected",
        "status": credential.connection_status,
        "last_checked": credential.last_checked_at.isoformat() if credential.last_checked_at else None,
    }
