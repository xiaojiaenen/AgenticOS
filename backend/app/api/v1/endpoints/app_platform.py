"""网站应用化平台端点（docs/research/网站应用化设计.md 步骤 1 + 2）。

三组路由：

1. **应用侧** ``/api/v1/apps/{app_id}/...``：终端用户 auth/login / signup / me
   与数据 CRUD —— 鉴权用应用级用户令牌（不含角色），行级权限在 service 层
   判定；``env`` 查询参数切 dev/prod（默认 prod）。
2. **管理端** ``/api/v1/admin/apps``：创建应用（secret 明文只返回一次）、
   提交 manifest → plan → approve/reject（apply 收紧后的 plan）、成员角色。
   全部 require_admin + 审计。
3. **静态 SDK** ``GET /sdk/agenticos.js``（``sdk_router``，挂在应用根）：
   零依赖浏览器 SDK，令牌只存内存（安全清单：不进 localStorage）。

安全对照（设计文档第 9 节能实现部分）：每个 app 端点校验令牌 app_id 与
路径一致（resolve_principal 403）；令牌过期/签名由 decode 兜住；角色实时查
membership 不读 claim；行级权限查询层注入；manifest 必过 schema 校验才进
审批；审批只能收紧不能放宽（apply 回退未批准风险项）；每次 apply 落审计；
secret/API key 哈希存储、令牌不落日志（audit_service 脱敏 + 只存哈希）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_perm
from app.db.models import AppModel, AppUserModel, UserModel
from app.schemas.app_platform import (
    ManifestDraftRequest,
    AppCreateRequest,
    AppLoginRequest,
    AppSignupRequest,
    ManifestApproveRequest,
    ManifestRejectRequest,
    ManifestSubmitRequest,
    MemberRolesRequest,
)
from app.services import audit_service
from app.services.app_platform.manifest import generate_plan, validate_manifest
from app.services.app_platform.service import (
    APP_TOKEN_EXPIRE_SECONDS,
    ENVIRONMENTS,
    AppPlatformError,
    AppPlatformService,
)

router = APIRouter(tags=["App Platform"])
sdk_router = APIRouter(tags=["App Platform SDK"])

_service = AppPlatformService()

_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")


# ── 通用小工具 ────────────────────────────────────────────────────────


def _get_app_or_404(db: Session, app_id: str) -> AppModel:
    app = db.get(AppModel, app_id)
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")
    return app


def _extract_bearer(request: Request) -> str | None:
    """从 Authorization: Bearer <token> 提取应用令牌（缺失/格式错返回 None）。"""
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        return token or None
    return None


def _resolve_principal(db: Session, app: AppModel, request: Request, *, allow_anonymous: bool) -> dict[str, Any] | None:
    """统一入口：应用级令牌 → principal（含实时角色）；错误语义在 service 里定。"""
    return _service.resolve_principal(db, app, _extract_bearer(request), allow_anonymous=allow_anonymous)


def _env_or_400(env: str) -> str:
    if env not in ENVIRONMENTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"env 只支持 {' / '.join(ENVIRONMENTS)}")
    return env


def _serialize_app(app: AppModel) -> dict[str, Any]:
    """管理端视图：secret 哈希等敏感列一律不出参。"""
    return {
        "id": app.id,
        "name": app.name,
        "slug": app.slug,
        "status": app.status,
        "owner_user_id": app.owner_user_id,
        "has_manifest": bool(app.manifest_json),
        "has_pending_manifest": bool(app.pending_manifest_json),
        "created_at": app.created_at.isoformat() if app.created_at else None,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


def _serialize_app_user(principal: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": principal.get("user_id"),
        "email": principal.get("email"),
        "display_name": principal.get("display_name"),
        "roles": principal.get("roles") or [],
    }


def _plan_summary(plan: list[dict[str, Any]]) -> list[str]:
    """plan 的紧凑摘要（审计 detail 用，避免整份 manifest 进审计库）。"""
    return [f"{item['op']} {item['path']}" for item in plan]


# ── 应用侧：认证 ──────────────────────────────────────────────────────


@router.post("/apps/{app_id}/auth/login", summary="应用终端用户登录，换取应用级令牌")
def app_login(app_id: str, payload: AppLoginRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    user = _service.authenticate_app_user(db, app, email=payload.email, password=payload.password)
    if user is None:
        audit_service.record_request(
            db, request, action="app_platform.auth.login", result=audit_service.RESULT_DENY,
            resource_type="app", resource_id=app.id, detail={"email": payload.email},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码不正确")
    audit_service.record_request(
        db, request, action="app_platform.auth.login", resource_type="app", resource_id=app.id,
        actor_email=user.email, detail={"app_user_id": user.id},
    )
    return {
        "access_token": _service.sign_app_token(app.id, user.id),
        "token_type": "bearer",
        "expires_in": APP_TOKEN_EXPIRE_SECONDS,
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name},
    }


@router.post("/apps/{app_id}/auth/signup", summary="应用终端用户注册（需 manifest allowSignup）")
def app_signup(app_id: str, payload: AppSignupRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    try:
        user, roles = _service.signup_app_user(
            db, app, email=payload.email, password=payload.password, display_name=payload.display_name or ""
        )
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.auth.signup", resource_type="app", resource_id=app.id,
        actor_email=user.email, detail={"app_user_id": user.id, "roles": roles},
    )
    return {
        "access_token": _service.sign_app_token(app.id, user.id),
        "token_type": "bearer",
        "expires_in": APP_TOKEN_EXPIRE_SECONDS,
        "user": {"id": user.id, "email": user.email, "display_name": user.display_name, "roles": roles},
    }


@router.get("/apps/{app_id}/me", summary="当前应用主体 + 实时角色")
def app_me(app_id: str, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    try:
        principal = _resolve_principal(db, app, request, allow_anonymous=False)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return _serialize_app_user(principal or {})


# ── 应用侧：数据 CRUD ────────────────────────────────────────────────


@router.get("/apps/{app_id}/data/{model}", summary="记录列表（行级过滤在查询层注入）")
def list_records(
    app_id: str,
    model: str,
    request: Request,
    env: str = Query(default="prod"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    order_by: str = Query(default="createdAt"),
    order: str = Query(default="desc"),
    where: str | None = Query(default=None, description="等值过滤 JSON，如 {\"status\": \"new\"}"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    env = _env_or_400(env)
    where_filter: dict[str, Any] | None = None
    if where:
        try:
            where_filter = json.loads(where)
            if not isinstance(where_filter, dict):
                raise ValueError("where 必须是 JSON 对象")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"where 参数不合法: {exc}") from exc
    try:
        principal = _resolve_principal(db, app, request, allow_anonymous=True)
        items = _service.list_records(
            db, app, env, model, principal,
            where=where_filter, order_by=order_by, order=order, limit=limit, offset=offset,
        )
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"items": items, "count": len(items)}


@router.post("/apps/{app_id}/data/{model}", summary="新建记录")
def create_record(
    app_id: str, model: str, request: Request, body: dict[str, Any], env: str = Query(default="prod"), db: Session = Depends(get_db)
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    env = _env_or_400(env)
    try:
        principal = _resolve_principal(db, app, request, allow_anonymous=False)
        record = _service.create_record(db, app, env, model, body, principal)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.data.create", resource_type="app_record", resource_id=record["id"],
        actor_email=(principal or {}).get("email"),
        detail={"app_id": app.id, "model": model, "env": env},
    )
    return record


@router.get("/apps/{app_id}/data/{model}/{record_id}", summary="读取单条记录")
def get_record(
    app_id: str, model: str, record_id: str, request: Request, env: str = Query(default="prod"), db: Session = Depends(get_db)
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    env = _env_or_400(env)
    try:
        principal = _resolve_principal(db, app, request, allow_anonymous=True)
        return _service.get_record(db, app, env, model, record_id, principal)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.patch("/apps/{app_id}/data/{model}/{record_id}", summary="修改记录（PATCH 合并语义）")
def update_record(
    app_id: str, model: str, record_id: str, request: Request, body: dict[str, Any],
    env: str = Query(default="prod"), db: Session = Depends(get_db),
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    env = _env_or_400(env)
    try:
        principal = _resolve_principal(db, app, request, allow_anonymous=False)
        record = _service.update_record(db, app, env, model, record_id, body, principal)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.data.update", resource_type="app_record", resource_id=record["id"],
        actor_email=(principal or {}).get("email"),
        detail={"app_id": app.id, "model": model, "env": env},
    )
    return record


@router.delete("/apps/{app_id}/data/{model}/{record_id}", summary="删除记录")
def delete_record(
    app_id: str, model: str, record_id: str, request: Request, env: str = Query(default="prod"), db: Session = Depends(get_db)
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    env = _env_or_400(env)
    try:
        principal = _resolve_principal(db, app, request, allow_anonymous=False)
        _service.delete_record(db, app, env, model, record_id, principal)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.data.delete", resource_type="app_record", resource_id=record_id,
        actor_email=(principal or {}).get("email"),
        detail={"app_id": app.id, "model": model, "env": env},
    )
    return {"deleted": True, "id": record_id}


# ── 管理端（require_admin + 审计）────────────────────────────────────


@router.post("/admin/apps", summary="创建应用（secret 明文仅本次返回）")
def create_app(
    payload: AppCreateRequest, request: Request, db: Session = Depends(get_db), admin: UserModel = Depends(require_perm("gallery:approve"))
) -> dict[str, Any]:
    if not _SLUG_PATTERN.match(payload.slug):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="slug 只允许小写字母/数字/连字符")
    existing = db.scalar(select(AppModel).where(AppModel.slug == payload.slug))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="slug 已被占用")
    app, secret = _service.create_app(db, name=payload.name, slug=payload.slug, owner_user_id=admin.id)
    audit_service.record_request(
        db, request, action="app_platform.create", actor=admin,
        resource_type="app", resource_id=app.id, detail={"slug": app.slug, "name": app.name},
    )
    return {"app": _serialize_app(app), "secret_key": secret}


@router.get("/admin/apps", summary="应用列表")
def list_apps(db: Session = Depends(get_db), _admin: UserModel = Depends(require_perm("gallery:approve"))) -> dict[str, Any]:
    apps = list(db.scalars(select(AppModel).order_by(AppModel.created_at.desc())).all())
    return {"items": [_serialize_app(a) for a in apps], "count": len(apps)}


@router.post("/admin/apps/{app_id}/manifest", summary="提交新版本 manifest（校验 → 生成 plan → pending）")
def submit_manifest(
    app_id: str, payload: ManifestSubmitRequest, request: Request, db: Session = Depends(get_db), admin: UserModel = Depends(require_perm("gallery:approve"))
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    errors = validate_manifest(payload.manifest)
    if errors:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="manifest 校验失败: " + "; ".join(errors))
    try:
        plan = _service.submit_manifest(db, app, payload.manifest)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.manifest.submit", actor=admin,
        resource_type="app", resource_id=app.id, detail={"plan": _plan_summary(plan)},
    )
    return {"app": _serialize_app(app), "plan": plan}


@router.get("/admin/apps/{app_id}/plan", summary="查看当前候选版本相对生效版本的变更计划")
def get_plan(app_id: str, db: Session = Depends(get_db), _admin: UserModel = Depends(require_perm("gallery:approve"))) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    if not app.pending_manifest_json:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有待审批的 manifest 版本")
    candidate = json.loads(app.pending_manifest_json)
    current = json.loads(app.manifest_json) if app.manifest_json else None
    return {"app": _serialize_app(app), "plan": generate_plan(current, candidate)}


@router.post("/admin/apps/{app_id}/approve", summary="批准候选版本（apply 收紧后的 plan，落审计）")
def approve_manifest(
    app_id: str, payload: ManifestApproveRequest, request: Request, db: Session = Depends(get_db), admin: UserModel = Depends(require_perm("gallery:approve"))
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    candidate = json.loads(app.pending_manifest_json) if app.pending_manifest_json else None
    current = json.loads(app.manifest_json) if app.manifest_json else None
    plan_before = generate_plan(current, candidate) if candidate is not None else []
    approved_paths = set(payload.approved_paths) if payload.approved_paths is not None else None
    try:
        app, effective = _service.approve_manifest(db, app, approved_paths=approved_paths)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.manifest.approve", actor=admin,
        resource_type="app", resource_id=app.id,
        detail={
            "plan": _plan_summary(plan_before),
            "approved_paths": sorted(approved_paths) if approved_paths is not None else "all",
            "manifest_version": effective.get("version"),
        },
    )
    return {"app": _serialize_app(app), "manifest": effective}


@router.post("/admin/apps/{app_id}/reject", summary="拒绝候选版本")
def reject_manifest(
    app_id: str, payload: ManifestRejectRequest, request: Request, db: Session = Depends(get_db), admin: UserModel = Depends(require_perm("gallery:approve"))
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    try:
        app = _service.reject_manifest(db, app)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.manifest.reject", actor=admin,
        resource_type="app", resource_id=app.id, detail={"reason": payload.reason or ""},
    )
    return {"app": _serialize_app(app)}


@router.put("/admin/apps/{app_id}/members/{app_user_id}", summary="设置应用成员角色（实时生效，不改令牌）")
def set_member_roles(
    app_id: str, app_user_id: int, payload: MemberRolesRequest, request: Request,
    db: Session = Depends(get_db), admin: UserModel = Depends(require_perm("gallery:approve")),
) -> dict[str, Any]:
    app = _get_app_or_404(db, app_id)
    user = db.get(AppUserModel, app_user_id)
    if user is None or user.app_id != app.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用成员不存在")
    try:
        membership = _service.set_membership(db, app, user, payload.roles)
    except AppPlatformError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.member.roles", actor=admin,
        resource_type="app", resource_id=app.id,
        detail={"app_user_id": user.id, "email": user.email, "roles": list(membership.roles or [])},
    )
    return {"app_user_id": user.id, "email": user.email, "roles": list(membership.roles or [])}


# ── 静态 SDK（挂在应用根：GET /sdk/agenticos.js）─────────────────────

_SDK_JS = r"""/*! AgenticOS App SDK v1 — 零依赖；令牌只存内存（安全清单：不进 localStorage） */
var AgenticOS = (function () {
  "use strict";

  var _token = null; // 内存保存（安全清单：不进 localStorage / cookie）
  var _defaultApp = null; // auth.login/signup/use 绑定的当前应用；data.<model> 直取时使用

  function request(appId, method, path, body, query) {
    var url = "/api/v1/apps/" + appId + path;
    if (query) {
      var qs = Object.keys(query)
        .filter(function (k) { return query[k] !== undefined && query[k] !== null; })
        .map(function (k) {
          var v = typeof query[k] === "object" ? JSON.stringify(query[k]) : query[k];
          return encodeURIComponent(k) + "=" + encodeURIComponent(v);
        })
        .join("&");
      if (qs) url += "?" + qs;
    }
    var headers = { "Content-Type": "application/json" };
    if (_token) headers["Authorization"] = "Bearer " + _token;
    return fetch(url, {
      method: method,
      headers: headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    }).then(function (resp) {
      return resp
        .json()
        .catch(function () { return null; })
        .then(function (data) {
          if (!resp.ok) {
            var err = new Error((data && data.detail) || "HTTP " + resp.status);
            err.status = resp.status;
            throw err;
          }
          return data;
        });
    });
  }

  var auth = {
    login: function (appId, credentials) {
      return request(appId, "POST", "/auth/login", credentials).then(function (resp) {
        _token = resp.access_token;
        _defaultApp = appId;
        return resp.user;
      });
    },
    signup: function (appId, payload) {
      return request(appId, "POST", "/auth/signup", payload).then(function (resp) {
        _token = resp.access_token;
        _defaultApp = appId;
        return resp.user;
      });
    },
    me: function (appId) {
      return request(appId || _defaultApp, "GET", "/me");
    },
    // 多模型直取（data.feedback.list()）前先绑定当前应用；login/signup 已自动绑定
    use: function (appId) {
      _defaultApp = appId;
    },
    logout: function () {
      _token = null;
    }
  };

  function model(appId, name) {
    var base = "/data/" + name;
    return {
      list: function (options) {
        options = options || {};
        return request(appId, "GET", base, undefined, {
          where: options.where,
          limit: options.limit,
          offset: options.offset,
          order_by: options.orderBy,
          order: options.order,
          env: options.env
        }).then(function (resp) { return resp.items; });
      },
      get: function (id, options) {
        return request(appId, "GET", base + "/" + id, undefined, { env: options && options.env });
      },
      create: function (data, options) {
        return request(appId, "POST", base, data, { env: options && options.env });
      },
      update: function (id, patch, options) {
        return request(appId, "PATCH", base + "/" + id, patch, { env: options && options.env });
      },
      remove: function (id, options) {
        return request(appId, "DELETE", base + "/" + id, undefined, { env: options && options.env });
      }
    };
  }

  function boundModel(name) {
    if (!_defaultApp) {
      throw new Error("请先 AgenticOS.auth.login(appId, ...) 或 AgenticOS.auth.use(appId) 绑定当前应用");
    }
    return model(_defaultApp, name);
  }

  // data.model(appId, name) 显式取模型；Proxy 支持 data.feedback 直取（绑定默认应用后）
  var data = { model: model };
  if (typeof Proxy === "function") {
    data = new Proxy(data, {
      get: function (target, prop) {
        if (prop in target) return target[prop];
        if (typeof prop === "string" && /^[a-zA-Z][a-zA-Z0-9_]*$/.test(prop)) return boundModel(prop);
        return undefined;
      }
    });
  }

  return {
    version: "v1",
    auth: auth,
    data: data,
    files: {
      upload: function () {
        return Promise.reject(new Error("files 能力未开放（设计文档步骤 3）"));
      }
    }
  };
})();

