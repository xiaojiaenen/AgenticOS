"""企业权限体系管理端点（M6-C）。

挂载四条管理面：

- ``/departments``  部门树 CRUD、成员查询、LDAP 全量同步
- ``/roles``        自定义角色 CRUD
- ``/permissions``  Casbin 策略（p）与角色绑定（g）的读写
- ``/audit-logs``   审计日志查询

鉴权：写操作统一 ``require_admin``（等价于「策略表里的 admin 角色」），
读操作 ``require_permission("read", ...)`，让部门管理员也能看到自己部门的授权情况。
审计：所有写操作在端点内显式调用 ``audit_service.record``（不引中间件）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.core.config import Settings, get_settings
from app.db.models import DepartmentModel, RoleModel, UserModel
from app.schemas.base import AppBaseModel
from app.services import audit_service
from app.services.department_service import (
    DepartmentError,
    assign_user_department,
    build_tree,
    count_members,
    create_department,
    delete_department,
    department_statistics,
    list_departments,
    members_of_department,
    move_department,
    set_dept_admin,
    update_department,
)

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


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    parent_id: Optional[int] = None
    description: str = ""
    ldap_dn: Optional[str] = Field(default=None, max_length=512)


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = None
    ldap_dn: Optional[str] = Field(default=None, max_length=512)
    is_active: Optional[bool] = None


class DepartmentMove(BaseModel):
    parent_id: Optional[int] = None


class DepartmentResponse(AppBaseModel):
    id: int
    name: str
    parent_id: Optional[int]
    path: str
    ldap_dn: Optional[str]
    description: str
    is_active: bool
    member_count: int = 0
    children: list["DepartmentResponse"] = Field(default_factory=list)


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


DepartmentResponse.model_rebuild()


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------


def _department_response(db: Session, dept: DepartmentModel) -> DepartmentResponse:
    """扁平节点（不带 children）——树形请用 ``/departments/tree``。"""
    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        parent_id=dept.parent_id,
        path=dept.path,
        ldap_dn=dept.ldap_dn,
        description=dept.description,
        is_active=dept.is_active,
        member_count=count_members(db, dept.id, include_subdepartments=False),
    )


@router.get("/departments", response_model=list[DepartmentResponse])
def list_department_nodes(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
):
    depts = list_departments(db, include_inactive=include_inactive)
    return [_department_response(db, dept) for dept in depts]


@router.get("/departments/tree")
def get_department_tree(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
):
    depts = list_departments(db, include_inactive=include_inactive)
    counts = {row["department_id"]: row["direct_members"] for row in department_statistics(db)}
    tree = build_tree(depts)
    _annotate_counts(tree, counts)
    return {"items": tree}


def _annotate_counts(nodes: list[dict[str, Any]], counts: dict[int, int]) -> None:
    for node in nodes:
        node["direct_members"] = counts.get(node["id"], 0)
        _annotate_counts(node["children"], counts)


@router.post("/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department_endpoint(
    payload: DepartmentCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    try:
        dept = create_department(
            db,
            name=payload.name,
            parent_id=payload.parent_id,
            description=payload.description,
            ldap_dn=payload.ldap_dn,
        )
    except DepartmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(
        db, request, action="department.create", actor=current_user,
        resource_type="department", resource_id=dept.id, detail={"name": dept.name, "path": dept.path},
    )
    return _department_response(db, dept)


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
def update_department_endpoint(
    department_id: int,
    payload: DepartmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    dept = db.get(DepartmentModel, department_id)
    if dept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    try:
        dept = update_department(
            db,
            dept,
            name=payload.name,
            description=payload.description,
            ldap_dn=payload.ldap_dn,
            is_active=payload.is_active,
        )
    except DepartmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(
        db, request, action="department.update", actor=current_user,
        resource_type="department", resource_id=dept.id, detail=payload.model_dump(exclude_none=True),
    )
    return _department_response(db, dept)


@router.post("/departments/{department_id}/move", response_model=DepartmentResponse)
def move_department_endpoint(
    department_id: int,
    payload: DepartmentMove,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    dept = db.get(DepartmentModel, department_id)
    if dept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    try:
        dept = move_department(db, dept, payload.parent_id)
    except DepartmentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _audit(
        db, request, action="department.move", actor=current_user,
        resource_type="department", resource_id=dept.id,
        detail={"new_parent_id": payload.parent_id, "path": dept.path},
    )
    return _department_response(db, dept)


@router.delete("/departments/{department_id}")
def delete_department_endpoint(
    department_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    dept = db.get(DepartmentModel, department_id)
    if dept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    stats = delete_department(db, dept)
    _audit(
        db, request, action="department.delete", actor=current_user,
        resource_type="department", resource_id=department_id, detail=stats,
    )
    return {"ok": True, **stats}


@router.get("/departments/{department_id}/members")
def list_department_members(
    department_id: int,
    include_subdepartments: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
):
    if db.get(DepartmentModel, department_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
    members = members_of_department(
        db, department_id, include_subdepartments=include_subdepartments, limit=limit, offset=offset
    )
    return {
        "items": [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role,
                "department_id": u.department_id,
                "is_active": u.is_active,
            }
            for u in members
        ],
        "total": count_members(db, department_id, include_subdepartments=include_subdepartments),
    }


class MemberAssign(BaseModel):
    user_id: int
    department_id: Optional[int] = None
    dept_admin: Optional[bool] = None


@router.post("/departments/{department_id}/members")
def assign_member(
    department_id: int,
    payload: MemberAssign,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    user = db.get(UserModel, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.department_id is not None and db.get(DepartmentModel, payload.department_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")

    user = assign_user_department(db, user, payload.department_id)
    if payload.dept_admin is not None:
        try:
            set_dept_admin(db, user, payload.dept_admin)
        except DepartmentError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _audit(
        db, request, action="department.assign_member", actor=current_user,
        resource_type="user", resource_id=user.id,
        detail={"department_id": payload.department_id, "dept_admin": payload.dept_admin},
    )
    return {"ok": True, "user_id": user.id, "department_id": user.department_id}


@router.post("/departments/ldap-sync")
async def ldap_sync_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
    settings: Settings = Depends(get_settings),
):
    """管理员触发的 LDAP 部门全量同步。

    只处理 ``auth_source='ldap'`` 的本地用户（本地账号没有工号，无从查目录）。
    使用服务账号仅搜索目录读取部门属性（不需要用户密码）。
    LDAP 未启用或未开启部门同步时直接 409，不产生任何网络调用。
    """
    import asyncio

    from app.services.ldap_auth_service import (
        LdapAuthError,
        apply_department,
        load_config,
        lookup_user,
    )

    config = load_config(db, settings)
    if not config.enabled or not config.department_sync:
        _audit(
            db, request, action="department.ldap_sync", actor=current_user,
            result="deny", detail={"reason": "ldap disabled or department_sync=false"},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LDAP 部门同步未启用，请先在系统设置中启用 LDAP 并开启部门同步",
        )

    users = db.scalars(select(UserModel).where(UserModel.auth_source == "ldap")).all()
    synced, skipped, missing = 0, 0, 0
    for user in users:
        username = user.email.split("@", 1)[0]
        try:
            ldap_user = await asyncio.to_thread(lookup_user, config, username)
        except LdapAuthError as e:  # noqa: BLE001 -- 单个用户失败不中断全量同步
            logger.warning("LDAP department sync failed for %s: %s", user.email, e)
            skipped += 1
            continue
        if ldap_user is None:
            missing += 1
            continue
        try:
            changed = apply_department(db, user, ldap_user.get("department_dn"), ldap_user.get("department_name"))
        except Exception:  # noqa: BLE001 -- 单个用户失败不中断全量同步
            logger.warning("department apply failed for %s", user.email, exc_info=True)
            skipped += 1
            continue
        synced += int(changed)
        skipped += int(not changed)

    _audit(
        db, request, action="department.ldap_sync", actor=current_user,
        resource_type="department",
        detail={"synced": synced, "unchanged": skipped, "missing_in_ldap": missing, "scanned": len(users)},
    )
    return {"scanned": len(users), "synced": synced, "unchanged": skipped, "missing_in_ldap": missing}


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(db: Session = Depends(get_db), _: UserModel = Depends(require_admin)):
    return db.scalars(select(RoleModel).order_by(RoleModel.is_builtin.desc(), RoleModel.slug)).all()


@router.post("/roles", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
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
    current_user: UserModel = Depends(require_admin),
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
    _: UserModel = Depends(require_admin),
):
    from app.services.permission_service import get_permission_service

    service = get_permission_service()
    if ptype == "g":
        return [
            PolicyResponse(ptype="g", sub=rule[0], dom=rule[2] if len(rule) > 2 else "*", obj="-", act="-")
            for rule in service.get_grouping_policy()
        ]
    return [PolicyResponse(ptype="p", sub=r[0], dom=r[1], obj=r[2], act=r[3]) for r in service.get_policy()]


@router.post("/permissions/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
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
    current_user: UserModel = Depends(require_admin),
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


@router.get("/permissions/roles/{user_id}")
def get_user_roles(
    user_id: int,
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
):
    from app.services.permission_service import (
        GLOBAL_DOMAIN,
        domain_for_user,
        get_permission_service,
        subject_for_user,
    )

    user = db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    service = get_permission_service()
    subject = subject_for_user(user)
    domain = domain_for_user(user)
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
    _: UserModel = Depends(require_admin),
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
    current_user: UserModel = Depends(require_admin),
):
    deleted = audit_service.purge_older_than(db, retention_days)
    _audit(
        db, request, action="audit.purge", actor=current_user,
        resource_type="audit_logs", detail={"retention_days": retention_days, "deleted": deleted},
    )
    return {"deleted": deleted, "retention_days": retention_days}
