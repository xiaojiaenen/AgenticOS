"""Casbin 权限服务（M6-C）。

设计要点见 ``app/resources/casbin_model.conf`` 与 ``docs/design/m6-design.md`` 第四节：

- **主体**统一为 ``user:<users.id>``，避免邮箱改名导致策略失联；
- **域**由 ``g`` 关系的域承载（``g, user:7, dept_admin, dept:2`` 只在本部门生效），
  因此 ``p`` 里的域可以统一写 ``*``，部门隔离靠角色归属实现；
- **策略存储**在 ``casbin_rule`` 表（v0..v5 / ptype）。这里自写一个
  ~40 行的 SQLAlchemy adapter（``SQLAlchemyAdapter``），不引入 casbin-sqlalchemy
  之类的额外适配器依赖 —— 我们只需要 5 个方法，且要复用项目自己的
  ``SessionLocal`` 与 ``AppDateTime`` 处理。

**单例与多进程一致性**：Casbin enforcer 是进程内策略缓存。多实例部署时
另一个进程改了策略，本进程最多滞后 ``POLICY_RELOAD_INTERVAL_SECONDS``
（默认 5s）才重新从库里加载；写操作由调用方显式调用
``get_permission_service().invalidate()`` 立即刷新本进程。
策略判定的量级很小（个人授权 + 部门角色），5s 延迟可接受。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import casbin
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import CasbinRuleModel, RoleModel, UserModel

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parents[1] / "resources" / "casbin_model.conf"

# 唯一授权域。部门下线后不再按组织隔离：所有策略与角色绑定都落在 global 域，
# 保留这个概念是因为 casbin model 的域参数还在（p/g 的第一/第三段）。
GLOBAL_DOMAIN = "global"
# 策略缓存的重新加载间隔（秒）—— 多实例部署下其他实例改策略的可见延迟上界
POLICY_RELOAD_INTERVAL_SECONDS = 5.0

ROLE_ADMIN = "admin"
ROLE_USER = "user"

BUILTIN_ROLES: tuple[tuple[str, str, str], ...] = (
    (ROLE_ADMIN, "系统管理员", "全权访问所有资源"),
    (ROLE_USER, "普通用户", "只能访问本人资源"),
)

# 内置策略。幂等写入（add_policy 内部按存在性去重）。
# 说明：
# - admin 的 obj/act 全是 ``*``（全权）；
# - 普通用户的「自身资源」由 PermissionService.enforce_for_user 里的 self-access
#   快捷判定承担（resource_type=user 且 resource_id 为本人时放行），不用一条
#   `p, user, *, user:*, read` 表达 —— 那会让 A 读到 B 的 user 资源。
# 元组含义为 (sub, dom, obj, act)，ptype 固定为 "p"。
DEFAULT_POLICIES: tuple[tuple[str, str, str, str], ...] = (
    (ROLE_ADMIN, "*", "*", "*"),
)

ACTION_DELETE = "delete"
ACTION_READ = "read"
ACTION_WRITE = "write"


def subject_for_user(user: UserModel | None) -> str:
    if user is None or user.id is None:
        return "anonymous"
    return f"user:{user.id}"


def domain_for_user(user: UserModel | None) -> str:
    """用户授权域：部门下线后恒为 global。"""
    return GLOBAL_DOMAIN


def domains_for_user(user: UserModel | None) -> list[str]:
    """用户判定的候选域（保留列表形态，兼容既有调用方）。"""
    return [GLOBAL_DOMAIN]


def build_object(resource_type: str, resource_id: Any = None) -> str:
    """把 (资源类型, 资源 id) 规范成 casbin 的 obj 串。"""
    if resource_id is None or resource_id == "":
        return resource_type
    return f"{resource_type}:{resource_id}"


def knowledge_base_domains(kb) -> list[str]:
    """知识库的授权域。

    部门下线后恒为 global：知识库的可读可写由「admin / 库 owner /
    ``p, user:<id>, *, kb:<id>, <act>`` 直接授权」三者决定，不再按组织归属隔离。
    ``kb.team_id`` 字段保留但不再参与鉴权（历史数据不动）。
    """
    return [GLOBAL_DOMAIN]


class SQLAlchemyAdapter(casbin.persist.Adapter):
    """casbin 持久化 adapter（只实现用到的 5 个方法）。

    必须继承 ``casbin.persist.Adapter``：pycasbin 的
    ``init_with_model_and_adapter`` 用 ``isinstance`` 校验 adapter 类型。
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # -- 读 ---------------------------------------------------------------
    def load_policy(self, model) -> None:
        with self._session_factory() as session:
            rows = session.execute(
                select(
                    CasbinRuleModel.ptype,
                    CasbinRuleModel.v0,
                    CasbinRuleModel.v1,
                    CasbinRuleModel.v2,
                    CasbinRuleModel.v3,
                    CasbinRuleModel.v4,
                    CasbinRuleModel.v5,
                )
            ).all()
        for ptype, v0, v1, v2, v3, v4, v5 in rows:
            rule = [value for value in (v0, v1, v2, v3, v4, v5) if value is not None]
            if not rule:
                continue
            model.add_policy("p" if ptype.startswith("p") else "g", ptype, rule)

    def load_filtered_policy(self, model, filter) -> None:  # pragma: no cover - 未使用过滤加载
        self.load_policy(model)

    # -- 写 ---------------------------------------------------------------
    def save_policy(self, model) -> None:
        with self._session_factory() as session:
            session.execute(delete(CasbinRuleModel))
            for ptype, rule in _iter_model_rules(model):
                session.add(_to_row(ptype, rule))
            session.commit()

    def add_policy(self, sec: str, ptype: str, rule: Sequence[str]) -> None:
        with self._session_factory() as session:
            session.add(_to_row(ptype, rule))
            session.commit()

    def remove_policy(self, sec: str, ptype: str, rule: Sequence[str]) -> None:
        with self._session_factory() as session:
            session.execute(delete(CasbinRuleModel).where(*_row_filters(ptype, rule)))
            session.commit()

    def remove_filtered_policy(self, sec: str, ptype: str, field_index: int, *field_values) -> None:
        columns = ["v0", "v1", "v2", "v3", "v4", "v5"]
        conditions = [CasbinRuleModel.ptype == ptype]
        for offset, value in enumerate(field_values):
            if value is None or value == "":
                continue
            idx = field_index + offset
            if idx >= len(columns):
                break
            conditions.append(getattr(CasbinRuleModel, columns[idx]) == value)
        with self._session_factory() as session:
            session.execute(delete(CasbinRuleModel).where(*conditions))
            session.commit()


