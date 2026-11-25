"""网站应用化平台回归（docs/research/网站应用化设计.md 步骤 1 + 2）。

覆盖：管理员建应用 → manifest 提交 → plan 生成 → 审批 apply（含逐项收紧）→
应用用户 signup/login/me → 数据 CRUD 全链 → 行级权限（owner 规则、角色规则、
跨 app 令牌 401/403）→ 令牌不含角色（membership 改后立即生效）→ env 隔离 →
公开只读 → SDK 路由 → manifest 校验拒绝 → 管理端权限。

注意：测试直连真实测试库，slug / 邮箱带唯一后缀避免跨用例污染。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import AppMembershipModel, AppModel, AppRecordModel, AppUserModel, UserModel
from app.db.session import create_db_session
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


# ── 夹具工具 ──────────────────────────────────────────────────────────


def _platform_token(email: str, role: str) -> str:
    """造平台侧用户 + 令牌（管理员 / 普通用户），对齐 test_published_items 模式。"""
    with create_db_session() as db:
        user = UserModel(
            email=email,
            name=f"{role.title()} User",
            password_hash=hash_password("password-123"),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    settings = get_settings()
    return create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        secret=settings.auth_secret_key,
        expires_in_seconds=settings.auth_token_expire_minutes * 60,
    )


def _cleanup(slug: str, *emails: str) -> None:
    """按外键安全顺序清理：records → memberships → app_users → app → 平台用户。"""
    with create_db_session() as db:
        apps = db.query(AppModel).filter(AppModel.slug == slug).all()
        for app_row in apps:
            db.query(AppRecordModel).filter(AppRecordModel.app_id == app_row.id).delete()
            db.query(AppMembershipModel).filter(AppMembershipModel.app_id == app_row.id).delete()
            db.query(AppUserModel).filter(AppUserModel.app_id == app_row.id).delete()
            db.delete(app_row)
        for email in emails:
            db.query(UserModel).filter(UserModel.email == email).delete()
        db.commit()


def _base_manifest() -> dict[str, Any]:
    """设计文档 2 节示例的最小可用版本（不含 rating 字段，留给增量测试）。"""
    return {
        "version": 1,
        "name": "客户反馈看板",
        "description": "收集客户反馈并按状态汇总",
        "auth": {
            "mode": "builtin",
            "loginMethods": ["email"],
            "allowSignup": True,
            "roles": ["viewer", "editor", "admin"],
        },
        "models": [
            {
                "name": "feedback",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "body", "type": "text"},
                    {"name": "status", "type": "enum", "options": ["new", "processing", "done"], "default": "new"},
                    {"name": "ownerId", "type": "string", "ref": "user"},
                ],
                "permissions": {
                    "read": ["owner", "role:editor", "role:admin"],
                    "create": ["role:viewer", "role:editor", "role:admin"],
                    "update": ["owner", "role:editor", "role:admin"],
                    "delete": ["role:admin"],
                },
            }
        ],
    }


def _create_app(client: TestClient, admin_token: str, slug: str) -> tuple[dict[str, Any], str]:
    """创建应用；secret 明文只出现这一次。"""
    resp = client.post(
        "/api/v1/admin/apps",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "反馈看板", "slug": slug},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    return payload["app"], payload["secret_key"]


def _deploy(
    client: TestClient, admin_token: str, app_id: str, manifest: dict[str, Any], *, approved_paths: list[str] | None = None
) -> dict[str, Any]:
    """提交 manifest → approve（默认全量批准；approved_paths 指定时逐项收紧）。"""
    submitted = client.post(
        f"/api/v1/admin/apps/{app_id}/manifest",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"manifest": manifest},
    )
    assert submitted.status_code == 200, submitted.text
    body: dict[str, Any] = {}
    if approved_paths is not None:
        body = {"approved_paths": approved_paths}
    approved = client.post(
        f"/api/v1/admin/apps/{app_id}/approve",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=body,
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def _app_user_headers(client: TestClient, app_id: str, email: str) -> dict[str, str]:
    """signup（已存在则 login）拿应用级令牌，返回 Authorization 头。"""
    resp = client.post(f"/api/v1/apps/{app_id}/auth/signup", json={"email": email, "password": "password-123"})
    if resp.status_code != 200:
        resp = client.post(f"/api/v1/apps/{app_id}/auth/login", json={"email": email, "password": "password-123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── 全链路：建应用 → 审批 → 账号 → 数据 CRUD ─────────────────────────


def test_full_chain_admin_app_to_data_crud(client):
    """管理员建应用 → manifest → plan → apply → signup → login → me → 数据 CRUD。"""
    suffix = uuid4().hex
    slug = f"app-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        # ── 1. 创建应用：secret 只返回一次，库里只有 sha256 ──
        app_row, secret = _create_app(client, admin_token, slug)
        app_id = app_row["id"]
        assert app_row["status"] == "draft"
        assert secret.startswith("ak-agenticos-")
        assert app_row["has_manifest"] is False

        listing = client.get("/api/v1/admin/apps", headers={"Authorization": f"Bearer {admin_token}"}).json()
        item = next(a for a in listing["items"] if a["id"] == app_id)
        assert "secret_key" not in item and "api_key_hash" not in item, "secret 相关字段不出参"
        assert item["status"] == "draft"

        with create_db_session() as db:
            stored = db.get(AppModel, app_id)
            assert stored.api_key_hash and secret not in stored.api_key_hash, "库里只存 sha256"

        # ── 2. 提交 manifest → plan 全是新建项 ──
        manifest = _base_manifest()
        submitted = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"manifest": manifest},
        )
        assert submitted.status_code == 200, submitted.text
        plan = submitted.json()["plan"]
        assert any(op["op"] == "+" and op["path"] == "models.feedback" for op in plan)
        # 能力默认拒绝：首次提交即开放注册，属于要人工细看的风险项（5.1 认证方式中风险）
        risk_paths = [op["path"] for op in plan if op["risk"]]
        assert risk_paths == ["auth.allowSignup"], risk_paths

        # 审批前数据端点不可用（未部署）
        early = client.get(f"/api/v1/apps/{app_id}/data/feedback")
        assert early.status_code == 403, early.text

        # ── 3. 批准 = apply → deployed ──
        approved = client.post(
            f"/api/v1/admin/apps/{app_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["app"]["status"] == "deployed"
        assert approved.json()["manifest"]["models"][0]["name"] == "feedback"

        # 幂等：无待审批版本时再批 → 400；再查 plan → 404
        again = client.post(f"/api/v1/admin/apps/{app_id}/approve", headers={"Authorization": f"Bearer {admin_token}"}, json={})
        assert again.status_code == 400
        no_plan = client.get(f"/api/v1/admin/apps/{app_id}/plan", headers={"Authorization": f"Bearer {admin_token}"})
        assert no_plan.status_code == 404

        # ── 4. 应用用户 signup / login / me ──
        user_email = f"user-{suffix}@example.com"
        signup = client.post(
            f"/api/v1/apps/{app_id}/auth/signup",
            json={"email": user_email, "password": "password-123", "display_name": "小张"},
        )
        assert signup.status_code == 200, signup.text
        token = signup.json()["access_token"]
        assert signup.json()["user"]["roles"] == ["viewer"], "初始角色取 manifest 默认"

        dup = client.post(f"/api/v1/apps/{app_id}/auth/signup", json={"email": user_email, "password": "password-456"})
        assert dup.status_code == 409, "同应用邮箱唯一"

        bad_login = client.post(f"/api/v1/apps/{app_id}/auth/login", json={"email": user_email, "password": "wrong-pass"})
        assert bad_login.status_code == 401
        good_login = client.post(f"/api/v1/apps/{app_id}/auth/login", json={"email": user_email, "password": "password-123"})
        assert good_login.status_code == 200, good_login.text

        headers = {"Authorization": f"Bearer {token}"}
        me = client.get(f"/api/v1/apps/{app_id}/me", headers=headers)
        assert me.status_code == 200, me.text
        assert me.json()["email"] == user_email
        assert me.json()["roles"] == ["viewer"]

        # ── 5. 数据 CRUD 全链 ──
        created = client.post(
            f"/api/v1/apps/{app_id}/data/feedback",
            headers=headers,
            json={"title": "页面卡顿"},
        )
        assert created.status_code == 200, created.text
        record = created.json()
        assert record["data"]["status"] == "new", "缺省字段注入 manifest default"
        assert record["data"]["ownerId"] == record["ownerId"], "ref=user 字段自动回填当前用户"
        record_id = record["id"]

        # 校验失败路径：缺必填 / 非法枚举 / 未知字段
        assert client.post(f"/api/v1/apps/{app_id}/data/feedback", headers=headers, json={"rating": 1}).status_code == 400
        assert client.post(
            f"/api/v1/apps/{app_id}/data/feedback", headers=headers, json={"title": "x", "status": "bogus"}
        ).status_code == 400
        assert client.post(
            f"/api/v1/apps/{app_id}/data/feedback", headers=headers, json={"title": "x", "hacked": 1}
        ).status_code == 400

        second = client.post(
            f"/api/v1/apps/{app_id}/data/feedback", headers=headers, json={"title": "导出报错", "status": "processing"}
        ).json()

        got = client.get(f"/api/v1/apps/{app_id}/data/feedback/{record_id}", headers=headers)
        assert got.status_code == 200 and got.json()["data"]["title"] == "页面卡顿"

        # where 等值过滤
        listed = client.get(
            f"/api/v1/apps/{app_id}/data/feedback",
            headers=headers,
            params={"where": json.dumps({"status": "processing"})},
        )
        assert listed.status_code == 200, listed.text
        assert [i["id"] for i in listed.json()["items"]] == [second["id"]]

        patched = client.patch(
            f"/api/v1/apps/{app_id}/data/feedback/{record_id}", headers=headers, json={"status": "done"}
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["data"]["status"] == "done"
        assert patched.json()["data"]["title"] == "页面卡顿", "PATCH 合并语义保留未提及字段"

        # viewer 无删除权限（delete 只给 role:admin），随后走管理端授权再删
        assert client.delete(f"/api/v1/apps/{app_id}/data/feedback/{record_id}", headers=headers).status_code == 403
        me_id = client.get(f"/api/v1/apps/{app_id}/me", headers=headers).json()["id"]
        grant = client.put(
            f"/api/v1/admin/apps/{app_id}/members/{me_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"roles": ["admin"]},
        )
        assert grant.status_code == 200, grant.text

        deleted = client.delete(f"/api/v1/apps/{app_id}/data/feedback/{record_id}", headers=headers)
        assert deleted.status_code == 200
        assert client.get(f"/api/v1/apps/{app_id}/data/feedback/{record_id}", headers=headers).status_code == 404

        # 未知模型 / 非法 env
        assert client.get(f"/api/v1/apps/{app_id}/data/ghost", headers=headers).status_code == 404
        assert client.get(
            f"/api/v1/apps/{app_id}/data/feedback", headers=headers, params={"env": "staging"}
        ).status_code == 400

        # 坏令牌 / 缺令牌 → 401
        assert client.get(f"/api/v1/apps/{app_id}/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
        assert client.get(f"/api/v1/apps/{app_id}/me").status_code == 401
    finally:
        _cleanup(slug, admin_email)


def test_plan_risk_items_and_admin_tightening(client):
    """v2 扩权在 plan 里显形（! 风险项）；审批逐项收紧后风险项不生效（5.4）。"""
    suffix = uuid4().hex
    slug = f"tight-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        app_row, _ = _create_app(client, admin_token, slug)
        app_id = app_row["id"]
        _deploy(client, admin_token, app_id, _base_manifest())

        # v2：新增 rating 字段 + read 放成通配 + 出站白名单 —— 两处扩权
        v2 = _base_manifest()
        v2["models"][0]["fields"].append({"name": "rating", "type": "number"})
        v2["models"][0]["permissions"]["read"] = ["*"]
        v2["capabilities"] = {"outbound": {"allow": ["api.example.com"], "mode": "deny"}}

        submitted = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"manifest": v2},
        )
        assert submitted.status_code == 200, submitted.text
        plan = submitted.json()["plan"]
        assert any(op["op"] == "!" and op["path"] == "models.feedback.permissions.read" for op in plan)
        assert any(op["op"] == "!" and op["path"] == "capabilities.outbound.allow" for op in plan)
        assert any(op["op"] == "~" and op["path"] == "models.feedback.fields.rating" for op in plan)
        assert any(op["op"] == "=" and op["path"] == "models.feedback.permissions.update" for op in plan)

        # GET plan 与提交响应一致（幂等可重放）
        plan_again = client.get(
            f"/api/v1/admin/apps/{app_id}/plan", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()["plan"]
        assert plan_again == plan

        # 只批准字段新增 → 两处扩权被回退，生效版本是收紧版
        approved = client.post(
            f"/api/v1/admin/apps/{app_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"approved_paths": ["models.feedback.fields.rating"]},
        )
        assert approved.status_code == 200, approved.text
        effective = approved.json()["manifest"]
        field_names = [f["name"] for f in effective["models"][0]["fields"]]
        assert "rating" in field_names, "已批准的字段修改生效"
        assert effective["models"][0]["permissions"]["read"] == ["owner", "role:editor", "role:admin"], "未批准的扩权被回退"
        assert (effective.get("capabilities", {}).get("outbound") or {}).get("allow") == [], "未批准的白名单扩容被回退（回到旧值空列表）"

        # 重新提交并全量批准 → 扩权生效（管理员有权放行）
        resubmitted = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"manifest": v2},
        )
        assert resubmitted.status_code == 200
        approved_all = client.post(
            f"/api/v1/admin/apps/{app_id}/approve",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={},
        )
        assert approved_all.status_code == 200
        final = approved_all.json()["manifest"]
        assert final["models"][0]["permissions"]["read"] == ["*"]
        assert final["capabilities"]["outbound"]["allow"] == ["api.example.com"]

        # 拒绝路径：提交一个候选再拒绝，保持 deployed、候选清空
        v3 = _base_manifest()
        v3["models"][0]["fields"].append({"name": "extra", "type": "string"})
        assert client.post(
            f"/api/v1/admin/apps/{app_id}/manifest",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"manifest": v3},
        ).status_code == 200
        rejected = client.post(
            f"/api/v1/admin/apps/{app_id}/reject",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"reason": "权限过宽"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["app"]["status"] == "deployed", "已部署版本的增量被拒 → 保持 deployed"
    finally:
        _cleanup(slug, admin_email)


def test_row_level_owner_and_role_rules(client):
    """owner 规则与 role 规则：viewer 只见自己的记录，editor 全读可改，admin 可删。"""
    suffix = uuid4().hex
    slug = f"acl-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        app_row, _ = _create_app(client, admin_token, slug)
        app_id = app_row["id"]
        _deploy(client, admin_token, app_id, _base_manifest())

        alice = _app_user_headers(client, app_id, f"alice-{suffix}@example.com")
        bob = _app_user_headers(client, app_id, f"bob-{suffix}@example.com")
        alice_id = client.get(f"/api/v1/apps/{app_id}/me", headers=alice).json()["id"]
        bob_id = client.get(f"/api/v1/apps/{app_id}/me", headers=bob).json()["id"]

        record = client.post(
            f"/api/v1/apps/{app_id}/data/feedback", headers=alice, json={"title": "alice 的反馈"}
        ).json()

        # 未登录（auth=builtin）→ 401
        assert client.get(f"/api/v1/apps/{app_id}/data/feedback").status_code == 401

        # viewer 只能读自己的行：bob 列表为空、单条 403、改删 403
        bob_list = client.get(f"/api/v1/apps/{app_id}/data/feedback", headers=bob)
        assert bob_list.status_code == 200 and bob_list.json()["items"] == []
        assert client.get(f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=bob).status_code == 403
        assert client.patch(
            f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=bob, json={"title": "x"}
        ).status_code == 403
        assert client.delete(f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=bob).status_code == 403

        # alice 是 owner：可见可改
        alice_list = client.get(f"/api/v1/apps/{app_id}/data/feedback", headers=alice)
        assert [i["id"] for i in alice_list.json()["items"]] == [record["id"]]
        assert client.patch(
            f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=alice, json={"status": "processing"}
        ).status_code == 200

        # 授予 editor（实时生效，无需换令牌）：bob 可读 alice 的行、可改，但仍不可删
        grant = client.put(
            f"/api/v1/admin/apps/{app_id}/members/{bob_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"roles": ["editor"]},
        )
        assert grant.status_code == 200, grant.text
        assert grant.json()["roles"] == ["editor"]

        bob_list2 = client.get(f"/api/v1/apps/{app_id}/data/feedback", headers=bob)
        assert [i["id"] for i in bob_list2.json()["items"]] == [record["id"]], "role:editor 可读全部行"
        assert client.patch(
            f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=bob, json={"status": "done"}
        ).status_code == 200
        assert client.delete(f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=bob).status_code == 403

        # 授予 admin：可删
        assert client.put(
            f"/api/v1/admin/apps/{app_id}/members/{bob_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"roles": ["admin"]},
        ).status_code == 200
        assert client.delete(f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=bob).status_code == 200

        # 未声明角色不能授予
        assert client.put(
            f"/api/v1/admin/apps/{app_id}/members/{bob_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"roles": ["superroot"]},
        ).status_code == 400
    finally:
        _cleanup(slug, admin_email)


def test_cross_app_token_rejected(client):
    """安全清单第一条：令牌的 app_id 与路径不一致 → 403；坏令牌 → 401。"""
    suffix = uuid4().hex
    slug_a, slug_b = f"xa-{suffix}", f"xb-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        app_a, _ = _create_app(client, admin_token, slug_a)
        app_b, _ = _create_app(client, admin_token, slug_b)
        _deploy(client, admin_token, app_a["id"], _base_manifest())
        _deploy(client, admin_token, app_b["id"], _base_manifest())

        token_a = _app_user_headers(client, app_a["id"], f"user-{suffix}@example.com")["Authorization"]
        headers_a = {"Authorization": token_a}

        # A 应用的令牌访问 B 应用的端点 → 403（令牌签名有效，作用域不匹配）
        wrong_app = client.get(f"/api/v1/apps/{app_b['id']}/data/feedback", headers=headers_a)
        assert wrong_app.status_code == 403, wrong_app.text
        assert client.get(f"/api/v1/apps/{app_b['id']}/me", headers=headers_a).status_code == 403

        # A 自己的端点正常
        assert client.get(f"/api/v1/apps/{app_a['id']}/me", headers=headers_a).status_code == 200
    finally:
        _cleanup(slug_a, slug_b, admin_email)


def test_token_has_no_roles_and_membership_realtime(client):
    """令牌 payload 不含角色；membership 改动即时生效，不需要重新登录。"""
    suffix = uuid4().hex
    slug = f"rt-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        app_row, _ = _create_app(client, admin_token, slug)
        app_id = app_row["id"]
        _deploy(client, admin_token, app_id, _base_manifest())

        headers = _app_user_headers(client, app_id, f"user-{suffix}@example.com")
        record = client.post(f"/api/v1/apps/{app_id}/data/feedback", headers=headers, json={"title": "x"}).json()

        # 1) 令牌里确实没有角色 claim
        from app.core.security import decode_access_token

        raw_token = headers["Authorization"].removeprefix("Bearer ")
        payload = decode_access_token(raw_token, secret=get_settings().auth_secret_key)
        assert payload is not None
        assert payload["app_id"] == app_id and isinstance(payload["user_id"], int)
        assert "roles" not in payload and "role" not in payload

        # viewer 不能删
        assert client.delete(f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=headers).status_code == 403

        # 2) membership 改成 admin（管理端）→ 同一枚令牌立即能删
        me = client.get(f"/api/v1/apps/{app_id}/me", headers=headers).json()
        assert me["roles"] == ["viewer"]
        grant = client.put(
            f"/api/v1/admin/apps/{app_id}/members/{me['id']}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"roles": ["admin"]},
        )
        assert grant.status_code == 200, grant.text
        assert client.get(f"/api/v1/apps/{app_id}/me", headers=headers).json()["roles"] == ["admin"]
        assert client.delete(
            f"/api/v1/apps/{app_id}/data/feedback/{record['id']}", headers=headers
        ).status_code == 200, "角色实时查库，旧令牌立即获得新权限"
    finally:
        _cleanup(slug, admin_email)


def test_signup_gating_and_public_readonly(client):
    """allowSignup=false 拒绝注册；auth.mode=none 应用匿名只读（无 create 规则即拒写）。"""
    suffix = uuid4().hex
    slug_closed, slug_public = f"closed-{suffix}", f"public-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        # ── 应用 1：builtin + allowSignup=false ──
        app_row, _ = _create_app(client, admin_token, slug_closed)
        manifest = _base_manifest()
        manifest["auth"]["allowSignup"] = False
        _deploy(client, admin_token, app_row["id"], manifest)

        denied = client.post(
            f"/api/v1/apps/{app_row['id']}/auth/signup", json={"email": f"u-{suffix}@example.com", "password": "password-123"}
        )
        assert denied.status_code == 403, denied.text

        # ── 应用 2：auth.mode=none（公开只读，等价当前静态站点）──
        app_row2, _ = _create_app(client, admin_token, slug_public)
        public_manifest = {
            "version": 1,
            "name": "公开留言板",
            "auth": {"mode": "none"},
            "models": [
                {
                    "name": "notes",
                    "fields": [{"name": "text", "type": "string", "required": True}],
                    "permissions": {"read": ["*"]},
                }
            ],
        }
        _deploy(client, admin_token, app_row2["id"], public_manifest)

        # 匿名可读（read: ["*"]），但注册被拒、写被拒（create 缺省 = 拒绝）
        anon_list = client.get(f"/api/v1/apps/{app_row2['id']}/data/notes")
        assert anon_list.status_code == 200 and anon_list.json()["items"] == []
        anon_create = client.post(f"/api/v1/apps/{app_row2['id']}/data/notes", json={"text": "x"})
        assert anon_create.status_code == 401, anon_create.text
        assert client.post(
            f"/api/v1/apps/{app_row2['id']}/auth/signup", json={"email": f"p-{suffix}@example.com", "password": "password-123"}
        ).status_code == 403, "auth.mode=none 不启用平台托管注册"
    finally:
        _cleanup(slug_closed, slug_public, admin_email)


def test_env_isolation(client):
    """dev/prod 数据隔离：env 列隔离，互不可见；非法 env 400。"""
    suffix = uuid4().hex
    slug = f"env-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        app_row, _ = _create_app(client, admin_token, slug)
        app_id = app_row["id"]
        _deploy(client, admin_token, app_id, _base_manifest())
        headers = _app_user_headers(client, app_id, f"user-{suffix}@example.com")

        dev_record = client.post(
            f"/api/v1/apps/{app_id}/data/feedback", headers=headers, json={"title": "开发数据"}, params={"env": "dev"}
        )
        assert dev_record.status_code == 200, dev_record.text

        prod_list = client.get(f"/api/v1/apps/{app_id}/data/feedback", headers=headers)
        assert prod_list.status_code == 200 and prod_list.json()["items"] == [], "dev 数据不进 prod"
        dev_list = client.get(
            f"/api/v1/apps/{app_id}/data/feedback", headers=headers, params={"env": "dev"}
        )
        assert [i["id"] for i in dev_list.json()["items"]] == [dev_record.json()["id"]]

        # dev 里删掉，prod 仍然没有（viewer 无删除权限，先授权 admin）
        me_id = client.get(f"/api/v1/apps/{app_id}/me", headers=headers).json()["id"]
        assert client.put(
            f"/api/v1/admin/apps/{app_id}/members/{me_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"roles": ["admin"]},
        ).status_code == 200
        assert client.delete(
            f"/api/v1/apps/{app_id}/data/feedback/{dev_record.json()['id']}", headers=headers, params={"env": "dev"}
        ).status_code == 200
        assert client.get(f"/api/v1/apps/{app_id}/data/feedback", headers=headers, params={"env": "dev"}).json()["items"] == []
    finally:
        _cleanup(slug, admin_email)


def test_sdk_route(client):
    """/sdk/agenticos.js：零依赖 JS，注入 window.AgenticOS，令牌只存内存。"""
    resp = client.get("/sdk/agenticos.js")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/javascript")
    body = resp.text
    assert "window.AgenticOS" in body
    assert "auth" in body and "data" in body and "files" in body
    assert "/api/v1/apps/" in body, "请求走相对路径平台端点"
    assert "setItem" not in body and "document.cookie" not in body, "安全清单：令牌不持久化（localStorage/cookie）"


def test_manifest_validation_rejects(client):
    """manifest 不过 schema 校验不进审批队列（2.0）。"""
    suffix = uuid4().hex
    slug = f"bad-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    try:
        app_row, _ = _create_app(client, admin_token, slug)
        app_id = app_row["id"]

        # 缺 auth
        no_auth = {"version": 1, "name": "x", "models": []}
        resp = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest", headers={"Authorization": f"Bearer {admin_token}"}, json={"manifest": no_auth}
        )
        assert resp.status_code == 400, resp.text

        # 权限规则格式非法（"admin" 不是 owner / role: 前缀 / 通配）
        bad_rule = _base_manifest()
        bad_rule["models"][0]["permissions"]["delete"] = ["admin"]
        resp = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest", headers={"Authorization": f"Bearer {admin_token}"}, json={"manifest": bad_rule}
        )
        assert resp.status_code == 400, resp.text

        # 模型重名
        dup_models = _base_manifest()
        dup_models["models"].append(json.loads(json.dumps(dup_models["models"][0])))
        resp = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest", headers={"Authorization": f"Bearer {admin_token}"}, json={"manifest": dup_models}
        )
        assert resp.status_code == 400, resp.text

        # enum 字段缺 options
        bad_enum = _base_manifest()
        bad_enum["models"][0]["fields"][2] = {"name": "status", "type": "enum"}
        resp = client.post(
            f"/api/v1/admin/apps/{app_id}/manifest", headers={"Authorization": f"Bearer {admin_token}"}, json={"manifest": bad_enum}
        )
        assert resp.status_code == 400, resp.text

        # 提交失败后 app 仍是 draft：数据端点不可用（坏令牌 401 / 未部署 403）
        assert client.get(
            f"/api/v1/apps/{app_id}/data/feedback", headers={"Authorization": "Bearer x"}
        ).status_code == 401
    finally:
        _cleanup(slug, admin_email)


def test_admin_endpoints_require_admin(client):
    """平台管理端点仅限管理员；slug 冲突 409。"""
    suffix = uuid4().hex
    slug = f"perm-{suffix}"
    admin_email = f"adm-{suffix}@example.com"
    user_email = f"usr-{suffix}@example.com"
    admin_token = _platform_token(admin_email, "admin")
    user_token = _platform_token(user_email, "user")
    try:
        assert client.post(
            "/api/v1/admin/apps", headers={"Authorization": f"Bearer {user_token}"}, json={"name": "x", "slug": slug}
        ).status_code == 403
        assert client.get("/api/v1/admin/apps", headers={"Authorization": f"Bearer {user_token}"}).status_code == 403

        _create_app(client, admin_token, slug)
        dup = client.post(
            "/api/v1/admin/apps", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "y", "slug": slug}
        )
        assert dup.status_code == 409, "slug 唯一"

        # slug 格式非法（pydantic pattern 校验 → 422）
        assert client.post(
            "/api/v1/admin/apps", headers={"Authorization": f"Bearer {admin_token}"}, json={"name": "z", "slug": "Bad Slug!"}
        ).status_code == 422
    finally:
        _cleanup(slug, admin_email, user_email)
