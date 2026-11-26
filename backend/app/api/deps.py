from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core import roles
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少登录凭证")

    payload = decode_access_token(credentials.credentials, secret=settings.auth_secret_key)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证无效，请重新登录")

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录凭证无效，请重新登录") from None

    auth_service = AuthService(db, settings)
    session_id = payload.get("sid")
    if isinstance(session_id, str) and session_id and not auth_service.is_session_active(user_id, session_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth session expired")

    user = auth_service.get_user(user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号未激活")

    # 「最近活跃」持久化 + 会话滑动续期：共用 60s 节流窗口，避免每个请求
    # 都写库。「当前在线」另由前端周期调用 /presence/heartbeat 走 Redis 心跳。
    #
    # 滑动续期解决「JWT 24 小时硬顶」：原来 expires_at 是登录时刻 + 24h 的
    # 固定值，活跃用户也会在用着用着的时候被 401 踢出去（每个用户每天必撞
    # 一次）。现在校验通过就把过期时间滑到"现在 + 24h"—— 活跃的人不掉线；
    # 被吊销的会话不续（强制下线语义不被洗掉，密码轮换自愈依赖这一点）。
    try:
        from app.core.timezone import app_now, to_app_timezone

        now = app_now()
        last = to_app_timezone(user.last_active_at) if user.last_active_at else None
        if last is None or (now - last).total_seconds() > 60:
            user.last_active_at = now
            if isinstance(session_id, str) and session_id:
                auth_service.slide_session_expiry(session_id)
            db.commit()
    except Exception:  # noqa: BLE001 -- 活跃时间刷新失败不影响鉴权
        db.rollback()
    return user


def require_admin(user: UserModel = Depends(get_current_user)) -> UserModel:
    """要求**完整平台管理**能力（`CAP_USER_MANAGE`：admin / superadmin）。

    注：函数名是历史遗留，判的是能力而非角色名（operator/auditor 过不了）。
    若端点只需审计只读或内容管理，应改用 `require_capability(CAP_AUDIT_VIEW)`
    或对应能力位，而不是误用本依赖。

    注意 operator（运营）/ auditor（审计员）**不是** admin：他们能进后台
    但只能用自己的专有端点（`require_capability`）。这样保持既有语义不漂移，
    同时新角色按需逐步放开具体能力。
    """
    if not roles.is_admin_like(user.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要完整平台管理权限（user:manage）",
        )
    return user


def require_capability(capability: str):
    """按能力做鉴权（兼容旧端点；新代码优先用 require_permission）。

    比 `require_admin` 更精确：运营能管内容但进不了用户管理，
    审计员只能读统计 —— 这些差异都在 `roles.py` 一张表里。
    """

    def dependency(user: UserModel = Depends(get_current_user)) -> UserModel:
        if not roles.has_capability(user.role, capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限：{capability}",
            )
        return user

    return dependency


def require_perm(permission: str):
    """按**权限点**鉴权（新端点的首选，权限矩阵的唯一判定入口）。

    注：名字不带 `_permission` 后缀，是因为本文件下方还有一个历史遗留的
    ``require_permission(action, resource_type, resolver)``（Casbin 资源级，
    已无调用方）。两者签名不同，故意用不同名字避免覆盖。

    权限点在 ``app.core.permission_catalog`` 注册；判定走
    ``permission_checker.has_permission``（角色自定义矩阵 > 内置默认，
    支持用户多角色并集）。未知权限点一律拒绝（fail-closed）。
    """

    def dependency(
        user: UserModel = Depends(get_current_user),
        db=Depends(get_db),
    ) -> UserModel:
        from app.services.permission_checker import has_permission

        if not has_permission(db, user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限：{permission}",
            )
        return user

    return dependency


def client_capabilities(user: UserModel) -> dict[str, object]:
    """前端要的「我能做什么」摘要（随 /auth/me 下发）。

    同时给 `can_enter_admin` 与完整能力位：前端用它决定菜单可见性，
    不再硬编码 `role === 'admin'` —— 加角色不用改前端。
    """
    return {
        "can_enter_admin": roles.can_enter_admin(user.role),
        "capabilities": sorted(roles.capabilities_for(user.role)),
    }


# ---------------------------------------------------------------------------
# Casbin 权限依赖（M6-C，见 app/services/permission_service.py）
# ---------------------------------------------------------------------------


def require_feature(action: str, feature: str):
    """功能级鉴权依赖工厂。

    这是本系统推荐的授权粒度：策略里写 ``p, <角色>, *, feature:build_website, write``
    表示「这个角色能用构建网站这个功能」，而不是「能操作某个 skill 实例」。

    与 ``require_permission`` 的区别：功能级没有资源实例，``obj`` 恒为
    ``feature:<name>``，因此不需要 resolver，也不会因为新增一个实例而失效。

    管理员仍然直接放行（``enforce_for_user`` 里的 admin 短路），这与
    ``require_admin`` 的既有语义一致。

    Args:
        action: read / write / delete / admin（read 表示「使用」）
        feature: 功能标识，与 ``FEATURE_GRANTS`` 里的键一致
    """
    from app.services.permission_service import get_permission_service

    def _dependency(
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> UserModel:
        service = get_permission_service()
        # 注意：require_feature 保持 **fail-closed**（未授权即拒绝）——
        # 这是既有契约，tests/test_permissions 有专门用例钉住。
        # 「新功能未配置时放行」的兼容语义只用于工作流（见
        # require_feature_compatible），不要改这里。
        if not service.enforce_for_user(user, action, "feature", feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: feature:{feature} ({action})",
            )
        return user

    return _dependency


def require_feature_compatible(action: str, feature: str):
    """功能级鉴权的**向后兼容**变体：新功能未配置前放行。

    与 ``require_feature`` 的差别只有一条：策略表里**从未出现过**该 feature
    时直接放行，一旦管理员显式写过（授权或收权）就严格按 Casbin 判定。

    用途：给**新上线**的功能接门禁。否则升级瞬间所有存量普通用户都会
    失去刚上线的能力（默认策略只有 admin 通配，fail-closed 对他们是全拒）。
    管理员配置过一次之后，行为就与 ``require_feature`` 完全一致。
    """
    from app.services.permission_service import get_permission_service

    def _dependency(
        user: UserModel = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> UserModel:
        service = get_permission_service()
        if service.feature_unconfigured(feature):
            return user
        if not service.enforce_for_user(user, action, "feature", feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: feature:{feature} ({action})",
            )
        return user

    return _dependency


def require_permission(
    action: str,
    resource_type: str,
    resolver: Callable[[Request], Any] | None = None,
):
    """按 Casbin 策略鉴权的依赖工厂。

    Args:
        action: read / write / delete / admin
        resource_type: 资源类型（``kb`` / ``skill`` / ``agent_profile`` ...），与策略里的 obj 前缀一致
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
    permission_point: str | None = None,
):
    """知识库行级鉴权（M6-C）。

    行级过滤的唯一入口 —— 端点禁止各自手写判定。

    判定顺序：
      1. 显式授权（``kb_access_control`` 成员表 / Casbin 直接策略 ``kb:<id>``）；
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
    from app.services.knowledge.acl import explicit_role, is_kb_admin, load_grants, role_allows
    from app.services.knowledge.retrieval import can_view_knowledge_base

    kb = db.get(KnowledgeBaseModel, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    # 权限矩阵全局点：持有对应权限点的用户可操作任意知识库（管理员语义）。
    # 这是矩阵 UI 上 kb:edit/delete/upload/reindex/acl 开关真正生效的地方 ——
    # 不直接 require_perm（会挡住普通用户管理自己的库），而是作为行级判定的
    # 一条"全局放行"分支。
    if permission_point:
        from app.services.permission_checker import has_permission

        if has_permission(db, user, permission_point):
            return kb

    # 显式授权（kb_access_control 成员表 / Casbin 直接策略 / owner / 系统 admin）
    grants = load_grants(db, [kb.id]).get(kb.id, [])
    if role_allows(explicit_role(user, kb, grants), action):
        return kb

    if action == "read" and can_view_knowledge_base(
        kb, user_id=user.id, is_admin=is_kb_admin(user.role)
    ):
        return kb

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Permission denied: kb:{kb_id} ({action})",
    )


def filter_readable_kb_ids(db: Session, user: UserModel, kb_ids: list[int]) -> set[int]:
    """批量行级过滤：返回 ``kb_ids`` 中当前用户可读的知识库 id 集合。

    列表查询统一走这里，避免 N+1 地逐个 require_kb_access。
    授权来源与 ``require_kb_access`` 完全一致（成员表 + 策略表 + 可见性兜底），
    否则会出现「详情页能打开、列表里却不显示」。
    """
    from app.db.models import KnowledgeBaseModel
    from app.services.knowledge.acl import explicit_role, is_kb_admin, load_grants, role_allows
    from app.services.knowledge.retrieval import can_view_knowledge_base

    if not kb_ids:
        return set()
    if is_kb_admin(user.role):
        return set(kb_ids)

    kbs = db.query(KnowledgeBaseModel).filter(KnowledgeBaseModel.id.in_(kb_ids)).all()
    grants = load_grants(db, [kb.id for kb in kbs])
    allowed: set[int] = set()
    for kb in kbs:
        if role_allows(explicit_role(user, kb, grants.get(kb.id, [])), "read"):
            allowed.add(kb.id)
        elif can_view_knowledge_base(kb, user_id=user.id, is_admin=False):
            allowed.add(kb.id)
    return allowed