def _to_row(ptype: str, rule: Sequence[str]) -> CasbinRuleModel:
    values = list(rule) + [None] * (6 - len(rule))
    return CasbinRuleModel(
        ptype=ptype,
        v0=str(values[0]) if values[0] is not None else None,
        v1=str(values[1]) if values[1] is not None else None,
        v2=str(values[2]) if values[2] is not None else None,
        v3=str(values[3]) if values[3] is not None else None,
        v4=str(values[4]) if values[4] is not None else None,
        v5=str(values[5]) if values[5] is not None else None,
    )


def _row_filters(ptype: str, rule: Sequence[str]):
    columns = ["v0", "v1", "v2", "v3", "v4", "v5"]
    conditions = [CasbinRuleModel.ptype == ptype]
    for idx, value in enumerate(rule[: len(columns)]):
        conditions.append(getattr(CasbinRuleModel, columns[idx]) == value)
    return tuple(conditions)


def _iter_model_rules(model) -> list[tuple[str, list[str]]]:
    rules: list[tuple[str, list[str]]] = []
    for sec in ("p", "g"):
        if sec not in model.model.keys():
            continue
        for ptype, ast in model.model[sec].items():
            for rule in ast.policy:
                rules.append((ptype, list(rule)))
    return rules


class PermissionService:
    """Casbin enforcer 的薄封装：单例加载 + 用户维度的判定入口。"""

    def __init__(self) -> None:
        from app.db.session import SessionLocal

        self._adapter = SQLAlchemyAdapter(SessionLocal)
        self._enforcer = casbin.Enforcer(str(MODEL_PATH), self._adapter)
        self._enforcer.enable_auto_save(True)
        self._loaded_at = time.monotonic()
        self._lock = threading.Lock()

    # -- 生命周期 ---------------------------------------------------------
    @property
    def enforcer(self) -> casbin.Enforcer:
        return self._enforcer

    def invalidate(self) -> None:
        """标记缓存过期；下一次判定前重新从数据库加载。"""
        self._loaded_at = 0.0

    def reload(self) -> None:
        with self._lock:
            self._enforcer.load_policy()
            self._loaded_at = time.monotonic()

    def _maybe_reload(self) -> None:
        if time.monotonic() - self._loaded_at > POLICY_RELOAD_INTERVAL_SECONDS:
            self.reload()

    # -- 判定 -------------------------------------------------------------
    def enforce(self, subject: str, domains: Sequence[str], obj: str, action: str) -> bool:
        self._maybe_reload()
        for domain in domains:
            try:
                if self._enforcer.enforce(subject, domain, obj, action):
                    return True
            except Exception:  # noqa: BLE001 -- 策略异常一律按拒绝处理，不放大故障
                logger.exception("casbin enforce failed: sub=%s dom=%s obj=%s act=%s", subject, domain, obj, action)
                return False
        return False

    def enforce_for_user(
        self,
        user: UserModel | None,
        action: str,
        resource_type: str,
        resource_id: Any = None,
        domains: Sequence[str] | None = None,
    ) -> bool:
        """用户维度的权限判定（deps.require_permission / require_kb_access 的唯一入口）。

        - admin 用户.role == "admin" 快速放行（与既有 require_admin 行为一致），
          即使策略表为空也不会把管理员锁在门外；
        - 「自身资源」：resource_type=user 且 resource_id 为本人时放行，
          对应设计稿里的 "user 自身资源"；
        - ``domains`` 缺省时用请求者自己的域（本部门域 + global）；
          **行级资源**（知识库）必须传入资源自己的域，见 ``knowledge_base_domains``；
        - 其余走 Casbin。
        """
        if user is None:
            return False
        if user.role == ROLE_ADMIN:
            return True
        if resource_type == "user" and str(resource_id) == str(user.id):
            return True
        return self.enforce(
            subject_for_user(user),
            list(domains) if domains is not None else domains_for_user(user),
            build_object(resource_type, resource_id),
            action,
        )

    # -- 策略维护 ---------------------------------------------------------
    def add_named_policy(self, ptype: str, *params: str) -> bool:
        """写一条规则（ptype 显式传入，"p" 为权限、"g" 为角色归属）。

        pycasbin 的 ``add_named_policy`` 内部写死了 sec="p"（KeyError: 'g'），
        所以 g 规则必须走 ``add_named_grouping_policy``。
        """
        if ptype.startswith("g"):
            added = self._enforcer.add_named_grouping_policy(ptype, *params)
        else:
            added = self._enforcer.add_named_policy(ptype, *params)
        self._loaded_at = time.monotonic()
        return added

    def remove_named_policy(self, ptype: str, *params: str) -> bool:
        if ptype.startswith("g"):
            removed = self._enforcer.remove_named_grouping_policy(ptype, *params)
        else:
            removed = self._enforcer.remove_named_policy(ptype, *params)
        self._loaded_at = time.monotonic()
        return removed

    def add_policy(self, *params: str) -> bool:
        return self.add_named_policy("p", *params)

    def remove_policy(self, *params: str) -> bool:
        return self.remove_named_policy("p", *params)

    def add_policies(self, rules: Sequence[Sequence[str]]) -> None:
        self._enforcer.add_policies(list(rules))
        self._loaded_at = time.monotonic()

    def remove_filtered_policy(self, field_index: int, *field_values) -> bool:
        removed = self._enforcer.remove_filtered_policy(field_index, *field_values)
        self._loaded_at = time.monotonic()
        return removed

    def remove_filtered_grouping_policy(self, field_index: int, *field_values) -> bool:
        removed = self._enforcer.remove_filtered_grouping_policy(field_index, *field_values)
        self._loaded_at = time.monotonic()
        return removed

    def get_policy(self) -> list[list[str]]:
        return [list(rule) for rule in self._enforcer.get_policy()]

    def get_named_policy(self, ptype: str) -> list[list[str]]:
        return [list(rule) for rule in self._enforcer.get_named_policy(ptype)]

    def get_grouping_policy(self) -> list[list[str]]:
        return [list(rule) for rule in self._enforcer.get_grouping_policy()]

    def get_roles_for_user(self, subject: str, domain: str = "*") -> list[str]:
        """主体的**直接**角色（不展开继承）。

        直接读 grouping policy 而不用 ``Enforcer.get_roles_for_user``：
        后者在省略 domain 参数时按空域查询，取不到 ``g, user:1, admin, *``
        这类全局域绑定，容易读出「明明授权了却查不到角色」的假象。
        """
        return [
            rule[1]
            for rule in self.get_grouping_policy()
            if len(rule) >= 2
            and rule[0] == subject
            and (domain == "*" or (len(rule) > 2 and rule[2] == domain))
        ]

    def add_role_for_user(self, user: str, role: str, domain: str = "*") -> bool:
        """授予角色（域感知）。

        pycasbin 的 ``Enforcer.add_role_for_user`` 只接受两段参数，域版本要走
        底层的 ``add_grouping_policy(user, role, domain)`` —— 后者同样会触发
        adapter 落库与 role link 重建。
        """
        added = self._enforcer.add_grouping_policy(user, role, domain)
        self._loaded_at = time.monotonic()
        return added

    def delete_role_for_user(self, user: str, role: str, domain: str = "*") -> bool:
        removed = self._enforcer.remove_grouping_policy(user, role, domain)
        self._loaded_at = time.monotonic()
        return removed

    # -- 引导 -------------------------------------------------------------
    def ensure_default_policies(self) -> None:
        """幂等写入内置策略与内置角色（可重复执行）。"""
        for sub, dom, obj, act in DEFAULT_POLICIES:
            self.add_policy(sub, dom, obj, act)
        seed_builtin_roles()


