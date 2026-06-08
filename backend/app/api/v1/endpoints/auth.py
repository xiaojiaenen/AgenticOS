from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.api.deps import bearer_scheme, get_current_user, get_db
from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.models import UserModel
from app.schemas.auth import (
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthResponse,
    LoginWithCodeRequest,
    RegisterWithCodeRequest,
    SendCodeRequest,
    UserPublic,
)
from app.services.auth_service import AuthError, AuthRateLimitError, AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _to_public(user: UserModel) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: AuthRegisterRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        result = AuthService(db, settings).register(
            email=request.email,
            name=request.name,
            password=request.password,
            client_ip=http_request.client.host if http_request.client else None,
        )
        # 发送欢迎邮件（异步，不阻塞响应）
        import asyncio
        from app.services.notification_service import send_welcome_email
        frontend_base = settings.get_cors_allow_origins()[0] if settings.get_cors_allow_origins() else ""
        asyncio.create_task(send_welcome_email(request.email, request.name, frontend_base))
        return result
    except AuthRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/login", response_model=AuthResponse)
def login(
    request: AuthLoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return AuthService(db, settings).login(
            email=request.email,
            password=request.password,
            client_ip=http_request.client.host if http_request.client else None,
        )
    except AuthRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/me", response_model=UserPublic)
def me(user: UserModel = Depends(get_current_user)) -> UserPublic:
    return _to_public(user)


@router.post("/logout")
def logout(
    _: UserModel = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    payload = decode_access_token(token, secret=settings.auth_secret_key) if token else None
    session_id = payload.get("sid") if isinstance(payload, dict) else None
    if isinstance(session_id, str) and session_id:
        AuthService(db, settings).revoke_session(session_id)
    return {"ok": True}


@router.post("/send-code")
async def send_code(request: SendCodeRequest) -> dict[str, object]:
    """发送验证码"""
    from app.services.verification_service import send_verification_code
    result = await send_verification_code(request.email, request.purpose)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])
    return {"success": True, "message": "验证码已发送"}


@router.post("/login-code", response_model=AuthResponse)
def login_with_code(
    request: LoginWithCodeRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """验证码登录"""
    try:
        return AuthService(db, settings).login_with_code(
            email=request.email,
            code=request.code,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/register-code", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register_with_code(
    request: RegisterWithCodeRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """验证码注册"""
    try:
        result = AuthService(db, settings).register_with_code(
            email=request.email,
            name=request.name,
            password=request.password,
            code=request.code,
        )
        # 发送欢迎邮件（异步，不阻塞响应）
        import asyncio
        from app.services.notification_service import send_welcome_email
        frontend_base = settings.get_cors_allow_origins()[0] if settings.get_cors_allow_origins() else ""
        asyncio.create_task(send_welcome_email(request.email, request.name, frontend_base))
        return result
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