// 浏览器挂 window.AgenticOS；Node 场景挂 globalThis（令牌仍在模块闭包内存里）
if (typeof window !== "undefined") {
  window.AgenticOS = AgenticOS;
} else if (typeof globalThis !== "undefined") {
  globalThis.AgenticOS = AgenticOS;
}
"""


@sdk_router.get("/sdk/agenticos.js", summary="应用前端 SDK（零依赖，注入 window.AgenticOS）")
def app_sdk() -> Response:
    return Response(
        content=_SDK_JS,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.post("/admin/apps/manifest/draft", summary="AI 生成 manifest 草稿（业务描述 → 结构化声明）")
async def draft_manifest_ai(
    payload: ManifestDraftRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_perm("gallery:approve")),
) -> dict[str, Any]:
    """网站应用化 2.0 的 AI 生成链路：业务描述 → 需求文档 + manifest 草稿。

    草稿**必须过 validate_manifest**（校验不过不进入审批队列，直接返回
    可操作的错误列表）；管理员在 plan/apply 审批里收紧权限后再生效。
    """
    from app.services.app_platform.manifest_ai import ManifestAIService

    try:
        draft = await ManifestAIService().generate_draft(payload.brief)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit_service.record_request(
        db, request, action="app_platform.manifest_draft", actor=current_user,
        resource_type="app_manifest", resource_id="draft",
        detail={"brief_len": len(payload.brief), "name": draft["manifest"].get("name")},
    )
    return draft