def seed_builtin_roles(session: Session | None = None) -> None:
    """把内置角色写进 ``roles`` 表（幂等 upsert）。"""
    from app.db.session import SessionLocal

    owns_session = session is None
    db = session or SessionLocal()
    try:
        for slug, name, description in BUILTIN_ROLES:
            existing = db.scalar(select(RoleModel).where(RoleModel.slug == slug))
            if existing is None:
                db.add(
                    RoleModel(
                        name=name,
                        slug=slug,
                        description=description,
                        is_builtin=True,
                        is_active=True,
                    )
                )
            else:
                existing.name = name
                existing.description = description
                existing.is_builtin = True
                existing.is_active = True
        db.commit()
    finally:
        if owns_session:
            db.close()


_service: PermissionService | None = None
_service_lock = threading.Lock()


def get_permission_service() -> PermissionService:
    """懒加载单例。首次调用会从 casbin_rule 加载全部策略。"""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = PermissionService()
    return _service


def reset_permission_service() -> None:
    """丢弃单例（测试用；下次访问重新从数据库加载）。"""
    global _service
    with _service_lock:
        _service = None


def ensure_default_policies() -> None:
    """应用启动时调用：幂等写入内置策略 + 内置角色。"""
    service = get_permission_service()
    for sub, dom, obj, act in DEFAULT_POLICIES:
        service.add_policy(sub, dom, obj, act)
    seed_builtin_roles()


def assign_default_role_for_user(user: UserModel) -> None:
    """新用户的默认角色绑定（幂等）。

    admin → ``g, user:N, admin, *``（全局域，不受部门影响）
    其他  → ``g, user:N, user, global``（普通用户基线角色）
    """
    service = get_permission_service()
    subject = subject_for_user(user)
    if user.role == ROLE_ADMIN:
        service.add_role_for_user(subject, ROLE_ADMIN, "*")
    else:
        service.add_role_for_user(subject, ROLE_USER, GLOBAL_DOMAIN)
