"""应用平台服务：应用账号、应用级 token、实时角色、行级权限、记录 CRUD。

鉴权模型（设计文档 3.1，对齐 Supabase「两把钥匙 + 用户令牌」共识）：

- **应用 secret**（服务端用）：创建时生成 ``ak-agenticos-*``，只存 sha256，
  明文仅返回一次 —— 「绝不能进前端」的私密钥匙档；
- **用户令牌**：``POST /auth/login`` 换取，payload 只含 ``{app_id, user_id}``
  + 标准的 iat/exp（24h），**不含角色** —— 角色与归属每次请求从
  ``app_memberships`` 实时查（JWT claim 过期窗口会越权，Supabase 多租户
  指南明确警告过）；
- **行级权限**：manifest ``permissions`` 声明 + API 层判定。``owner`` 规则
  按记录归属者、``role:x`` 按 membership 角色、``*`` 通配；缺省的动作 =
  不授权（"只读数据"就是只声明 read）。列表查询在**查询层注入过滤条件**，
  不依赖用户代码自滤。

数据隔离（6.1 隔离档 C）：共享表 ``app_records`` + ``app_id``/``env``/``model``
三要素隔离；字段校验只在 API 层（本模块 ``validate_record_data``），平台
掌控唯一写入口。PG 部署时按 6.3 叠加 RLS policy 作双保险。
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.db.models import AppMembershipModel, AppModel, AppRecordModel, AppUserModel
from app.services.app_platform import manifest as manifest_module

logger = logging.getLogger("agenticos.app_platform")

#: 应用级 token 有效期（设计文档 3.1：默认 24h）
APP_TOKEN_EXPIRE_SECONDS = 24 * 3600
#: 应用 secret 前缀（提示调用方这是服务端密钥，对齐 api_keys 的 sk- 风格）
APP_SECRET_PREFIX = "ak-agenticos-"

ENVIRONMENTS = ("dev", "prod")
ACTIONS = ("read", "create", "update", "delete")
#: 列表查询硬上限（where 过滤/分页在 Python 侧做，防全表扫描失控；
#: JSONB 条件下推 + GIN 索引属 PG 部署时的优化项）
MAX_LIST_FETCH = 1000
MAX_LIST_LIMIT = 200


class AppPlatformError(Exception):
    """携带 HTTP 状态码的业务异常；端点层统一转 HTTPException。"""

    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


class AppNotFound(AppPlatformError):
    status_code = 404


class AppAuthError(AppPlatformError):
    status_code = 401


class AppForbidden(AppPlatformError):
    status_code = 403


def _hash_secret(raw_secret: str) -> str:
    return hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()


def _load_manifest(app: AppModel) -> dict[str, Any]:
    """解析生效 manifest；未部署/无 manifest 时抛 403（数据端点的前置检查）。"""
    if not app.manifest_json:
        raise AppForbidden("应用尚未部署（无生效 manifest）", status_code=403)
    try:
        return json.loads(app.manifest_json)
    except (TypeError, ValueError) as exc:
        raise AppForbidden("应用 manifest 损坏，请联系管理员", status_code=403) from exc


def _auth_mode(manifest: dict[str, Any]) -> str:
    auth = manifest.get("auth") or {}
    return auth.get("mode") if isinstance(auth, dict) else None


class AppPlatformService:
    """无状态服务；db 显式传参，方便测试直连会话。"""

    # ── 应用生命周期（管理端）─────────────────────────────────────────

    def create_app(
        self,
        db: Session,
        *,
        name: str,
        slug: str,
        owner_user_id: int | None = None,
    ) -> tuple[AppModel, str]:
        """创建应用并生成应用 secret；明文仅本次返回，库里只存 sha256。"""
        raw_secret = APP_SECRET_PREFIX + secrets.token_urlsafe(32)
        app = AppModel(
            name=(name or "").strip() or slug,
            slug=slug,
            status="draft",
            owner_user_id=owner_user_id,
            api_key_hash=_hash_secret(raw_secret),
        )
        db.add(app)
        db.commit()
        db.refresh(app)
        logger.info("app created slug=%s owner=%s", slug, owner_user_id)
        return app, raw_secret

    def submit_manifest(self, db: Session, app: AppModel, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        """提交新版本 manifest → 生成 plan，应用进入 pending（5.3 状态机）。

        校验不过不进审批队列（2.0：manifest 必过 JSON Schema 校验）。
        """
        errors = manifest_module.validate_manifest(manifest)
        if errors:
            raise AppPlatformError("manifest 校验失败: " + "; ".join(errors))
        current = json.loads(app.manifest_json) if app.manifest_json else None
        plan = manifest_module.generate_plan(current, manifest)
        app.pending_manifest_json = json.dumps(manifest, ensure_ascii=False)
        app.status = "pending"
        db.commit()
        return plan

    def approve_manifest(
        self,
        db: Session,
        app: AppModel,
        *,
        approved_paths: set[str] | None = None,
    ) -> tuple[AppModel, dict[str, Any]]:
        """批准 = apply：候选版本落为生效版本（管理员可逐项收紧，5.4）。"""
        if not app.pending_manifest_json:
            raise AppPlatformError("没有待审批的 manifest 版本")
        candidate = json.loads(app.pending_manifest_json)
        current = json.loads(app.manifest_json) if app.manifest_json else None
        effective = manifest_module.apply_plan(current, candidate, approved_paths=approved_paths)
        app.manifest_json = json.dumps(effective, ensure_ascii=False)
        app.pending_manifest_json = None
        app.status = "deployed"
        db.commit()
        db.refresh(app)
        return app, effective

    def reject_manifest(self, db: Session, app: AppModel) -> AppModel:
        """拒绝候选版本：应用回到部署前状态（重新提交走新版本）。"""
        if not app.pending_manifest_json:
            raise AppPlatformError("没有待审批的 manifest 版本")
        app.pending_manifest_json = None
        # 首次提交被拒 → 回 draft；已部署版本的增量被拒 → 保持 deployed
        app.status = "draft" if not app.manifest_json else "deployed"
        db.commit()
        db.refresh(app)
        return app

    # ── 应用账号与令牌 ────────────────────────────────────────────────

    def signup_app_user(
        self,
        db: Session,
        app: AppModel,
        *,
        email: str,
        password: str,
        display_name: str = "",
    ) -> tuple[AppUserModel, list[str]]:
        """注册应用终端用户（仅 manifest auth.allowSignup = true 时）。

        初始角色取 manifest.auth.roles 的第一个（viewer 优先）；角色随时可由
        membership 调整 —— 令牌里不写角色，改完立即生效。
        """
        manifest = _load_manifest(app)
        if manifest.get("auth", {}).get("mode") != "builtin":
            raise AppForbidden("该应用未启用平台托管登录")
        if not manifest.get("auth", {}).get("allowSignup"):
            raise AppForbidden("该应用未开放注册", status_code=403)

        email = (email or "").strip().lower()
        if not email or "@" not in email:
            raise AppPlatformError("邮箱格式不正确")
        if not password or len(password) < 8:
            raise AppPlatformError("密码长度至少 8 位")

        existing = db.scalar(select(AppUserModel).where(AppUserModel.app_id == app.id, AppUserModel.email == email))
        if existing is not None:
            raise AppPlatformError("该邮箱已注册", status_code=409)

        user = AppUserModel(
            app_id=app.id,
            email=email,
            password_hash=hash_password(password),
            display_name=(display_name or "").strip()[:120],
        )
        db.add(user)
        db.flush()  # 拿到自增 id 再建 membership
        roles = self.default_roles(manifest)
        db.add(AppMembershipModel(app_id=app.id, app_user_id=user.id, roles=roles))
        db.commit()
        db.refresh(user)
        return user, roles

    def authenticate_app_user(self, db: Session, app: AppModel, *, email: str, password: str) -> AppUserModel | None:
        """应用终端用户登录校验：邮箱 + 密码（Argon2id 双验）。"""
        email = (email or "").strip().lower()
        user = db.scalar(select(AppUserModel).where(AppUserModel.app_id == app.id, AppUserModel.email == email))
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def sign_app_token(self, app_id: str, user_id: int) -> str:
        """签发应用级用户令牌：payload 只有 app_id / user_id（+ iat/exp），24h。

        **不含角色** —— 角色从 membership 实时查（设计文档 3.1 关键点）。
        """
        return create_access_token(
            {"app_id": app_id, "user_id": user_id},
            secret=get_settings().auth_secret_key,
            expires_in_seconds=APP_TOKEN_EXPIRE_SECONDS,
        )

    def decode_app_token(self, token: str) -> dict[str, Any] | None:
        """校验并解码应用令牌；签名/过期/格式任何失败返回 None。"""
        payload = decode_access_token(token, secret=get_settings().auth_secret_key)
        if payload is None or not isinstance(payload.get("app_id"), str) or payload.get("user_id") is None:
            return None
        return payload

    def default_roles(self, manifest: dict[str, Any]) -> list[str]:
        """注册时的初始角色：viewer 优先，否则 manifest 声明的第一个角色。"""
        roles = [r for r in (manifest.get("auth", {}).get("roles") or []) if isinstance(r, str)]
        if "viewer" in roles:
            return ["viewer"]
        return roles[:1]

    def get_membership(self, db: Session, app_id: str, app_user_id: int) -> list[str]:
        """实时查角色 —— 行级权限的唯一角色来源，不信任任何 claim。"""
        row = db.scalar(
            select(AppMembershipModel).where(
                AppMembershipModel.app_id == app_id,
                AppMembershipModel.app_user_id == app_user_id,
            )
        )
        roles = row.roles if row is not None else None
        return [r for r in (roles or []) if isinstance(r, str)]

    def set_membership(self, db: Session, app: AppModel, app_user: AppUserModel, roles: list[str]) -> AppMembershipModel:
        """管理端设置角色（白名单：只能授予 manifest.auth.roles 声明过的角色）。"""
        manifest = _load_manifest(app)
        declared = set(manifest.get("auth", {}).get("roles") or [])
        clean = sorted({r for r in (roles or []) if isinstance(r, str) and r in declared})
        dropped = set(roles or []) - declared
        if dropped:
            raise AppPlatformError(f"未声明的角色: {sorted(dropped)}")
        row = db.scalar(
            select(AppMembershipModel).where(
                AppMembershipModel.app_id == app.id,
                AppMembershipModel.app_user_id == app_user.id,
            )
        )
        if row is None:
            row = AppMembershipModel(app_id=app.id, app_user_id=app_user.id, roles=clean)
            db.add(row)
        else:
            row.roles = clean
        db.commit()
        db.refresh(row)
        return row

    def resolve_principal(
        self,
        db: Session,
        app: AppModel,
        token: str | None,
        *,
        allow_anonymous: bool = False,
    ) -> dict[str, Any] | None:
        """解析请求主体（principal）。

        - 无令牌且应用为公开只读（auth.mode = none）→ 匿名主体（roles=[]）；
        - 令牌无效/过期 → 401；**令牌的 app_id 与路径应用不一致 → 403**
          （安全清单第一条：防跨应用越权，本场景令牌本身签名有效，是作用域错）；
        - 命中令牌后实时查 membership 得到角色。
        """
        if not token:
            if allow_anonymous and _auth_mode(_load_manifest(app)) == "none":
                return {"user_id": None, "email": None, "display_name": None, "roles": []}
            raise AppAuthError("缺少应用令牌")

        payload = self.decode_app_token(token)
        if payload is None:
            raise AppAuthError("应用令牌无效或已过期")
        if payload["app_id"] != app.id:
            # 令牌有效但属于另一个应用 —— 明确 403 而不是笼统 401
            raise AppForbidden("令牌与应用不匹配", status_code=403)

        user = db.scalar(
            select(AppUserModel).where(AppUserModel.id == int(payload["user_id"]), AppUserModel.app_id == app.id)
        )
        if user is None or not user.is_active:
            raise AppAuthError("应用账号不存在或已停用")

        return {
            "user_id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "roles": self.get_membership(db, app.id, user.id),
        }

    # ── 行级权限判定 ─────────────────────────────────────────────────

    @staticmethod
    def can(
        record_owner_id: str | None,
        model_perms: dict[str, Any] | None,
        action: str,
        user_id: int | None,
        membership_roles: list[str],
    ) -> bool:
        """行级权限判定（设计文档 3.2）。

        规则语义：``*`` 通配放行；``owner`` 记录归属者等于当前用户（create 时
        无记录可归属，不生效）；``role:x`` 命中 membership 角色。动作缺省 =
        拒绝（显式声明才授权）。
        """
        rules = (model_perms or {}).get(action)
        if not isinstance(rules, list) or not rules:
            return False
        if "*" in rules:
            return True
        roles = set(membership_roles or [])
        for rule in rules:
            if rule == "owner" and user_id is not None and record_owner_id is not None and record_owner_id == str(user_id):
                return True
            if isinstance(rule, str) and rule.startswith("role:") and rule[5:] in roles:
                return True
        return False

    @staticmethod
    def _read_allows_all(model_perms: dict[str, Any] | None, membership_roles: list[str]) -> bool:
        """列表场景：该主体能否读全部行（通配或命中角色规则）。"""
        rules = (model_perms or {}).get("read")
        if not isinstance(rules, list) or not rules:
            return False
        if "*" in rules:
            return True
        roles = set(membership_roles or [])
        return any(isinstance(r, str) and r.startswith("role:") and r[5:] in roles for r in rules)

    # ── 数据校验 ─────────────────────────────────────────────────────

    def validate_record_data(self, model_def: dict[str, Any], data: Any) -> tuple[dict[str, Any], list[str]]:
        """按 manifest model 字段校验记录 JSON，返回 (规范化数据, 错误列表)。

        校验覆盖：未知字段拒绝（平台掌控唯一写入口）、required、type、
        enum options、default 注入。``ref`` 引用存在性需要查库，由
        ``_validate_refs`` 在写入路径上补查。
        """
        if not isinstance(data, dict):
            return {}, ["记录数据必须是 JSON 对象"]
        fields = {f.get("name"): f for f in (model_def.get("fields") or []) if isinstance(f, dict)}
        errors: list[str] = []
        for key in data:
            if key not in fields:
                errors.append(f"未知字段 {key!r}（模型未声明）")
        normalized: dict[str, Any] = {}
        for name, field in fields.items():
            value = data.get(name)
            if value is None:
                if field.get("required"):
                    errors.append(f"缺少必填字段 {name!r}")
                    continue
                if "default" in field and field["default"] is not None:
                    normalized[name] = field["default"]
                continue
            error = _check_field_value(name, field, value)
            if error:
                errors.append(error)
                continue
            normalized[name] = value
        return normalized, errors

    def _validate_refs(
        self,
        db: Session,
        app: AppModel,
        model_def: dict[str, Any],
        normalized: dict[str, Any],
        principal: dict[str, Any] | None,
    ) -> list[str]:
        """ref 引用完整性（2.1：模型间引用由平台写入时校验，避免脏数据）。

        ref="user" 必须指向本应用的终端用户；缺省时自动回填当前登录用户
        （秒哒同款「业务数据通过 userID 自动关联」），匿名场景留空。
        """
        errors: list[str] = []
        for field in model_def.get("fields") or []:
            if not isinstance(field, dict) or field.get("ref") != "user":
                continue
            name = field.get("name")
            if name is None:
                continue
            if name not in normalized:
                user_id = (principal or {}).get("user_id")
                if user_id is not None:
                    normalized[name] = str(user_id)
                elif field.get("required"):
                    errors.append(f"缺少必填字段 {name!r}")
                continue
            raw = normalized[name]
            try:
                ref_id = int(raw)
            except (TypeError, ValueError):
                errors.append(f"字段 {name!r} 的用户引用必须是应用用户 id")
                continue
            exists = db.scalar(select(AppUserModel.id).where(AppUserModel.id == ref_id, AppUserModel.app_id == app.id))
            if exists is None:
                errors.append(f"字段 {name!r} 引用的用户 {ref_id} 不存在于本应用")
        return errors

    # ── 记录 CRUD ────────────────────────────────────────────────────

    def _require_deployed_model(self, app: AppModel, model_name: str) -> dict[str, Any]:
        """数据端点前置检查：应用已部署 + 模型在生效 manifest 里声明。"""
        manifest = _load_manifest(app)
        for model_def in manifest.get("models") or []:
            if isinstance(model_def, dict) and model_def.get("name") == model_name:
                return model_def
        raise AppNotFound(f"数据模型 {model_name!r} 不存在")

    @staticmethod
    def _model_perms(model_def: dict[str, Any]) -> dict[str, Any]:
        perms = model_def.get("permissions")
        return perms if isinstance(perms, dict) else {}

    @staticmethod
    def _serialize(record: AppRecordModel) -> dict[str, Any]:
        return {
            "id": record.record_id,
            "ownerId": record.owner_id,
            "createdAt": record.created_at.isoformat() if record.created_at else None,
            "updatedAt": record.updated_at.isoformat() if record.updated_at else None,
            "data": record.data if isinstance(record.data, dict) else {},
        }

    def list_records(
        self,
        db: Session,
        app: AppModel,
        env: str,
        model_name: str,
        principal: dict[str, Any] | None,
        *,
        where: dict[str, Any] | None = None,
        order_by: str = "createdAt",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """列表：行级过滤在查询层注入（3.2「平台在查询层直接注入条件」）。

        where 等值过滤当前在 Python 侧做（SQLite/PG JSON 方言差异大，
        第一步优先正确性）；行集硬上限 MAX_LIST_FETCH 防失控。
        """
        model_def = self._require_deployed_model(app, model_name)
        perms = self._model_perms(model_def)
        user_id = (principal or {}).get("user_id")
        roles = (principal or {}).get("roles") or []

        stmt = select(AppRecordModel).where(
            AppRecordModel.app_id == app.id,
            AppRecordModel.env == env,
            AppRecordModel.model == model_name,
        )
        if self._read_allows_all(perms, roles):
            pass  # 通配 / 命中角色规则 → 可读全部行，无需附加过滤
        elif "owner" in (perms.get("read") or []) and user_id is not None:
            stmt = stmt.where(AppRecordModel.owner_id == str(user_id))
        else:
            raise AppForbidden(f"对模型 {model_name!r} 没有读取权限", status_code=403)

        order_column = {"createdAt": AppRecordModel.created_at, "updatedAt": AppRecordModel.updated_at}.get(order_by)
        if order_column is None:
            raise AppPlatformError("order_by 只支持 createdAt / updatedAt")
        stmt = stmt.order_by(order_column.desc() if order == "desc" else order_column.asc()).limit(MAX_LIST_FETCH)

        rows = list(db.scalars(stmt).all())
        if where:
            unknown = [k for k in where if k not in {f.get("name") for f in model_def.get("fields") or []}]
            if unknown:
                raise AppPlatformError(f"where 含未声明字段: {unknown}")
            rows = [r for r in rows if isinstance(r.data, dict) and all(r.data.get(k) == v for k, v in where.items())]
        return [self._serialize(r) for r in rows[offset : offset + max(1, min(limit, MAX_LIST_LIMIT))]]

    def get_record(
        self, db: Session, app: AppModel, env: str, model_name: str, record_id: str, principal: dict[str, Any] | None
    ) -> dict[str, Any]:
        model_def = self._require_deployed_model(app, model_name)
        record = self._fetch(db, app, env, model_name, record_id)
        principal = principal or {"user_id": None, "roles": []}
        if not self.can(record.owner_id, self._model_perms(model_def), "read", principal.get("user_id"), principal.get("roles") or []):
            raise AppForbidden("没有读取该记录的权限", status_code=403)
        return self._serialize(record)

    def create_record(
        self,
        db: Session,
        app: AppModel,
        env: str,
        model_name: str,
        data: Any,
        principal: dict[str, Any] | None,
    ) -> dict[str, Any]:
        model_def = self._require_deployed_model(app, model_name)
        perms = self._model_perms(model_def)
        principal = principal or {"user_id": None, "roles": []}
        if not self.can(None, perms, "create", principal.get("user_id"), principal.get("roles") or []):
            raise AppForbidden(f"对模型 {model_name!r} 没有创建权限", status_code=403)

        normalized, errors = self.validate_record_data(model_def, data)
        errors.extend(self._validate_refs(db, app, model_def, normalized, principal))
        if errors:
            raise AppPlatformError("记录校验失败: " + "; ".join(errors))

        record = AppRecordModel(
            app_id=app.id,
            env=env,
            model=model_name,
            record_id=str(uuid4()),
            owner_id=str(principal["user_id"]) if principal.get("user_id") is not None else None,
            data=normalized,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return self._serialize(record)

    def update_record(
        self,
        db: Session,
        app: AppModel,
        env: str,
        model_name: str,
        record_id: str,
        patch: Any,
        principal: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """PATCH 语义：patch 与现有 data 合并后整体校验（行级 update 权限）。"""
        model_def = self._require_deployed_model(app, model_name)
        record = self._fetch(db, app, env, model_name, record_id)
        principal = principal or {"user_id": None, "roles": []}
        if not self.can(record.owner_id, self._model_perms(model_def), "update", principal.get("user_id"), principal.get("roles") or []):
            raise AppForbidden("没有修改该记录的权限", status_code=403)

        merged = dict(record.data) if isinstance(record.data, dict) else {}
        if isinstance(patch, dict):
            merged.update(patch)
        normalized, errors = self.validate_record_data(model_def, merged)
        errors.extend(self._validate_refs(db, app, model_def, normalized, principal))
        if errors:
            raise AppPlatformError("记录校验失败: " + "; ".join(errors))
        record.data = normalized
        db.commit()
        db.refresh(record)
        return self._serialize(record)

    def delete_record(
        self, db: Session, app: AppModel, env: str, model_name: str, record_id: str, principal: dict[str, Any] | None
    ) -> None:
        model_def = self._require_deployed_model(app, model_name)
        record = self._fetch(db, app, env, model_name, record_id)
        principal = principal or {"user_id": None, "roles": []}
        if not self.can(record.owner_id, self._model_perms(model_def), "delete", principal.get("user_id"), principal.get("roles") or []):
            raise AppForbidden("没有删除该记录的权限", status_code=403)
        db.delete(record)
        db.commit()

    @staticmethod
    def _fetch(db: Session, app: AppModel, env: str, model_name: str, record_id: str) -> AppRecordModel:
        record = db.get(AppRecordModel, {"app_id": app.id, "env": env, "model": model_name, "record_id": record_id})
        if record is None:
            raise AppNotFound("记录不存在")
        return record


def _check_field_value(name: str, field: dict[str, Any], value: Any) -> str | None:
    """单字段类型校验；返回错误文案或 None。"""
    field_type = field.get("type")
    if field_type in {"string", "text", "date", "datetime"}:
        if not isinstance(value, str):
            return f"字段 {name!r} 应为字符串"
    elif field_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"字段 {name!r} 应为数字"
    elif field_type == "boolean":
        if not isinstance(value, bool):
            return f"字段 {name!r} 应为布尔值"
    elif field_type == "enum":
        if not isinstance(value, str) or value not in (field.get("options") or []):
            return f"字段 {name!r} 取值 {value!r} 不在枚举范围内"
    return None
