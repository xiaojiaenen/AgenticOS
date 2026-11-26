"""企业权限体系管理端点。

挂载三条管理面：

- ``/roles``        自定义角色 CRUD
- ``/permissions``  Casbin 策略（p）与角色绑定（g）的读写
- ``/audit-logs``   审计日志查询

鉴权：管理面统一 ``require_admin``。

> 部门（departments）已整体下线：权限只按「用户 → 角色 → 策略」组织，
> 不再有部门树、部门域与 dept_admin 角色。知识库的授权同样落在全局域，
> 由库 owner 与 ``p, user:<id>, *, kb:<id>, <act>`` 直接授权表达。

审计：所有写操作在端点内显式调用 ``audit_service.record``（不引中间件）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_perm
from app.db.models import RoleModel, UserModel
from app.schemas.base import AppBaseModel
from app.services import audit_service
from app.services.permission_service import GLOBAL_DOMAIN

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Permissions"])


def _audit(db: Session, request: Request | None, *, action: str, actor: UserModel | None, **fields) -> None:
    ctx = audit_service.request_context(request)
    try:
        audit_service.record(db, action=action, actor=actor, ip=ctx["ip"], user_agent=ctx["user_agent"], **fields)
    except Exception:  # noqa: BLE001 -- 审计异常不得让管理操作失败
        logger.warning("audit %s failed", action, exc_info=True)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    slug: str = Field(..., min_length=1, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    description: str = ""


class RoleResponse(AppBaseModel):
    id: int
    name: str
    slug: str
    description: str
    is_builtin: bool
    is_active: bool
    created_at: datetime


class PolicyRequest(BaseModel):
    """一条 Casbin 策略。``ptype='p'`` 为权限，``'g'`` 为角色绑定。"""

    ptype: str = Field(default="p", pattern="^[pg]$")
    sub: str = Field(..., min_length=1, max_length=256)
    dom: str = Field(default="*", max_length=256)
    obj: str = Field(default="*", max_length=256)
    act: str = Field(default="read", max_length=64)


class PolicyResponse(BaseModel):
    ptype: str
    sub: str
    dom: str
    obj: str
    act: str


class AuditLogResponse(AppBaseModel):
    id: int
    actor_id: Optional[int]
    actor_email: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    result: str
    ip: Optional[str]
    user_agent: Optional[str]
    detail: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int



# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(db: Session = Depends(get_db), _: UserModel = Depends(require_perm("role:manage"))):
    return db.scalars(select(RoleModel).order_by(RoleModel.is_builtin.desc(), RoleModel.slug)).all()


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    if db.scalar(select(RoleModel).where(RoleModel.slug == payload.slug)) is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role slug already exists")
    role = RoleModel(
        name=payload.name.strip(),
        slug=payload.slug,
        description=payload.description,
        is_builtin=False,
        is_active=True,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    _audit(
        db, request, action="role.create", actor=current_user,
        resource_type="role", resource_id=role.id, detail={"slug": role.slug},
    )
    return role


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    role = db.get(RoleModel, role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_builtin:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Built-in roles cannot be deleted")

    from app.services.permission_service import get_permission_service

    service = get_permission_service()
    policies_removed = service.remove_filtered_policy(0, role.slug)
    bindings_removed = service.remove_filtered_grouping_policy(1, role.slug)
    db.delete(role)
    db.commit()
    _audit(
        db, request, action="role.delete", actor=current_user,
        resource_type="role", resource_id=role_id,
        detail={
            "slug": role.slug,
            "policies_removed": policies_removed,
            "bindings_removed": bindings_removed,
        },
    )
    return {"ok": True, "policies_removed": policies_removed, "bindings_removed": bindings_removed}


# ---------------------------------------------------------------------------
# Casbin policies
# ---------------------------------------------------------------------------


@router.get("/permissions/policies", response_model=list[PolicyResponse])
def list_policies(
    ptype: str = Query(default="p", pattern="^[pg]$"),
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    from app.services.permission_service import get_permission_service

    service = get_permission_service()
    if ptype == "g":
        # 与写接口保持同一套字段语义：sub=用户标识，obj=角色，dom=域。
        # 旧实现把角色写进了"-"，前端拿到后无法回传删除（DELETE 走 obj=角色）。
        return [
            PolicyResponse(
                ptype="g",
                sub=rule[0],
                dom=rule[2] if len(rule) > 2 else "*",
                obj=rule[1],
                act="-",
            )
            for rule in service.get_grouping_policy()
        ]
    return [PolicyResponse(ptype="p", sub=r[0], dom=r[1], obj=r[2], act=r[3]) for r in service.get_policy()]


@router.post("/permissions/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    from app.services.permission_service import get_permission_service

    service = get_permission_service()
    params = (
        (payload.sub, payload.dom, payload.obj, payload.act)
        if payload.ptype == "p"
        else (payload.sub, payload.obj, payload.dom)  # g: sub, role, domain
    )
    added = service.add_named_policy(payload.ptype, *params)
    if not added:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Policy already exists")
    _audit(
        db, request, action="permission.grant", actor=current_user,
        resource_type="policy", resource_id=payload.sub, detail=payload.model_dump(),
    )
    return PolicyResponse(ptype=payload.ptype, sub=payload.sub, dom=payload.dom, obj=payload.obj, act=payload.act)


@router.delete("/permissions/policies")
def delete_policy(
    payload: PolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    from app.services.permission_service import get_permission_service

    service = get_permission_service()
    params = (
        (payload.sub, payload.dom, payload.obj, payload.act)
        if payload.ptype == "p"
        else (payload.sub, payload.obj, payload.dom)
    )
    removed = service.remove_named_policy(payload.ptype, *params)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    _audit(
        db, request, action="permission.revoke", actor=current_user,
        resource_type="policy", resource_id=payload.sub, detail=payload.model_dump(),
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# 授权目录：把「资源 / 动作 / 主体」变成可选项
# ---------------------------------------------------------------------------


class GrantableResource(BaseModel):
    """一条可授权的对象。

    ``obj`` 就是策略里该填的值。``kind`` 区分两类：

    - ``feature``：功能级（``feature:build_website``）—— 授权说的是「能用这个
      功能」，而不是「能操作某个资源实例」。这是推荐的授权粒度；
    - ``resource``：实例级（``kb:12``）—— 仅用于需要逐条控制的场景（某个知识库
      只给某个角色看）。
    """

    obj: str
    label: str
    kind: str
    resource_type: str
    resource_id: str
    description: str = ""


class SubjectOption(BaseModel):
    """可被授权的主体。``sub`` 就是策略里该填的值。"""

    sub: str
    label: str
    kind: str  # role | user
    description: str = ""


class PermissionCatalog(BaseModel):
    """策略编辑器需要的全部选项。

    为什么要这个接口：策略里的 ``sub`` / ``obj`` 是 Casbin 的内部标识
    （``feature:build_website``、``user:3``、角色 slug），让管理员手写这些
    字符串等于要求他记住数据库主键。这里把它们翻成「功能名 / 用户邮箱」，
    前端只做选择。
    """

    resource_types: list[dict[str, str]]
    actions: list[dict[str, str]]
    subjects: list[SubjectOption]
    resources: list[GrantableResource]
    domain: str


# 功能级授权项：以「能做什么」为单位，而不是「哪个对象」。
#
# 这是本系统推荐的授权粒度 —— 管理员想表达的是「这个角色能构建网站」，
# 而不是「这个角色能操作 skill:1」。后者既难理解，也会在新增一个技能时
# 需要重新授权一次。
FEATURE_GRANTS: tuple[tuple[str, str, str], ...] = (
    ("build_website", "构建网站（npm install + build）", "网站智能体的构建能力"),
    ("deploy_website", "部署网站（需审批）", "把构建产物发布到 nginx"),
    ("manage_skills", "管理技能", "新建 / 编辑 / 删除技能"),
    ("run_skill", "运行技能脚本", "执行 Skill 里的 Python 脚本"),
    ("manage_knowledge", "管理知识库", "创建 / 编辑知识库与文档"),
    ("read_knowledge", "读取知识库", "检索与阅读知识库内容"),
    ("manage_agents", "管理智能体", "创建 / 编辑智能体配置"),
    ("use_agents", "使用智能体", "在对话里选用智能体"),
    ("manage_users", "管理用户", "创建 / 停用 / 删除用户"),
    ("manage_providers", "管理 AI 提供商", "配置大模型后端与 Key"),
    ("manage_integrations", "管理第三方集成", "配置外部系统与 API"),
    ("manage_mcp", "管理 MCP 服务器", "注册 / 连接 MCP 服务"),
    ("view_audit", "查看审计日志", "查询权限与操作审计"),
)


@router.get("/permissions/catalog", response_model=PermissionCatalog)
def get_permission_catalog(
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    """列出策略编辑器可选的授权项、动作、主体与实例资源。"""
    from app.db.models import KnowledgeBaseModel
    from app.services.permission_service import GLOBAL_DOMAIN

    roles = db.scalars(select(RoleModel).order_by(RoleModel.is_builtin.desc(), RoleModel.slug)).all()
    users = db.scalars(select(UserModel).order_by(UserModel.id).limit(500)).all()

    subjects: list[SubjectOption] = [
        SubjectOption(
            sub=role.slug,
            label=f"{role.name}（角色）",
            kind="role",
            description=role.description or "",
        )
        for role in roles
    ]
    subjects.extend(
        SubjectOption(
            sub=f"user:{user.id}",
            label=f"{user.email}（用户）",
            kind="user",
            description=f"#{user.id} · {user.role}",
        )
        for user in users
    )

    resources: list[GrantableResource] = [
        GrantableResource(
            obj="*",
            label="全部功能（通配）",
            kind="feature",
            resource_type="*",
            resource_id="*",
            description="仅建议给 admin 类角色",
        )
    ]
    for key, label, description in FEATURE_GRANTS:
        resources.append(
            GrantableResource(
                obj=f"feature:{key}",
                label=label,
                kind="feature",
                resource_type="feature",
                resource_id=key,
                description=description,
            )
        )
    # 实例级：只在需要逐条控制时用（例如某个知识库只开放给一个角色）
    for kb in db.scalars(select(KnowledgeBaseModel).order_by(KnowledgeBaseModel.id)).all():
        resources.append(
            GrantableResource(
                obj=f"kb:{kb.id}",
                label=f"知识库：{kb.name}",
                kind="resource",
                resource_type="kb",
                resource_id=str(kb.id),
                description=kb.description or "实例级授权（逐条控制）",
            )
        )

    return PermissionCatalog(
        resource_types=[
            {"value": "feature", "label": "功能（推荐）"},
            {"value": "kb", "label": "知识库实例"},
            {"value": "skill", "label": "技能实例"},
            {"value": "agent_profile", "label": "智能体实例"},
            {"value": "*", "label": "全部"},
        ],
        actions=[
            {"value": "read", "label": "读取 / 使用"},
            {"value": "write", "label": "创建 / 修改"},
            {"value": "delete", "label": "删除"},
            {"value": "admin", "label": "管理（含授权）"},
            {"value": "*", "label": "全部动作"},
        ],
        subjects=subjects,
        resources=resources,
        domain=GLOBAL_DOMAIN,
    )


@router.get("/permissions/roles/{user_id}")
def get_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    from app.services.permission_service import (
        get_permission_service,
        subject_for_user,
    )

    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    service = get_permission_service()
    subject = subject_for_user(user)
    domain = GLOBAL_DOMAIN
    return {
        "user_id": user.id,
        "subject": subject,
        "domain": domain,
        "roles": sorted(
            set(service.get_roles_for_user(subject, domain)) | set(service.get_roles_for_user(subject, GLOBAL_DOMAIN))
        ),
        "app_role": user.role,
    }


# ---------------------------------------------------------------------------
# Audit logs
# ---------------------------------------------------------------------------


@router.get("/audit-logs", response_model=AuditLogPage)
def list_audit_logs(
    actor_id: Optional[int] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    result: Optional[str] = Query(default=None, pattern="^(allow|deny|error)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    rows, total = audit_service.query_logs(
        db,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        limit=limit,
        offset=offset,
    )
    return AuditLogPage(
        items=[
            AuditLogResponse(
                id=row.id,
                actor_id=row.actor_id,
                actor_email=row.actor_email,
                action=row.action,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                result=row.result,
                ip=row.ip,
                user_agent=row.user_agent,
                detail=json.loads(row.detail_json or "{}"),
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
    )


@router.post("/audit-logs/purge")
def purge_audit_logs_endpoint(
    request: Request,
    retention_days: int = Query(default=audit_service.RETENTION_DAYS, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    deleted = audit_service.purge_older_than(db, retention_days)
    _audit(
        db, request, action="audit.purge", actor=current_user,
        resource_type="audit_logs", detail={"retention_days": retention_days, "deleted": deleted},
    )
    return {"deleted": deleted, "retention_days": retention_days}


# ---------------------------------------------------------------------------
# 权限矩阵（细粒度权限点 + 角色配置 + 用户多角色）
# ---------------------------------------------------------------------------


class RolePermissionsUpdate(BaseModel):
    permissions: list[str] = Field(default_factory=list, description="权限点 key 列表")


class UserRolesUpdate(BaseModel):
    roles: list[str] = Field(default_factory=list, description="额外角色 slug 列表（不含主角色）")


def _assert_not_self(actor: UserModel, target_id: int, *, what: str) -> None:
    """禁止管理员改自己的角色 / 权限点。

    与 ``users.py`` 的「不能改自己的角色」同一口径：否则拿到 ``role:manage``
    的人可以给自己加超管角色或给自己松绑权限点，绕过审计与权限边界。
    """
    if actor.id == target_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不能修改自己的{what}",
        )


def _assert_permissions_within_actor(db: Session, actor: UserModel, permissions: frozenset[str]) -> None:
    """目标权限点不得超出操作者自身的权限档位（``target_caps <= actor_caps``）。

    权限点按 ``permission_catalog`` 的分组映射到 capability；目标点集合展开出的
    capability 若是操作者当前不具备的（例如 admin 授出仅 superadmin 才有的
    ``system:dangerous`` / ``conversation:read_any``），即为提权，拒绝。

    操作者权限取**当前生效的权限点**（矩阵自定义后的结果，含多角色并集），
    而不是只看主角色 —— 这样内置角色被矩阵收紧后不会反过来放大可授范围。
    """
    from app.core.permission_catalog import PERMISSION_POINTS
    from app.services.permission_checker import capabilities_for_user

    cap_by_point = {p.key: p.group for p in PERMISSION_POINTS}
    target_caps = {cap_by_point[p] for p in permissions if p in cap_by_point}
    actor_caps = set(capabilities_for_user(db, actor))
    extra = target_caps - actor_caps
    if extra:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"不能授予超出自己权限档位的权限（多出：{'、'.join(sorted(extra))}）",
        )


def _assert_roles_within_actor(db: Session, actor: UserModel, role_slugs: list[str]) -> None:
    """目标角色（主/额外）的权限点不得超出操作者自身权限档位。

    角色可能已被矩阵自定义，所以按角色的**当前生效权限点**判定，与
    ``_assert_permissions_within_actor`` 共用同一套能力比对。
    """
    from app.services.permission_checker import role_permissions

    for slug in role_slugs:
        _assert_permissions_within_actor(db, actor, role_permissions(db, slug))


@router.get("/permission-matrix/catalog")
def get_permission_matrix_catalog(
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    """权限点目录（分组 + 权限点），矩阵 UI 的左侧结构。"""
    from app.core.permission_catalog import catalog_payload

    return catalog_payload()


@router.get("/permission-matrix/roles")
def get_permission_matrix_roles(
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    """所有角色及其权限点（矩阵数据）。

    返回每项含 role 元信息 + permissions（当前生效的权限点）+ customized
    （是否管理员自定义过）。内置角色未自定义时展示默认展开。
    """
    from app.core.permission_catalog import default_permissions_for_role
    from app.core.roles import ROLE_META
    from app.services.permission_checker import _permissions_from_json

    result = []
    for meta in ROLE_META:
        slug = meta["value"]
        role = db.scalar(select(RoleModel).where(RoleModel.slug == slug))
        custom = _permissions_from_json(role.permissions_json) if role else None
        perms = custom if custom is not None else default_permissions_for_role(slug)
        result.append({
            **meta,
            "is_builtin": True,
            "permissions": sorted(perms),
            "customized": custom is not None,
        })
    # 自定义角色（RoleModel 里非内置）
    for role in db.scalars(select(RoleModel).where(RoleModel.is_builtin.is_(False)).order_by(RoleModel.slug)).all():
        custom = _permissions_from_json(role.permissions_json)
        perms = custom if custom is not None else frozenset()
        result.append({
            "value": role.slug,
            "label": role.name,
            "hint": role.description or "自定义角色",
            "is_builtin": False,
            "permissions": sorted(perms),
            "customized": custom is not None,
        })
    return {"roles": result}


@router.put("/permission-matrix/roles/{slug}")
def update_role_permissions(
    slug: str,
    payload: RolePermissionsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    """更新一个角色的权限点（矩阵打勾）。权限点 key 自动过滤非法值。"""
    from app.core.permission_catalog import normalize_permissions
    from app.core.roles import normalize_role
    from app.services.permission_checker import clear_role_permission_cache

    slug = normalize_role(slug)
    role = db.scalar(select(RoleModel).where(RoleModel.slug == slug))
    if role is None:
        # 内置角色若还没有 RoleModel 行，为它建一条（幂等）
        from app.core.roles import ROLE_META

        meta = next((m for m in ROLE_META if m["value"] == slug), None)
        if meta is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="角色不存在")
        role = RoleModel(
            name=meta["label"], slug=slug, description=meta["hint"],
            is_builtin=True, is_active=True,
        )
        db.add(role)
        db.flush()

    perms = normalize_permissions(payload.permissions)
    # 越权保护：不能把一个角色配出操作者自己都不具备的权限档位。
    # 例：admin 没有 system:dangerous / conversation:read_any，就不能给任何
    # 角色勾上这两个分组下的权限点（否则可借角色把自己或他人提成超管）。
    _assert_permissions_within_actor(db, current_user, perms)
    role.permissions_json = json.dumps(sorted(perms))
    db.commit()
    clear_role_permission_cache()
    _audit(
        db, request, action="permission.role_permissions.update", actor=current_user,
        resource_type="role", resource_id=slug, detail={"permissions": sorted(perms)},
    )
    return {"role": slug, "permissions": sorted(perms)}


@router.post("/permission-matrix/roles/{slug}/reset")
def reset_role_permissions(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    """恢复角色的默认权限（清空自定义矩阵，回到内置角色展开）。"""
    from app.core.roles import normalize_role
    from app.core.permission_catalog import default_permissions_for_role
    from app.services.permission_checker import clear_role_permission_cache

    slug = normalize_role(slug)
    perms = default_permissions_for_role(slug)
    # 与「设置权限点」同口径：恢复默认也不得把角色拉到操作者不具备的档位
    # （例如 admin 把 superadmin 角色重置回含高危点的默认展开）。
    _assert_permissions_within_actor(db, current_user, perms)
    role = db.scalar(select(RoleModel).where(RoleModel.slug == slug))
    if role is not None:
        role.permissions_json = None  # null = 用默认展开
        db.commit()
    clear_role_permission_cache()
    _audit(
        db, request, action="permission.role_permissions.reset", actor=current_user,
        resource_type="role", resource_id=slug,
    )
    return {"role": slug, "permissions": sorted(perms)}


@router.get("/permission-matrix/users/{user_id}/roles")
def get_matrix_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_perm("role:manage")),
):
    """用户的角色（主角色 + 额外角色）与生效权限点。"""
    from app.services.permission_checker import permissions_for_user, user_role_slugs

    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return {
        "user_id": user_id,
        "primary_role": user.role,
        "roles": user_role_slugs(db, user),
        "permissions": sorted(permissions_for_user(db, user)),
    }


@router.put("/permission-matrix/users/{user_id}/roles")
def set_matrix_user_roles(
    user_id: int,
    payload: UserRolesUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("role:manage")),
):
    """设置用户的额外角色（主角色不变）。role slug 白名单校验。"""
    from app.core.roles import VALID_ROLES, normalize_role
    from app.db.models import UserRoleModel

    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    # 不能改自己的角色（与 users.py:update_user 同一硬约束）：否则可给自己
    # 加一个超管额外角色完成自升权，绕开 users.py 的档位校验与审计。
    _assert_not_self(current_user, user_id, what="角色")
    slugs = []
    for raw in payload.roles:
        slug = normalize_role(raw)
        if slug not in VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"非法角色：{raw}")
        if slug not in slugs:
            slugs.append(slug)
    # 越权保护：不能给别人超出自己权限档位的角色/权限点。
    # 目标角色可能已被矩阵自定义，所以按生效权限点判定而非只看角色名。
    _assert_roles_within_actor(db, current_user, slugs)
    # 整组替换额外角色
    db.execute(delete(UserRoleModel).where(UserRoleModel.user_id == user_id))
    for slug in slugs:
        db.add(UserRoleModel(user_id=user_id, role_slug=slug))
    db.commit()
    _audit(
        db, request, action="permission.user_roles.update", actor=current_user,
        resource_type="user", resource_id=str(user_id), detail={"roles": slugs},
    )
    return {"user_id": user_id, "extra_roles": slugs}


@router.get("/permission-matrix/me")
def get_my_permissions(
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """当前用户生效的权限点（前端初始化 /auth/me 后可再拉一次）。"""
    from app.services.permission_checker import (
        capabilities_for_user, can_enter_admin_by_permissions, permissions_for_user,
    )

    perms = permissions_for_user(db, current_user)
    return {
        "permissions": sorted(perms),
        "capabilities": capabilities_for_user(db, current_user),
        "can_enter_admin": can_enter_admin_by_permissions(db, current_user),
    }
