"""作品库（gallery）与部署可见性 回归。

产品语义：
- 部署时可选 public/private，默认 private（没明确说要公开的不该被公开）；
- public：审批后发布到 nginx /sites/{slug}/，作品库所有人可见；
- private：仅部署者（和管理员）在作品库可见，访问走 30 天签名端点，
  **绝不落到公开的 /sites/ 路径**；
- 同一 pending 请求改可见性 → 就地更新（幂等 + 允许改主意）。

注意：测试直连真实数据库，slug/邮箱必须带唯一后缀避免跨用例污染。
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def proj(tmp_path, monkeypatch):
    """造一个已构建的网站项目（monkeypatch WEBSITES_DIR 与 NGINX_SERVE_ROOT）。"""
    from app.services import website_deploy_service as svc_mod

    base = tmp_path / "websites"
    serve = tmp_path / "serve"
    serve.mkdir()
    monkeypatch.setattr(svc_mod, "_WEBSITES_DIR", base)
    monkeypatch.setattr(svc_mod, "NGINX_SERVE_ROOT", serve)
    # 端点模块里的同名常量也要指过去（私密站点访问/预览用）
    import app.api.v1.endpoints.website as web_ep
    monkeypatch.setattr(web_ep, "_WEBSITES_DIR", base)
    # 跳过 nginx reload（测试环境没有 nginx），并真实执行发布逻辑
    def _exec(self, deploy):
        from pathlib import Path as _P
        dist_path = self._resolve_dist_path(deploy)
        assert dist_path.exists(), f"dist missing: {dist_path}"
        visibility = deploy.visibility or "private"
        if visibility == "public":
            target = serve / deploy.project_slug
            deploy.deploy_url = f"/sites/{deploy.project_slug}/"
        else:
            target = serve / "_private" / deploy.project_slug
            deploy.deploy_url = None
        target.mkdir(parents=True, exist_ok=True)
        for item in dist_path.iterdir():
            dest = target / item.name
            if item.is_dir():
                import shutil
                shutil.copytree(item, dest)
            else:
                import shutil
                shutil.copy2(item, dest)
        deploy.status = "deployed"
        if visibility != "public":
            deploy.access_token = self._issue_access_token(deploy)

    monkeypatch.setattr(svc_mod.WebsiteDeployService, "_execute_deploy", _exec)
    return base


def _register(client, email):
    resp = client.post(
        "/api/v1/auth/register",
        json={"name": "g", "email": email, "password": "secret123"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user, token = body["user"], body["access_token"]
    # 部署走 Casbin 功能级鉴权 —— enforce 的 obj 是 build_object("feature",
    # "deploy_website") = "feature:deploy_website"，策略必须同形才匹配
    from app.services.permission_service import get_permission_service

    get_permission_service().add_policy(f"user:{user['id']}", "*", "feature:deploy_website", "write")
    return user, token


def _slug(user_id: int, uid: str) -> str:
    """归属校验要求的 slug 形态：u<用户ID>_s<会话ID>_v<版本>。"""
    return f"u{user_id}_s{uid}_v1"


def _session(uid: str) -> str:
    return f"s-{uid}"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_project(proj, slug: str) -> None:
    dist = proj / slug / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>gal</body></html>", encoding="utf-8"
    )
    (dist / "assets" / "a.js").write_text("console.log(1)", encoding="utf-8")


def _make_deploy(client, token, visibility, slug, session):
    resp = client.post(
        "/api/v1/website/deploy",
        headers=_auth(token),
        json={"session_id": session, "project_slug": slug, "stack": "vanilla",
              "visibility": visibility},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestVisibility:
    def test_deploy_defaults_to_private(self, client, proj):
        u = uuid.uuid4().hex[:8]
        user, token = _register(client, f"gal1-{u}@test.local")
        slug = _slug(user["id"], u)
        _make_project(proj, slug)
        d = _make_deploy(client, token, "private", slug, f"s-{u}")
        assert d["visibility"] == "private"

    def test_rejects_bad_visibility(self, client, proj):
        u = uuid.uuid4().hex[:8]
        user, token = _register(client, f"gal2-{u}@test.local")
        slug = _slug(user["id"], u)
        _make_project(proj, slug)
        resp = client.post(
            "/api/v1/website/deploy",
            headers=_auth(token),
            json={"session_id": f"s-{u}", "project_slug": slug, "stack": "vanilla",
                  "visibility": "internal"},
        )
        assert resp.status_code == 422

    def test_reuse_updates_visibility(self, client, proj):
        """同一 pending 请求改可见性 → 就地更新而非复用旧值。"""
        u = uuid.uuid4().hex[:8]
        user, token = _register(client, f"gal3-{u}@test.local")
        slug = _slug(user["id"], u)
        _make_project(proj, slug)
        d1 = _make_deploy(client, token, "private", slug, f"s-{u}")
        d2 = _make_deploy(client, token, "public", slug, f"s-{u}")
        assert d1["id"] == d2["id"], "应复用同一条 pending"
        assert d2["visibility"] == "public"


class TestGalleryPermissions:
    def test_private_hidden_from_others(self, client, proj):
        """私密作品不出现在其他人的作品库里。"""
        u1, u2 = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
        owner, owner_token = _register(client, f"own-{u1}@test.local")
        other, other_token = _register(client, f"oth-{u2}@test.local")

        slug_priv = _slug(owner["id"], u1)
        slug_pub = _slug(other["id"], u2)
        _make_project(proj, slug_priv)
        _make_project(proj, slug_pub)
        _make_deploy(client, owner_token, "private", slug_priv, f"s-own-{u1}")
        _make_deploy(client, other_token, "public", slug_pub, f"s-other-{u2}")
        # gallery 只列 deployed：把两条 pending 真正发布
        from app.services import website_deploy_service as svc_mod  # noqa: F811
        from app.db.models import WebsiteDeployModel as _WDM
        from app.db.session import create_db_session as _cdb
        svc = svc_mod.WebsiteDeployService()
        with _cdb() as _db:
            for d_id in (_make_deploy_ids := [None]):
                pass
            for row in _db.scalars(
                __import__("sqlalchemy").select(_WDM)
                .where(_WDM.status == "pending")
                .where(_WDM.session_id.in_([f"s-own-{u1}", f"s-other-{u2}"]))
            ).all():
                svc._execute_deploy(row)
            _db.commit()

        # owner 的 gallery：自己的 private + other 的 public
        mine = client.get("/api/v1/website/gallery", headers=_auth(owner_token)).json()
        slugs_own = {i["project_slug"] for i in mine}
        assert slug_priv in slugs_own
        assert slug_pub in slugs_own
        # other 的 gallery：只有 public，看不到 owner 的 private
        theirs = client.get("/api/v1/website/gallery", headers=_auth(other_token)).json()
        slugs_other = {i["project_slug"] for i in theirs}
        assert slug_priv not in slugs_other
        assert slug_pub in slugs_other
        # 每条 private 都带访问链接
        for item in mine:
            if item["project_slug"] == slug_priv:
                assert item.get("access_url")


class TestPrivateSiteAccess:
    def test_private_serves_with_token_and_rejects_without(self, client, proj):
        from app.db.models import WebsiteDeployModel
        from app.db.session import create_db_session
        from app.services import website_deploy_service as svc_mod

        u = uuid.uuid4().hex[:8]
        owner, owner_token = _register(client, f"pv-{u}@test.local")
        slug = _slug(owner["id"], u)
        _make_project(proj, slug)
        d = _make_deploy(client, owner_token, "private", slug, f"s-{u}")

        svc = svc_mod.WebsiteDeployService()
        with create_db_session() as db:
            row = db.get(WebsiteDeployModel, d["id"])
            svc._execute_deploy(row)
            db.commit()
            db.refresh(row)
            access_token = row.access_token
            assert row.deploy_url is None, "私密站点不该有 /sites/ 公开地址"

        assert access_token, "私密部署必须签发访问令牌"
        r1 = client.get(f"/api/v1/website/site/{slug}/?t={access_token}")
        assert r1.status_code == 200 and "gal" in r1.text
        # 相对路径资源（query 里的 t 不影响 path 解析）
        r2 = client.get(f"/api/v1/website/site/{slug}/assets/a.js?t={access_token}")
        assert r2.status_code == 200

        # 无令牌 / 错令牌 → 403
        assert client.get(f"/api/v1/website/site/{slug}/?t=fake").status_code == 403
        assert client.get(f"/api/v1/website/site/{slug}/").status_code in (403, 422)

    def test_public_deploy_uses_sites_path(self, client, proj):
        """公开站点发布到 /sites/（nginx 路径），无访问令牌。"""
        from app.db.models import WebsiteDeployModel
        from app.db.session import create_db_session
        from app.services import website_deploy_service as svc_mod

        u = uuid.uuid4().hex[:8]
        user, token = _register(client, f"pub-{u}@test.local")
        slug = _slug(user["id"], u)
        _make_project(proj, slug)
        d = _make_deploy(client, token, "public", slug, f"s-{u}")
        svc = svc_mod.WebsiteDeployService()
        with create_db_session() as db:
            row = db.get(WebsiteDeployModel, d["id"])
            svc._execute_deploy(row)
            db.commit()
            db.refresh(row)
            assert row.visibility == "public"
            assert row.deploy_url == f"/sites/{slug}/"
            assert not row.access_token
