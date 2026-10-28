"""知识库行级访问控制。

两类授权来源，判定时取"更高者"：

1. **``kb_access_control`` 表** —— 显式共享，管理员在「共享成员」里加人加角色
   （viewer / editor / admin）。这是产品语义上真正的「把这个库分享给某个人」。
2. **Casbin 直接策略** ``p, user:<id>, *, kb:<id>, <act>`` —— 创建者拿到的
   直接授权、以及历史上通过策略表发的授权。

为什么两个来源都要看：策略表是判定源（``require_kb_access`` 一直在用它），
``kb_access_control`` 是后加的、面向用户的共享表。只认其中一个，都会出现
「我已经被加进成员列表但检索不到」这类割裂感。

角色映射（Casbin 只有 act，没有角色概念，按能力反推）：

    delete 命中 → admin       （能删就能写能读）
    write  命中 → editor
    read   命中 → viewer

本模块只回答「显式授予了什么角色」，**不含** public/org 的可见性兜底 ——
那是 ``can_view_knowledge_base`` 的职责，两者在调用方组合使用。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import KBAccessControlModel, KnowledgeBaseModel, UserModel

logger = logging.getLogger("knowledge.acl")

ROLE_RANK: dict[str, int] = {"viewer": 1, "editor": 2, "admin": 3}
VALID_ROLES = tuple(ROLE_RANK)
# action → 允许该动作所需的最低角色
ACTION_MIN_ROLE: dict[str, str] = {
    "read": "viewer",
    "write": "editor",
    "delete": "admin",
}


@dataclass(slots=True)
class KBGrant:
    """一条显式授权。"""

    principal_type: str
    principal_id: int
    role: str


def load_grants(db: Session, kb_ids: Sequence[int]) -> dict[int, list[KBGrant]]:
    """批量读取显式授权：{kb_id: [KBGrant, ...]}。"""
    if not kb_ids:
        return {}
    rows = db.execute(
        select(KBAccessControlModel).where(
            KBAccessControlModel.knowledge_base_id.in_(list(kb_ids))
        )
    ).scalars().all()

    result: dict[int, list[KBGrant]] = {}
    for row in rows:
        result.setdefault(row.knowledge_base_id, []).append(
            KBGrant(
                principal_type=row.principal_type,
                principal_id=row.principal_id,
                role=row.role,
            )
        )
    return result


def grants_role_for_user(grants: Iterable[KBGrant], user_id: int | None) -> str | None:
    """从授权列表里取该用户的最高角色（仅 user 主体；team 主体当前无消费方）。"""
    if user_id is None:
        return None
    best: str | None = None
    for grant in grants:
        if grant.principal_type != "user" or grant.principal_id != user_id:
            continue
        if grant.role not in ROLE_RANK:
            continue
        if best is None or ROLE_RANK[grant.role] > ROLE_RANK[best]:
            best = grant.role
    return best


def role_allows(role: str | None, action: str) -> bool:
    """该角色是否允许执行 action。"""
    if role is None:
        return False
    required = ACTION_MIN_ROLE.get(action, "admin")
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(required, 99)


def casbin_role_for_kb(user: UserModel, kb: KnowledgeBaseModel) -> str | None:
    """把 Casbin 的 act 能力反推成角色。策略表不可用时返回 None（不阻断）。"""
    try:
        from app.services.permission_service import (
            get_permission_service,
            knowledge_base_domains,
        )

        service = get_permission_service()
        domains = knowledge_base_domains(kb)
        for action, role in (("delete", "admin"), ("write", "editor"), ("read", "viewer")):
            if service.enforce_for_user(user, action, "kb", kb.id, domains=domains):
                return role
    except Exception as exc:  # noqa: BLE001 —— 策略引擎异常不得让检索整体失败
        logger.warning("Casbin 判定失败 kb=%s: %s", kb.id, exc)
    return None


def explicit_role(
    user: UserModel,
    kb: KnowledgeBaseModel,
    grants: Sequence[KBGrant] = (),
) -> str | None:
    """该用户对知识库的显式角色（owner/admin 视为 admin；无授权返回 None）。"""
    if user.role == "admin":
        return "admin"
    if kb.owner_id is not None and kb.owner_id == user.id:
        return "admin"
    from_table = grants_role_for_user(grants, user.id)
    if from_table:
        return from_table
    return casbin_role_for_kb(user, kb)


# ---------------------------------------------------------------------------
# 管理面：读写共享成员
# ---------------------------------------------------------------------------


def list_grants(db: Session, kb_id: int) -> list[dict]:
    """列出知识库的共享成员（附用户信息，供管理界面展示）。"""
    rows = db.execute(
        select(KBAccessControlModel, UserModel)
        .join(UserModel, UserModel.id == KBAccessControlModel.principal_id, isouter=True)
        .where(
            KBAccessControlModel.knowledge_base_id == kb_id,
            KBAccessControlModel.principal_type == "user",
        )
        .order_by(KBAccessControlModel.id)
    ).all()

    items: list[dict] = []
    for grant, user in rows:
        items.append(
            {
                "id": grant.id,
                "principal_type": grant.principal_type,
                "principal_id": grant.principal_id,
                "role": grant.role,
                "email": user.email if user else None,
                "name": user.name if user else None,
                "granted_by": grant.granted_by,
                "created_at": grant.created_at,
            }
        )
    return items


def replace_grants(
    db: Session,
    kb_id: int,
    entries: Iterable[dict],
    *,
    granted_by: int,
) -> int:
    """整体替换知识库的共享成员（幂等：先清后写），返回写入条数。

    去重键是 (principal_type, principal_id)：同一人重复提交只保留最后一条，
    避免撞 ``uq_kb_access`` 唯一约束。不提交，由调用方控制事务。
    """
    normalized: dict[tuple[str, int], str] = {}
    for entry in entries:
        principal_type = str(entry.get("principal_type") or "user")
        if principal_type != "user":
            # team 主体对应的组织模型已下线，静默忽略而不是报错：
            # 前端旧数据里可能带着 team 条目
            continue
        try:
            principal_id = int(entry.get("principal_id"))
        except (TypeError, ValueError):
            continue
        role = str(entry.get("role") or "viewer")
        if role not in ROLE_RANK:
            continue
        normalized[(principal_type, principal_id)] = role

    db.execute(
        delete(KBAccessControlModel).where(
            KBAccessControlModel.knowledge_base_id == kb_id
        )
    )
    for (principal_type, principal_id), role in normalized.items():
        db.add(
            KBAccessControlModel(
                knowledge_base_id=kb_id,
                principal_type=principal_type,
                principal_id=principal_id,
                role=role,
                granted_by=granted_by,
            )
        )
    db.flush()
    return len(normalized)
