"""会话工作区浏览端点（右侧「文件」面板）的行为与安全。"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-1234567890abcdef")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.core.data_path import workspace_dir  # noqa: E402
from app.db.models import UserModel  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def panel_client(tmp_path, monkeypatch):
    """覆盖用户身份与工作区根目录，避免碰真实数据。

    端点在函数体内 `from app.core.data_path import workspace_dir`，
    所以只需补丁来源模块。
    """
    user = UserModel(id=4242, email="panel@t.dev", password_hash="x", role="user")
    app.dependency_overrides[get_current_user] = lambda: user

    real_root = Path(tmp_path) / "ws"
    real_root.mkdir()
    (real_root / "uploads").mkdir()
    (real_root / "uploads" / "hello.txt").write_text("hi", encoding="utf-8")

    import app.core.data_path as data_path_mod

    monkeypatch.setattr(
        data_path_mod, "workspace_dir", lambda uid, sid, create=False: real_root
    )

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


class TestWorkspaceListing:
    def test_lists_entries_with_type_and_size(self, panel_client):
        r = panel_client.get("/api/v1/files/workspace", params={"session_id": "s1"})
        assert r.status_code == 200
        body = r.json()
        assert body["root_exists"] is True
        names = {e["name"]: e for e in body["entries"]}
        assert "uploads" in names
        assert names["uploads"]["type"] == "dir"

        r = panel_client.get(
            "/api/v1/files/workspace", params={"session_id": "s1", "path": "uploads"}
        )
        entries = r.json()["entries"]
        assert entries[0]["name"] == "hello.txt"
        assert entries[0]["type"] == "file"
        assert entries[0]["size"] == 2

    def test_missing_workspace_returns_root_exists_false(self, panel_client, monkeypatch):
        import app.core.data_path as data_path_mod

        monkeypatch.setattr(
            data_path_mod,
            "workspace_dir",
            lambda uid, sid, create=False: Path("Z:/definitely-not-here"),
        )
        r = panel_client.get("/api/v1/files/workspace", params={"session_id": "s1"})
        assert r.status_code == 200
        assert r.json() == {"path": "", "entries": [], "root_exists": False}

    def test_traversal_is_rejected(self, panel_client):
        for evil in ("../../..", "..\\..\\windows", "uploads/../../.."):
            r = panel_client.get(
                "/api/v1/files/workspace", params={"session_id": "s1", "path": evil}
            )
            assert r.status_code == 400, f"path={evil!r} 应被拒绝"

    def test_hidden_files_are_skipped(self, panel_client):
        import app.core.data_path as data_path_mod

        # 在 fixture 根下补一个隐藏文件
        root = data_path_mod.workspace_dir(1, "1", create=False)
        (root / ".secret").write_text("x", encoding="utf-8")
        r = panel_client.get("/api/v1/files/workspace", params={"session_id": "s1"})
        names = [e["name"] for e in r.json()["entries"]]
        assert ".secret" not in names
