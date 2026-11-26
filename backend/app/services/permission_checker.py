"""统一权限判定（权限矩阵的唯一运行时入口）。

职责：
- 计算一个用户拥有的**全部权限点**（主角色 + 额外角色的并集）
- 角色权限以 RoleModel.permissions_json 为准（自定义矩阵）；未自定义则用
  permission_catalog 里内置角色的默认展开
- 提供 ``has_permission`` / ``permissions_for_user`` / ``can_enter_admin``
  —— 后端端点依赖与 /auth/me 下发都走这里，保证前后端口径一致

与旧体系的关系：
- ``app.core.roles`` 保留 capability 常量与内置角色映射（兼容 require_admin 等）
- 本模块是「细粒度权限点」层，能力 = 权限点分组；新增功能一律用权限点
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from sqlalchemy import select

from app.core.permission_catalog import (
    PERMISSION_KEYS, default_permissions_for_role, normalize_permissions,
    points_for_capability,
)
from app.core.roles import CAP_AGENT_USE, CAP_CONVERSATION_OWN, normalize_role

logger = logging.getLogger(__name__)


def _permissions_from_json(raw: str | None) -> frozenset[str] | None:
    """解析角色自定义权限点；null/非法 → None（表示用默认展开）。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, list):
        return None
    return normalize_permissions(str(x) for x in parsed)


@lru_cache(maxsize=256)
def _role_permissions_cached(role_slug: str, permissions_json: str | None) -> frozenset[str]:
    """单角色的权限点（优先自定义矩阵，否则内置默认）。带缓存，矩阵变更时清缓存。"""
    custom = _permissions_from_json(permissions_json)
    if custom is not None:
        return custom
    return default_permissions_for_role(role_slug)


def clear_role_permission_cache() -> None:
    """角色权限矩阵变更后调用。"""
    _role_permissions_cached.cache_clear()


def role_permissions(db, role_slug: str) -> frozenset[str]:
    """取一个角色的权限点集合（含自定义覆盖）。"""
    from app.db.models import RoleModel

    slug = normalize_role(role_slug)
    role = db.scalar(select(RoleModel).where(RoleModel.slug == slug, RoleModel.is_active.is_(True)))
    raw = role.permissions_json if role else None
    return _role_permissions_cached(slug, raw)


def user_role_slugs(db, user: Any) -> list[str]:
    """用户的全部角色 slug（主角色 + 额外角色，去重保序）。"""
    from app.db.models import UserRoleModel

    slugs: list[str] = []
    primary = normalize_role(getattr(user, "role", None))
    if primary:
        slugs.append(primary)
    if getattr(user, "id", None) is not None:
        extras = db.scalars(
            select(UserRoleModel.role_slug).where(UserRoleModel.user_id == user.id)
        ).all()
        for extra in extras:
            slug = normalize_role(extra)
            if slug and slug not in slugs:
                slugs.append(slug)
    return slugs


def permissions_for_user(db, user: Any) -> frozenset[str]:
    """用户的全部权限点（多角色并集）。"""
    perms: set[str] = set()
    for slug in user_role_slugs(db, user):
        perms |= role_permissions(db, slug)
    return frozenset(perms)


def has_permission(db, user: Any, permission: str) -> bool:
    """用户是否拥有某权限点。未知权限点 → False（fail-closed）。"""
    if permission not in PERMISSION_KEYS:
        return False
    return permission in permissions_for_user(db, user)


def can_enter_admin_by_permissions(db, user: Any) -> bool:
    """是否能进后台：拥有任一「非基础使用」分组的权限点。"""
    perms = permissions_for_user(db, user)
    basic = points_for_capability(CAP_AGENT_USE) | points_for_capability(CAP_CONVERSATION_OWN)
    return bool(perms - basic)


def capabilities_for_user(db, user: Any) -> list[str]:
    """从权限点反推 capability 列表（给前端兼容旧 capabilities 字段）。"""
    from app.core.permission_catalog import PERMISSION_POINTS

    perms = permissions_for_user(db, user)
    groups = {p.group for p in PERMISSION_POINTS if p.key in perms}
    return sorted(groups)
