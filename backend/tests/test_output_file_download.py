"""回归：会话 outputs/ 下的导出文件（csv/xlsx/json）必须能通过带鉴权端点下载。

原端点 ``get_session_output_image`` 只允许图片，导致 analyze_with_pandas 的
csv/xlsx/json 导出在 FilesPanel 里能看到却下载不了（400）。这里锁定扩展名
白名单、media_type、Content-Disposition、以及原有安全边界（会话归属 / 路径穿越）。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, ".")
os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-1234567890abcdef")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_current_user  # noqa: E402
from app.db.models import UserModel  # noqa: E402
from app.main import app  # noqa: E402
from app.services.agent_service import get_agent_service  # noqa: E402


class _FakeAgentService:
    async def ensure_session_access(self, request, user) -> None:
        # 模拟服务端会话归属校验：只允许 s-own，其余一律 403。
        if request.session_id != "s-own":
            raise PermissionError("当前用户无权访问该会话。")


@pytest.fixture()
def output_client(tmp_path, monkeypatch):
    """覆盖鉴权与工作区根目录，产出几种真实文件。"""
    user = UserModel(id=777, email="output@t.dev", password_hash="x", role="user")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_agent_service] = lambda: _FakeAgentService()

    root = Path(tmp_path) / "ws"
    out = root / "outputs"
    out.mkdir(parents=True)
    (out / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (out / "data.xlsx").write_bytes(b"PK\x03\x04-fake-xlsx")
    (out / "data.json").write_text('[{"a": 1}]', encoding="utf-8")
    (out / "notes.txt").write_text("hello", encoding="utf-8")
    (out / "notes.md").write_text("# hi", encoding="utf-8")
    (out / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (out / "photo.jpeg").write_bytes(b"\xff\xd8\xff")
    # 模型用 write_text_file("index.html") 直接写到工作区根目录的产物
    (root / "index.html").write_text("<!DOCTYPE html><html></html>", encoding="utf-8")

    import app.core.data_path as data_path_mod

    monkeypatch.setattr(
        data_path_mod, "workspace_dir", lambda uid, sid, create=False: root
    )

    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_agent_service, None)


def _url(filename: str, session_id: str = "s-own") -> str:
    return f"/api/v1/agent/sessions/{session_id}/outputs/{filename}"


class TestOutputFileDownload:
    def test_filename_regex_rejects_traversal(self):
        from app.api.v1.endpoints.agent import _IMAGE_OUTPUT_RE

        for evil in ("../x.csv", "..\\x.csv", "a/b.csv", "x.csv/../y.csv", "x.csv\x00.csv"):
            assert not _IMAGE_OUTPUT_RE.match(evil), evil
        assert _IMAGE_OUTPUT_RE.match("e2e.excel.xlsx")
        assert _IMAGE_OUTPUT_RE.match("e2e.json")

    @pytest.mark.parametrize(
        "filename, media_type",
        [
            ("data.csv", "text/csv"),
            ("data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("data.json", "application/json"),
            ("notes.txt", "text/plain"),
            ("notes.md", "text/markdown"),
        ],
    )
    def test_exports_download_as_attachments(self, output_client, filename, media_type):
        r = output_client.get(_url(filename))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith(media_type)
        assert r.headers["content-disposition"] == f'attachment; filename="{filename}"'
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "max-age=300" in r.headers["cache-control"]

    @pytest.mark.parametrize("filename", ["img.png", "photo.jpeg"])
    def test_images_stay_inline(self, output_client, filename):
        r = output_client.get(_url(filename))
        assert r.status_code == 200, r.text
        assert r.headers["content-disposition"] == "inline"
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_unsupported_extension_is_rejected(self, output_client, tmp_path):
        out = tmp_path / "ws" / "outputs"
        (out / "evil.exe").write_bytes(b"MZ")
        r = output_client.get(_url("evil.exe"))
        assert r.status_code == 400

    def test_traversal_filename_is_rejected(self, output_client):
        # 带路径分隔符的名字：无论路由阶段 404 还是进入端点被正则拒绝，
        # 都必须拿不到文件（绝不能 200）。安全边界由正则 + resolve/relative_to 兜底。
        assert output_client.get(_url("../secret.csv")).status_code in (400, 404)
        # 不含路径分隔符但扩展名不在白名单 → 端点明确 400。
        r = output_client.get(_url("secret.csv.bak"))
        assert r.status_code == 400

    def test_other_users_session_is_forbidden(self, output_client):
        r = output_client.get(_url("data.csv", session_id="s-other"))
        assert r.status_code == 403

    def test_missing_file_is_404(self, output_client):
        r = output_client.get(_url("missing.csv"))
        assert r.status_code == 404

    def test_html_in_workspace_root_downloads(self, output_client):
        """模型写到工作区根目录的 html 必须能下载（实测「非法文件名」bug）。

        原端点只在 outputs/ 下找文件，且扩展名白名单不含 html →
        write_text_file("index.html") 的产物点击后 400「非法文件名」。
        """
        r = output_client.get(_url("index.html"))
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["content-disposition"] == 'attachment; filename="index.html"'
        assert b"DOCTYPE html" in r.content
