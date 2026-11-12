"""文件型作品发布（PPT / 文档 / 表格）回归。

产品语义（用户明确要求）：

- PPT / Word / Excel 也能发布到作品库，**只能公开**（没有私密态）；
- 发布走「用户申请 → 管理员审批 → 后端导出文件 → 上架」；
- 审批前**不产生任何可访问的文件**（不能靠猜 URL 提前拿到内容）；
- 取消发布：作品下架，**源产物保留**（可重新发布）；
- 短链 ``/s/<code>/`` 指向已上架的作品；未上架的短码给出明确原因。

注意：测试直连真实数据库，标识必须带唯一后缀避免跨用例污染。
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.models import PublishedItemModel, UserModel
from app.db.session import create_db_session
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


def create_token(email: str, role: str) -> str:
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


def cleanup(source_ref: str, *emails: str) -> None:
    with create_db_session() as db:
        db.query(PublishedItemModel).filter(
            PublishedItemModel.source_ref == source_ref
        ).delete()
        for email in emails:
            db.query(UserModel).filter(UserModel.email == email).delete()
        db.commit()


def test_publish_request_then_approve_then_shortlink(client, tmp_path, monkeypatch):
    """完整链路：申请 → 审批 → 生成文件 → 短链可访问 → 取消后下架。"""
    suffix = uuid4().hex
    source_ref = f"sheet-dir-{suffix}"
    admin_email = f"pub-admin-{suffix}@example.com"
    user_email = f"pub-user-{suffix}@example.com"

    # 造一个 Univer 表格快照
    from app.core import data_path as dp

    sheets_dir = tmp_path / "sheets"
    sheet_dir = sheets_dir / source_ref
    sheet_dir.mkdir(parents=True)
    snapshot = {
        "name": "示例表格",
        "sheetOrder": ["s1"],
        "sheets": {
            "s1": {
                "name": "数据",
                "cellData": [[{"content": {"v": "你好"}}]],
            }
        },
    }
    (sheet_dir / "workbook.json").write_text(
        json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(dp, "SHEETS_DIR", sheets_dir)

    import app.services.published_item_service as svc_mod

    published_root = tmp_path / "published"
    monkeypatch.setattr(svc_mod, "PUBLISHED_ITEMS_DIR", published_root)

    admin_token = create_token(admin_email, "admin")
    user_token = create_token(user_email, "user")

    try:
        # ── 1. 提交申请 ──
        created = client.post(
            "/api/v1/published-items",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "kind": "sheet",
                "session_id": f"sess-{suffix}",
                "source_ref": source_ref,
                "title": "季度数据",
                "description": "一张示例表格",
            },
        )
        assert created.status_code == 200, created.text
        payload = created.json()
        item_id = payload["id"]
        assert payload["status"] == "pending"
        assert payload["visibility"] == "public"

        # 审批前不能通过下载端点拿到文件
        early = client.get(f"/api/v1/published-items/{item_id}/download")
        assert early.status_code == 404, early.text

        # 短码在未上架时给出明确原因
        short_code = payload["short_code"]
        early_short = client.get(f"/s/{short_code}/")
        assert early_short.status_code == 404
        assert "审批" in early_short.json()["detail"]

        # ── 2. 管理员审批通过 ──
        approved = client.post(
            f"/api/v1/admin/published-items/{item_id}/decision",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "approved", "reason": "内容合规"},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "deployed"

        # 文件真的生成了
        file_path = published_root / approved.json()["short_code"]
        assert file_path.is_dir()
        xlsx_files = list(file_path.glob("*.xlsx"))
        assert xlsx_files, f"未生成 xlsx: {list(file_path.iterdir())}"

        # ── 3. 下载端点可访问 ──
        downloaded = client.get(f"/api/v1/published-items/{item_id}/download")
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content[:2] == b"PK"  # xlsx 是 zip

        # ── 4. 短链 302 到下载端点 ──
        short = client.get(f"/s/{short_code}/", follow_redirects=False)
        assert short.status_code == 302
        assert f"/api/v1/published-items/{item_id}/download" in short.headers["location"]

        # ── 5. 取消发布 → 下架，源产物保留 ──
        cancelled = client.post(
            f"/api/v1/published-items/{item_id}/cancel",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"

        after = client.get(f"/api/v1/published-items/{item_id}/download")
        assert after.status_code == 404

        # 源快照还在（可重新发布）
        assert (sheet_dir / "workbook.json").is_file()
    finally:
        cleanup(source_ref, admin_email, user_email)


def test_publish_requires_valid_kind(client):
    """非法产物类型被拒（400），不会静默建单。"""
    suffix = uuid4().hex
    user_email = f"pub-bad-{suffix}@example.com"
    user_token = create_token(user_email, "user")
    try:
        resp = client.post(
            "/api/v1/published-items",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "kind": "video",
                "session_id": f"sess-{suffix}",
                "source_ref": f"x-{suffix}",
                "title": "x",
            },
        )
        assert resp.status_code == 422, resp.text
    finally:
        cleanup(f"x-{suffix}", user_email)


def test_non_admin_cannot_decide(client):
    """普通用户不能审批发布。"""
    suffix = uuid4().hex
    source_ref = f"noperm-{suffix}"
    admin_email = f"pub-adm-{suffix}@example.com"
    user_email = f"pub-usr-{suffix}@example.com"
    admin_token = create_token(admin_email, "admin")
    user_token = create_token(user_email, "user")
    try:
        created = client.post(
            "/api/v1/published-items",
            headers={"Authorization": f"Bearer {user_token}"},
            json={
                "kind": "ppt",
                "session_id": f"sess-{suffix}",
                "source_ref": source_ref,
                "title": "标题",
            },
        )
        assert created.status_code == 200
        item_id = created.json()["id"]

        denied = client.post(
            f"/api/v1/admin/published-items/{item_id}/decision",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"status": "approved"},
        )
        assert denied.status_code == 403, denied.text

        # 管理员可以审批（PPT 源不存在 → 落 failed，不是 500）
        admin_resp = client.post(
            f"/api/v1/admin/published-items/{item_id}/decision",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"status": "approved"},
        )
        assert admin_resp.status_code == 200, admin_resp.text
        assert admin_resp.json()["status"] == "failed"
    finally:
        cleanup(source_ref, admin_email, user_email)
