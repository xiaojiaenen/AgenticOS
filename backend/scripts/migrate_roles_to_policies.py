"""一次性迁移：把现有 users.role 映射成 Casbin 策略（M6-C）。

对应设计稿第六节风险 3 ——「Casbin 首次全量授权需要一次性数据迁移脚本」。

映射规则
--------
- ``role == 'admin'``  → ``g, user:<id>, admin, *``（全局域，不受部门影响）
- 其他                  → ``g, user:<id>, user, global``（普通用户基线角色）

用法（幂等，可重复执行）::

    cd backend
    uv run python scripts/migrate_roles_to_policies.py            # 全量
    uv run python scripts/migrate_roles_to_policies.py --dry-run  # 只报告不改库

幂等性来自两处：``add_named_policy`` / ``add_grouping_policy`` 在规则已存在时
返回 False 且不写库；``--prune``（默认开启）只删掉「角色已不属于该用户」的 g 规则，
不会误删管理员手工加的 p 规则。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db.models import UserModel  # noqa: E402
from app.db.session import create_db_session  # noqa: E402
from app.services.permission_service import (  # noqa: E402
    GLOBAL_DOMAIN,
    ROLE_ADMIN,
    ROLE_USER,
    ensure_default_policies,
    get_permission_service,
    subject_for_user,
)

logger = logging.getLogger("migrate_roles_to_policies")


def migrate(*, dry_run: bool = False, prune: bool = True) -> dict[str, int]:
    """执行映射，返回统计计数。"""
    stats = {"admins": 0, "users": 0, "linked": 0, "pruned": 0}

    if not dry_run:
        ensure_default_policies()
    service = get_permission_service()

    with create_db_session() as db:
        users = db.scalars(select(UserModel).order_by(UserModel.id)).all()
        expected: set[tuple[str, str, str]] = set()

        for user in users:
            subject = subject_for_user(user)
            if user.role == ROLE_ADMIN:
                rule = (subject, ROLE_ADMIN, "*")
                stats["admins"] += 1
            else:
                rule = (subject, ROLE_USER, GLOBAL_DOMAIN)
                stats["users"] += 1
            expected.add(rule)
            if not dry_run:
                service.add_named_policy("g", *rule)
            stats["linked"] += 1

        if prune and not dry_run:
            for rule in service.get_grouping_policy():
                triple = tuple(rule[:3])
                if len(triple) == 3 and triple[1] in {ROLE_ADMIN, ROLE_USER} and triple not in expected:
                    service.remove_named_policy("g", *triple)
                    stats["pruned"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate users.role into Casbin policies")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument(
        "--no-prune",
        dest="prune",
        action="store_false",
        help="保留多余的 g 规则（默认会清理 admin/user 的陈旧绑定）",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    stats = migrate(dry_run=args.dry_run, prune=args.prune)
    prefix = "[dry-run] " if args.dry_run else ""
    logger.info(
        "%sscanned=%d admins=%d users=%d linked=%d pruned=%d",
        prefix,
        stats["admins"] + stats["users"],
        stats["admins"],
        stats["users"],
        stats["linked"],
        stats["pruned"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
