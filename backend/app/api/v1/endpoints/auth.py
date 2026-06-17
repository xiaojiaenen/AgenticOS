from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
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
from app.services.ldap_auth_service import LdapAuthError, LdapAuthService


def _is_ldap_enabled(db: Session, settings: Settings) -> bool:
    """检查 LDAP 是否启用：优先从 DB 读取，无记录时回退到环境变量。"""
    from sqlalchemy import select
    from app.db.models import SystemSettingModel
    row = db.scalar(
        select(SystemSettingModel).where(SystemSettingModel.key == "ldap_enabled")
    )
    if row is not None:
        return row.value == "true"
    return settings.ldap_enabled

router = APIRouter(prefix="/auth", tags=["Auth"])


def _to_public(user: UserModel) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        is_active=user.is_active,
        auth_source=user.auth_source,
    )


def _extract_mail_no(raw: str, domain: str) -> str | None:
    """从登录输入中提取 LDAP 工号。

    - 纯数字 → 直接作工号
    - 以 @domain 结尾 → 取前缀
    - 其他 → None（非 LDAP 用户）
    """
    s = raw.strip().lower()
    if re.fullmatch(r"\d+", s):
        return s
    if s.endswith(f"@{domain.lower()}") and "@" in s:
        prefix = s[: s.index("@")]
        if re.fullmatch(r"\d+", prefix):
            return prefix
    return None


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: AuthRegisterRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if _is_ldap_enabled(db, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="LDAP 认证已启用，注册已关闭")
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
async def login(
    request: AuthLoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    # ── LDAP 路径 ──
    if _is_ldap_enabled(db, settings):
        mail_no = _extract_mail_no(request.email, settings.ldap_email_domain)
        if mail_no is not None:
            ldap = LdapAuthService(settings)
            try:
                ldap_user = await ldap.authenticate(mail_no, request.password)
            except LdapAuthError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=str(exc),
                ) from exc

            # 查找或自动创建本地用户
            email = ldap_user["email"]
            user = db.scalar(select(UserModel).where(func.lower(UserModel.email) == email))

            if user is None:
                if settings.ldap_auto_create_users:
                    # JIT 自动创建 LDAP 用户（随机密码，LDAP 用户不通过本地密码验证）
                    import secrets
                    user = UserModel(
                        email=email,
                        name=ldap_user["name"],
                        password_hash=secrets.token_hex(32),
                        role="admin" if db.scalar(select(func.count(UserModel.id))) == 0 else "user",
                        is_active=True,
                        auth_source="ldap",
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="LDAP 用户未授权，请联系管理员",
                    )
            elif user.auth_source != "ldap":
                # 已存在但为本地用户 → 拒绝（不覆盖）
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="LDAP 用户未授权，请联系管理员",
                )
            elif not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="用户已被禁用",
                )
            else:
                # 已存在的 LDAP 用户，更新显示名
                user.name = ldap_user["name"]
                db.add(user)
                db.commit()
                db.refresh(user)

            # 自动配置邮箱凭据
            ldap.auto_configure_email(db, user.id, mail_no, request.password)

            return AuthService(db, settings)._auth_response(user)
        else:
            # 输入格式不匹配 LDAP（非数字且非公司邮箱）→ 直接拒绝
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="LDAP 认证已启用，请使用工号登录",
            )

    # ── 本地密码路径 ──
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
async def send_code(
    request: SendCodeRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """发送验证码"""
    if _is_ldap_enabled(db, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="LDAP 认证已启用，无需验证码")
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
    if _is_ldap_enabled(db, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="LDAP 认证已启用，验证码登录已关闭")
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
    if _is_ldap_enabled(db, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="LDAP 认证已启用，注册已关闭")
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
