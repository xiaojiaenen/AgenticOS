"""网站发布链路回归：短链 / 取消部署 / 重新部署需重新审批。

产品语义（用户明确要求）：

- 部署后的对外地址是短链 ``/s/<code>/``，不再暴露
  ``u<uid>_s<时间戳><随机>_v<n>`` 这类目录名；
- **取消部署**：站点下线，但**源码保留**（能随时重新部署）；
- 会话里更新项目后重新部署 → **必须重新审批**：旧版本立刻下架，
  新版本以 pending 建单。已上线内容永远对应一次明确批准的快照。

注意：测试直连真实数据库，slug/邮箱必须带唯一后缀避免跨用例污染。
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.models import WebsiteDeployModel
from app.db.session import create_db_session
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

    def _exec(self, deploy):
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
        import shutil

        for item in dist_path.iterdir():
            dest = target / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
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
    from app.services.permission_service import get_permission_service

    get_permission_service().add_policy(
        f"user:{user['id']}", "*", "feature:deploy_website", "write"
    )
    return user, token


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_project(proj: Path, slug: str) -> None:
    dist = proj / slug / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><body>hi</body></html>", encoding="utf-8"
    )


def test_deploy_uses_short_link(client, proj):
    """部署后的对外地址是 /s/<code>/，不含目录名。"""
    uid = uuid.uuid4().hex[:8]
    user, token = _register(client, f"short-{uid}@example.com")
    slug = f"u{user['id']}_s{uid}_v1"
    _make_project(proj, slug)

    resp = client.post(
        "/api/v1/website/deploy",
        headers=_auth(token),
        json={
            "session_id": f"s-{uid}",
            "project_slug": slug,
            "stack": "vanilla",
            "visibility": "public",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["short_code"], body
    assert body["short_url"].startswith("/s/")
    assert slug not in body["short_url"]

    # 短链在未审批时给出明确原因
    short = client.get(f"/s/{body['short_code']}/", follow_redirects=False)
    assert short.status_code == 404
    assert "审批" in short.json()["detail"]


def test_cancel_deploy_keeps_source(client, proj):
    """取消部署：站点下线，源码保留（dist 目录仍在）。"""
    uid = uuid.uuid4().hex[:8]
    user, token = _register(client, f"cancel-{uid}@example.com")
    slug = f"u{user['id']}_s{uid}_v1"
    _make_project(proj, slug)

    created = client.post(
        "/api/v1/website/deploy",
        headers=_auth(token),
        json={
            "session_id": f"s-{uid}",
            "project_slug": slug,
            "stack": "vanilla",
            "visibility": "public",
        },
    ).json()

    cancelled = client.post(
        f"/api/v1/website/deploy/{created['id']}/cancel", headers=_auth(token)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    # 源码保留
    assert (proj / slug / "dist" / "index.html").is_file()

    # 取消后短链给出明确原因
    short = client.get(f"/s/{created['short_code']}/", follow_redirects=False)
    assert short.status_code == 404
    assert "取消" in short.json()["detail"]


def test_redeploy_supersedes_previous_and_requires_new_approval(client, proj):
    """重新部署 → 旧版下架（superseded），新版回到 pending。"""
    uid = uuid.uuid4().hex[:8]
    user, token = _register(client, f"redeploy-{uid}@example.com")
    slug = f"u{user['id']}_s{uid}_v1"
    _make_project(proj, slug)

    first = client.post(
        "/api/v1/website/deploy",
        headers=_auth(token),
        json={
            "session_id": f"s-{uid}",
            "project_slug": slug,
            "stack": "vanilla",
            "visibility": "public",
        },
    ).json()

    # 直接把第一条标成已上线（模拟审批通过）
    with create_db_session() as db:
        row = db.get(WebsiteDeployModel, first["id"])
        row.status = "deployed"
        db.commit()

    second = client.post(
        "/api/v1/website/deploy",
        headers=_auth(token),
        json={
            "session_id": f"s-{uid}",
            "project_slug": slug,
            "stack": "vanilla",
            "visibility": "public",
        },
    ).json()

    assert second["id"] != first["id"]
    assert second["status"] == "pending"

    with create_db_session() as db:
        old = db.get(WebsiteDeployModel, first["id"])
        assert old.status == "superseded"
