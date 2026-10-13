"""部门树服务（M6-C）。

物化路径方案
------------
``DepartmentModel.path`` 存的是从根到自身的 id 串（``1`` / ``1/4`` / ``1/4/9``），
子树查询因此是一次 ``path LIKE '1/4/%'``，不需要递归 CTE：

- 创建：先 ``flush()`` 拿到自增 id，再用 ``父.path + '/' + id`` 组装；
- 移动：只改被移动节点与它的子树（用旧前缀/新前缀做字符串替换），单次 UPDATE 批量完成；
- 删除：软删除（``is_active=False``），并把挂在子树上的用户的 ``department_id`` 置空
  —— 硬删会撞上 ``users.department_id`` 外键，且会静默改变一批人的可见域。

Casbin 侧的联动
--------------
``g, user:<id>, dept_admin, dept:<id>`` 这条角色绑定由本服务维护：
用户换部门时先删旧绑定再加新绑定，否则离职/调岗会残留旧部门的 dept_admin 权限。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.timezone import app_now
from app.db.models import DepartmentModel, UserModel

logger = logging.getLogger(__name__)

PATH_SEPARATOR = "/"


class DepartmentError(ValueError):
    """部门树操作非法（重名、成环、父节点不存在等）。"""


def department_domain(department_id: int) -> str:
    """部门对应的 Casbin 域标识（与 permission_service 的实现保持一致）。"""
    from app.services.permission_service import department_domain_for_user

    return department_domain_for_user(department_id)


# ---------------------------------------------------------------------------
# 路径维护
# ---------------------------------------------------------------------------


def build_path(parent: DepartmentModel | None, node_id: int) -> str:
    if parent is None:
        return str(node_id)
    return f"{parent.path}{PATH_SEPARATOR}{node_id}"


def _rebuild_subtree_paths(db: Session, node: DepartmentModel, new_path: str) -> int:
    """把 node 的整棵子树的 path 前缀替换为 new_path，返回受影响节点数。"""
    if node.path == new_path:
        return 0
    old_prefix = node.path
    affected = 0
    for descendant in db.scalars(
        select(DepartmentModel).where(
            DepartmentModel.path.startswith(old_prefix + PATH_SEPARATOR)
        )
    ).all():
        descendant.path = new_path + descendant.path[len(old_prefix):]
        affected += 1
    node.path = new_path
    return affected + 1


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def get_department(db: Session, department_id: int) -> DepartmentModel | None:
    return db.get(DepartmentModel, department_id)


def get_department_by_name(db: Session, name: str, parent_id: int | None = None) -> DepartmentModel | None:
    return db.scalar(
        select(DepartmentModel).where(
            DepartmentModel.name == name,
            DepartmentModel.parent_id.is_(parent_id) if parent_id is None else DepartmentModel.parent_id == parent_id,
        )
    )


def list_departments(db: Session, *, include_inactive: bool = False) -> list[DepartmentModel]:
    stmt = select(DepartmentModel)
    if not include_inactive:
        stmt = stmt.where(DepartmentModel.is_active.is_(True))
    return list(db.scalars(stmt.order_by(DepartmentModel.path)).all())


def build_tree(departments: list[DepartmentModel]) -> list[dict[str, Any]]:
    """把扁平列表组装成嵌套树（按 path 排序后逐层挂接）。"""
    nodes: dict[int, dict[str, Any]] = {}
    for dept in departments:
        nodes[dept.id] = {
            "id": dept.id,
            "name": dept.name,
            "path": dept.path,
            "parent_id": dept.parent_id,
            "ldap_dn": dept.ldap_dn,
            "description": dept.description,
            "is_active": dept.is_active,
            "children": [],
        }
    roots: list[dict[str, Any]] = []
    for dept in departments:
        node = nodes[dept.id]
        parent = nodes.get(dept.parent_id) if dept.parent_id is not None else None
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
    return roots


def create_department(
    db: Session,
    *,
    name: str,
    parent_id: int | None = None,
    description: str = "",
    ldap_dn: str | None = None,
) -> DepartmentModel:
    name = name.strip()
    if not name:
        raise DepartmentError("Department name is required")

    parent: DepartmentModel | None = None
    if parent_id is not None:
        parent = db.get(DepartmentModel, parent_id)
        if parent is None:
            raise DepartmentError(f"Parent department not found: {parent_id}")

    existing = db.scalar(
        select(DepartmentModel).where(
            DepartmentModel.name == name,
            DepartmentModel.parent_id == parent_id if parent_id is not None else DepartmentModel.parent_id.is_(None),
        )
    )
    if existing is not None:
        raise DepartmentError(f"Department already exists under the same parent: {name}")

    dept = DepartmentModel(
        name=name,
        parent_id=parent_id,
        path="",
        description=description,
        ldap_dn=ldap_dn,
        is_active=True,
    )
    db.add(dept)
    db.flush()  # 拿到自增 id 才能组装物化路径
    dept.path = build_path(parent, dept.id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def update_department(
    db: Session,
    dept: DepartmentModel,
    *,
    name: str | None = None,
    description: str | None = None,
    ldap_dn: str | None = None,
    is_active: bool | None = None,
) -> DepartmentModel:
    if name is not None:
        name = name.strip()
        if not name:
            raise DepartmentError("Department name is required")
        clash = db.scalar(
            select(DepartmentModel).where(
                DepartmentModel.name == name,
                DepartmentModel.id != dept.id,
                DepartmentModel.parent_id == dept.parent_id
                if dept.parent_id is not None
                else DepartmentModel.parent_id.is_(None),
            )
        )
        if clash is not None:
            raise DepartmentError(f"Department already exists under the same parent: {name}")
        dept.name = name
    if description is not None:
        dept.description = description
    if ldap_dn is not None:
        dept.ldap_dn = ldap_dn or None
    if is_active is not None:
        dept.is_active = is_active

    dept.updated_at = app_now()
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def move_department(db: Session, dept: DepartmentModel, new_parent_id: int | None) -> DepartmentModel:
    """移动部门节点并同步刷新整棵子树的物化路径。"""
    if new_parent_id is None:
        new_parent: DepartmentModel | None = None
    else:
        if new_parent_id == dept.id:
            raise DepartmentError("A department cannot be its own parent")
        new_parent = db.get(DepartmentModel, new_parent_id)
        if new_parent is None:
            raise DepartmentError(f"Parent department not found: {new_parent_id}")
        # 成环：新父节点必须位于自己子树之外
        if new_parent.path.startswith(dept.path + PATH_SEPARATOR):
            raise DepartmentError("Cannot move a department under its own descendant")

    new_path = build_path(new_parent, dept.id)
    dept.parent_id = new_parent_id
    _rebuild_subtree_paths(db, dept, new_path)
    dept.updated_at = app_now()
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


def delete_department(db: Session, dept: DepartmentModel) -> dict[str, int]:
    """软删除部门：子树一并停用，成员解绑（department_id 置空）。

    不用硬删：`users.department_id` 与 `departments.parent_id` 都指向本表，
    硬删会因外键约束失败，而且会让一批用户的 Casbin 域静默消失。
    """
    subtree_ids = [
        row[0]
        for row in db.execute(
            select(DepartmentModel.id).where(
                or_(
                    DepartmentModel.id == dept.id,
                    DepartmentModel.path.startswith(dept.path + PATH_SEPARATOR),
                )
            )
        ).all()
    ]
    if not subtree_ids:
        return {"deactivated": 0, "unlinked_users": 0}

    db.execute(
        update(DepartmentModel)
        .where(DepartmentModel.id.in_(subtree_ids))
        .values(is_active=False, updated_at=app_now())
    )
    unlinked = db.execute(
        update(UserModel).where(UserModel.department_id.in_(subtree_ids)).values(department_id=None)
    ).rowcount
    db.commit()
    return {"deactivated": len(subtree_ids), "unlinked_users": unlinked}


# ---------------------------------------------------------------------------
# 成员查询
# ---------------------------------------------------------------------------


def members_of_department(
    db: Session,
    department_id: int,
    *,
    include_subdepartments: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> list[UserModel]:
    """按部门查成员（默认含子部门，走物化路径）。"""
    dept = db.get(DepartmentModel, department_id)
    if dept is None:
        return []
    if include_subdepartments:
        condition = or_(
            UserModel.department_id == dept.id,
            UserModel.department_id.in_(
                select(DepartmentModel.id).where(
                    DepartmentModel.path.startswith(dept.path + PATH_SEPARATOR)
                )
            ),
        )
    else:
        condition = UserModel.department_id == dept.id
    return list(
        db.scalars(
            select(UserModel)
            .where(condition)
            .order_by(UserModel.created_at)
            .offset(offset)
            .limit(limit)
        ).all()
    )


def count_members(db: Session, department_id: int, *, include_subdepartments: bool = True) -> int:
    return len(members_of_department(db, department_id, include_subdepartments=include_subdepartments, limit=10_000))


def department_statistics(db: Session) -> list[dict[str, Any]]:
    """每个部门的直属成员数（管理页概览用）。"""
    rows = db.execute(
        select(UserModel.department_id, func.count(UserModel.id))
        .where(UserModel.department_id.is_not(None))
        .group_by(UserModel.department_id)
    ).all()
    counts = {row[0]: row[1] for row in rows}
    return [
        {
            "department_id": dept.id,
            "name": dept.name,
            "path": dept.path,
            "direct_members": counts.get(dept.id, 0),
        }
        for dept in list_departments(db)
    ]


# ---------------------------------------------------------------------------
# 成员挂接（含 Casbin 角色重绑）
# ---------------------------------------------------------------------------


def assign_user_department(db: Session, user: UserModel, department_id: int | None) -> UserModel:
    """把用户挂到新部门，并同步维护 Casbin 的 ``dept_admin`` 域绑定。

    旧域绑定必须先删：``g, user:5, dept_admin, dept:1`` 残留会让调岗后的人
    继续持有原部门的部门管理员权限。
    """
    from app.services.permission_service import (
        ROLE_DEPT_ADMIN,
        department_domain_for_user,
        get_permission_service,
        subject_for_user,
    )

    previous = user.department_id
    if previous is not None and department_id is not None and previous != department_id:
        service = get_permission_service()
        service.delete_role_for_user(
            subject_for_user(user), ROLE_DEPT_ADMIN, department_domain_for_user(previous)
        )

    user.department_id = department_id
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_dept_admin(db: Session, user: UserModel, enabled: bool) -> UserModel:
    """授予/撤销用户的本部门管理员角色。"""
    from app.services.permission_service import (
        ROLE_DEPT_ADMIN,
        department_domain_for_user,
        get_permission_service,
        subject_for_user,
    )

    if not user.department_id:
        raise DepartmentError("User has no department; cannot grant dept_admin")

    service = get_permission_service()
    domain = department_domain_for_user(user.department_id)
    if enabled:
        service.add_role_for_user(subject_for_user(user), ROLE_DEPT_ADMIN, domain)
    else:
        service.delete_role_for_user(subject_for_user(user), ROLE_DEPT_ADMIN, domain)
    return user
