"""网站预览静态托管回归：签名校验 + 路径穿越防护。

背景：预览此前把 dist 内联成 100KB+ HTML 塞进 iframe srcdoc（每次拼字符串、
无法缓存、相对路径要手工改写、内联 module 脚本不执行导致白屏）。
改为带签名的静态托管，但**不能放 nginx /sites/**（那是审批通过后的发布位，
放进去等于绕过审批直接公开），所以走私有 API 通道。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def test_preview_token_requires_login(client):
    """未登录不能签发预览令牌。"""
    resp = client.post("/api/v1/website/preview-token?slug=x&session_id=s")
    assert resp.status_code in (401, 403)


def test_preview_rejects_invalid_token(client):
    """无效/伪造令牌一律 403。"""
    resp = client.get("/api/v1/website/preview/some-slug/bogus-token/index.html")
    assert resp.status_code == 403


def test_preview_rejects_token_for_other_slug(client):
    """令牌与项目不匹配 → 403（防止拿自己项目的令牌读别人的）。"""
    from app.core.config import get_settings
    from app.core.security import create_access_token

    s = get_settings()
    token = create_access_token(
        {"sub": "1", "scope": "website_preview", "sid": "s1", "slug": "project-a"},
        secret=s.auth_secret_key,
        expires_in_seconds=600,
    )
    resp = client.get(f"/api/v1/website/preview/project-b/{token}/index.html")
    assert resp.status_code == 403


def test_preview_rejects_path_traversal(client):
    """路径穿越（../）必须被挡掉。"""
    from app.core.config import get_settings
    from app.core.security import create_access_token

    s = get_settings()
    token = create_access_token(
        {"sub": "1", "scope": "website_preview", "sid": "s1", "slug": "proj"},
        secret=s.auth_secret_key,
        expires_in_seconds=600,
    )
    for evil in ("../../../etc/passwd", "..%2f..%2fetc%2fpasswd", "....//....//etc/passwd"):
        resp = client.get(f"/api/v1/website/preview/proj/{token}/{evil}")
        assert resp.status_code in (403, 404), evil


def test_preview_serves_file_with_valid_token(client, tmp_path, monkeypatch):
    """有效令牌 + 真实 dist 文件 → 返回内容与正确 MIME。"""
    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.api.v1.endpoints import website_preview as wp

    # 造一个项目 dist
    proj = tmp_path / "proj-x" / "dist"
    (proj / "assets").mkdir(parents=True)
    (proj / "index.html").write_text("<!doctype html><html><body>hi</body></html>", encoding="utf-8")
    (proj / "assets" / "a.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setattr(wp, "WEBSITES_DIR", tmp_path)

    s = get_settings()
    token = create_access_token(
        {"sub": "1", "scope": "website_preview", "sid": "s1", "slug": "proj-x"},
        secret=s.auth_secret_key,
        expires_in_seconds=600,
    )

    resp = client.get(f"/api/v1/website/preview/proj-x/{token}/index.html")
    assert resp.status_code == 200
    assert "hi" in resp.text
    assert "html" in resp.headers.get("content-type", "")

    # 空路径回退到 index.html（iframe 直接开根路径的场景）
    resp2 = client.get(f"/api/v1/website/preview/proj-x/{token}/")
    assert resp2.status_code == 200

    # 资源文件按扩展名给 MIME
    resp3 = client.get(f"/api/v1/website/preview/proj-x/{token}/assets/a.js")
    assert resp3.status_code == 200
    assert "javascript" in resp3.headers.get("content-type", "")
