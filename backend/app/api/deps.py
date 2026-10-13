from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_access_token
from app.db.models import UserModel
from app.db.session import create_db_session
from app.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    db = create_db_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserModel:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth token")

    payload = decode_access_token(credentials.credentials, secret=settings.auth_secret_key)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid auth token") from None

    auth_service = AuthService(db, settings)
    session_id = payload.get("sid")
    if isinstance(session_id, str) and session_id and not auth_service.is_session_active(user_id, session_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth session expired")

    user = auth_service.get_user(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return user


def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


# ---------------------------------------------------------------------------
# Casbin 权限依赖（M6-C，见 app/services/permission_service.py）
# ---------------------------------------------------------------------------


def require_permission(
    action: str,
    resource_type: str,
    resolver: Callable[[Request], Any] | None = None,
):
    """按 Casbin 策略鉴权的依赖工厂。

    Args:
        action: read / write / delete / admin
        resource_type: 资源类型（``kb`` / ``skill`` / ``department`` ...），与策略里的 obj 前缀一致
        resolver: 可选，从 ``Request`` 解析 resource_id（路径参数或查询参数）。
            典型用法::

                def _kb_id(request: Request) -> int:
                    return int(request.path_params["kb_id"])

                kb_admin = require_permission("write", "kb", _kb_id)

    判定逻辑集中在 ``PermissionService.enforce_for_user``，端点不自己拼策略，
    也不允许绕过 service 直接问 enforcer。
    """
    from app.services.permission_service import get_permission_service

    def _dependency(
        request: Request,
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> UserModel:
        resource_id = resolver(request) if resolver is not None else None
        if not get_permission_service().enforce_for_user(user, action, resource_type, resource_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource_type}"
                + (f":{resource_id}" if resource_id is not None else "")
                + f" ({action})",
            )
        return user

    return _dependency


def path_param(name: str) -> Callable[[Request], Any]:
    """构造一个从路径参数取 resource_id 的 resolver。"""

    def _resolver(request: Request) -> Any:
        return request.path_params.get(name)

    return _resolver


def query_param(name: str) -> Callable[[Request], Any]:
    """构造一个从查询参数取 resource_id 的 resolver。"""

    def _resolver(request: Request) -> Any:
        return request.query_params.get(name)

    return _resolver


def require_kb_access(
    db: Session,
    user: UserModel,
    kb_id: int,
    action: str = "read",
):
    """知识库行级鉴权（M6-C）。

    行级过滤的唯一入口 —— 端点禁止各自手写判定。

    判定顺序：
      1. Casbin 策略命中（admin 全权 / dept_admin 限本部门 / 资源的直接授权）；
      2. **owner 兜底**：``kb.owner_id`` 是本人时读写删都放行。M6 之前建的库
         没有 owner 直接授权，若只靠策略表，拥有者会被自己的库挡在门外；
      3. **只读** 时回落到既有的 ``can_view_knowledge_base`` 可见性语义
         （public/org 知识库对所有人可读、private/personal 仅 owner），
         保证 M6 之前建的公开知识库不因策略表为空而不可见；
      4. 否则 403。

    Returns:
        KnowledgeBaseModel: 命中的知识库对象（省掉端点再查一次）。
    """
    from app.db.models import KnowledgeBaseModel
    from app.services.knowledge.retrieval import can_view_knowledge_base
    from app.services.permission_service import get_permission_service, knowledge_base_domains

    kb = db.get(KnowledgeBaseModel, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    if get_permission_service().enforce_for_user(
        user, action, "kb", kb.id, domains=knowledge_base_domains(kb)
    ):
        return kb

    if kb.owner_id is not None and kb.owner_id == user.id:
        return kb

    if action == "read" and can_view_knowledge_base(
        kb, user_id=user.id, is_admin=user.role == "admin"
    ):
        return kb

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Permission denied: kb:{kb_id} ({action})",
    )


def filter_readable_kb_ids(db: Session, user: UserModel, kb_ids: list[int]) -> set[int]:
    """批量行级过滤：返回 ``kb_ids`` 中当前用户可读的知识库 id 集合。

    列表查询统一走这里，避免 N+1 地逐个 require_kb_access。
    """
    from app.db.models import KnowledgeBaseModel
    from app.services.knowledge.retrieval import can_view_knowledge_base
    from app.services.permission_service import get_permission_service, knowledge_base_domains

    if not kb_ids:
        return set()
    if user.role == "admin":
        return set(kb_ids)

    service = get_permission_service()
    allowed: set[int] = set()
    for kb in db.query(KnowledgeBaseModel).filter(KnowledgeBaseModel.id.in_(kb_ids)).all():
        if service.enforce_for_user(
            user, "read", "kb", kb.id, domains=knowledge_base_domains(kb)
        ) or can_view_knowledge_base(kb, user_id=user.id, is_admin=False):
            allowed.add(kb.id)
    return allowed
