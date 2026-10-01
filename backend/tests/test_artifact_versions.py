"""产物版本管理测试（网站快照 + 版本列表合并）。"""

from __future__ import annotations

import pytest

from app.services import artifact_version_service as svc


@pytest.fixture(autouse=True)
def _isolated_version_dir(tmp_path, monkeypatch):
    """把版本目录指向临时路径，避免污染真实 data/。"""
    monkeypatch.setattr(svc, "WEBSITE_VERSIONS_DIR", tmp_path / "website-versions")
    return tmp_path


SAMPLE_HTML = "<!DOCTYPE html><html><body><h1>第 1 版</h1></body></html>"


class TestWebsiteSnapshot:
    @pytest.mark.anyio
    async def test_first_snapshot_is_v1(self, _isolated_version_dir):
        assert await svc.snapshot_website_version("sess-a", SAMPLE_HTML, "第一版") == 1

    @pytest.mark.anyio
    async def test_subsequent_snapshots_increment(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML)
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML)
        assert await svc.snapshot_website_version("sess-a", SAMPLE_HTML) == 3

    @pytest.mark.anyio
    async def test_sessions_are_isolated(self, _isolated_version_dir):
        assert await svc.snapshot_website_version("sess-a", SAMPLE_HTML) == 1
        assert await svc.snapshot_website_version("sess-b", SAMPLE_HTML) == 1
        # a 再快照仍然是 2，不受 b 影响
        assert await svc.snapshot_website_version("sess-a", SAMPLE_HTML) == 2

    @pytest.mark.anyio
    async def test_empty_html_skipped(self, _isolated_version_dir):
        assert await svc.snapshot_website_version("sess-a", "") is None
        assert await svc.snapshot_website_version("", SAMPLE_HTML) is None

    @pytest.mark.anyio
    async def test_snapshot_content_roundtrip(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML, "第一版")
        assert svc.load_website_version("sess-a", 1) == SAMPLE_HTML

    @pytest.mark.anyio
    async def test_load_missing_version_returns_none(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML)
        assert svc.load_website_version("sess-a", 99) is None

    @pytest.mark.anyio
    async def test_build_artifact_shape(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML, "第一版")
        artifact = svc.build_website_version_artifact("sess-a", 1, "第一版")
        assert artifact is not None
        assert artifact["type"] == "website"
        assert artifact["artifact_id"] == "sess-a_v1"
        assert artifact["preview_html"] == SAMPLE_HTML
        assert artifact["title"] == "第一版"

    def test_build_artifact_missing_returns_none(self, _isolated_version_dir):
        assert svc.build_website_version_artifact("sess-a", 7) is None


class TestListWebsiteVersions:
    @pytest.mark.anyio
    async def test_newest_first_with_title(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML, "第一版")
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML, "第二版")
        versions = svc.list_website_versions("sess-a")
        assert [v["version"] for v in versions] == [2, 1]
        assert versions[0]["title"] == "第二版"
        assert versions[0]["kind"] == "website"
        assert versions[0]["reference"] == "v2"

    def test_empty_session_returns_empty(self, _isolated_version_dir):
        assert svc.list_website_versions("sess-none") == []


class TestListSessionVersions:
    class _FakePptArtifacts:
        def __init__(self, rows):
            self.rows = rows

        async def list_for_session(self, session_id):
            return self.rows

    @pytest.mark.anyio
    async def test_merges_ppt_and_website_newest_first(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML, "网站版")
        ppt = self._FakePptArtifacts([
            {"artifact_id": "ppt-1", "title": "PPT 一版", "slide_count": 5,
             "created_at": "2026-10-01T10:00:00+08:00"},
        ])
        versions = await svc.list_session_versions("sess-a", ppt)
        kinds = [v["kind"] for v in versions]
        assert set(kinds) == {"ppt", "website"}
        # 网站快照是刚写入的（时间最新），应排在 PPT 记录（10-01）之前
        assert versions[0]["kind"] == "website"
        assert versions[-1]["kind"] == "ppt"

    @pytest.mark.anyio
    async def test_ppt_failure_does_not_break_website(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML)

        class _Broken:
            async def list_for_session(self, session_id):
                raise RuntimeError("db down")

        versions = await svc.list_session_versions("sess-a", _Broken())
        assert [v["kind"] for v in versions] == ["website"]

    @pytest.mark.anyio
    async def test_no_ppt_service_still_lists_website(self, _isolated_version_dir):
        await svc.snapshot_website_version("sess-a", SAMPLE_HTML)
        versions = await svc.list_session_versions("sess-a", None)
        assert len(versions) == 1

    @pytest.mark.anyio
    async def test_empty_session_empty_list(self, _isolated_version_dir):
        versions = await svc.list_session_versions("sess-none", None)
        assert versions == []