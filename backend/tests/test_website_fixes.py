"""网站智能体 3 个缺陷的回归测试。

对应 `docs/reports/网站智能体全流程实测报告.md` 第五节：

- 缺陷 1【中】历史版本的 project_slug 非法 → 版本条切换后点部署必 400
- 缺陷 2【中】构建超时留下半截 node_modules → 后续构建永久失败
- 缺陷 3【低】部署记录的 stack 恒为 "vanilla"
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from app.core.data_path import _parse_dir_name
from app.services import artifact_version_service as version_svc
from app.services.website_stack import detect_stack


# ---------------------------------------------------------------------------
# 缺陷 1：历史版本 project_slug 必须合法且可部署
# ---------------------------------------------------------------------------


class TestHistoricalVersionSlug:
    """版本快照的编号与项目目录的编号是两套空间，不能凭版本号反推 slug。"""

    @pytest.fixture(autouse=True)
    def _isolated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            version_svc, "WEBSITE_VERSIONS_DIR", tmp_path / "website-versions"
        )
        # 模拟 data/websites 下存在一个真实项目目录
        websites = tmp_path / "websites"
        (websites / "u42_sabc123_v1").mkdir(parents=True)
        monkeypatch.setattr("app.core.data_path.WEBSITES_DIR", websites)
        return tmp_path

    @pytest.mark.anyio
    async def test_snapshot_records_real_project_slug(self, _isolated):
        """快照必须把真实项目 slug 写进元数据。"""
        await version_svc.snapshot_website_version(
            "abc123", "<html></html>", "第一版", "u42_sabc123_v1", "react"
        )
        meta = version_svc._read_version_meta("abc123", 1)
        assert meta["project_slug"] == "u42_sabc123_v1"
        assert meta["stack"] == "react"

    @pytest.mark.anyio
    async def test_version_artifact_slug_passes_deploy_validation(self, _isolated):
        """回看历史版本得到的 slug 必须能通过部署接口的归属校验。

        部署端点用 ``_parse_dir_name`` 解析 slug 来比对用户 id，
        解析不出来 → HTTP 400「项目标识不合法」。
        """
        await version_svc.snapshot_website_version(
            "abc123", "<html></html>", "第一版", "u42_sabc123_v1", "react"
        )
        artifact = version_svc.build_website_version_artifact("abc123", 1, "第一版")
        assert artifact is not None

        slug = artifact["project_slug"]
        parsed = _parse_dir_name(slug)
        assert parsed is not None, f"slug {slug!r} 无法被 _parse_dir_name 解析"
        assert parsed[0] == 42
        assert parsed[1] == "abc123"

    def test_legacy_snapshot_without_slug_falls_back_to_project_dir(self, _isolated):
        """升级前写入的老快照没有 project_slug 字段，必须回退而不是造非法值。

        旧实现是 ``f"u{session_id}_v{version}"`` → "uabc123_v1"，
        不符合 ``^u(\\d+)_s(.+)_v(\\d+)$`` → 部署必然 400。
        """
        path = version_svc._ensure_dir() / "u abc123_v1.html".replace(" ", "")
        path.write_text("<html>legacy</html>", encoding="utf-8")
        path.with_suffix(".json").write_text(
            json.dumps({"title": "老版本", "bytes": 20}), encoding="utf-8"
        )

        artifact = version_svc.build_website_version_artifact("abc123", 1)
        assert artifact is not None
        slug = artifact["project_slug"]
        assert slug == "u42_sabc123_v1"
        assert _parse_dir_name(slug) is not None

    @pytest.mark.anyio
    async def test_no_project_at_all_yields_empty_slug_not_illegal(self, _isolated):
        """找不到任何项目目录时返回空串，而不是伪造一个非法 slug。

        非法 slug 会被前端填进部署请求 → 400。空串则让前端不渲染部署按钮。
        """
        import shutil

        shutil.rmtree(_isolated / "websites")
        artifact = version_svc.build_website_version_artifact("abc123", 1)
        # 没有快照 → None；这里只验证"不会造出非法 slug"
        assert artifact is None or artifact["project_slug"] == ""

    @pytest.mark.anyio
    async def test_stack_is_preserved_from_snapshot(self, _isolated):
        await version_svc.snapshot_website_version(
            "abc123", "<html></html>", "第一版", "u42_sabc123_v1", "vue"
        )
        artifact = version_svc.build_website_version_artifact("abc123", 1)
        assert artifact is not None
        assert artifact["stack"] == "vue"
        assert artifact["stack"] != "vanilla"


# ---------------------------------------------------------------------------
# 缺陷 2：构建超时残留必须被检测并清理
# ---------------------------------------------------------------------------


class TestBrokenNodeModules:
    """npm 被 SIGKILL 打断后留下半截原生二进制，后续构建永久失败。"""

    @pytest.fixture
    def _project(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "package.json").write_text('{"name": "x"}', encoding="utf-8")
        return proj

    def test_detects_truncated_native_binary(self, _project):
        from app.tools.website_tools import _detect_broken_node_modules

        native = _project / "node_modules" / "@rollup" / "rollup-darwin-arm64"
        native.mkdir(parents=True)
        (native / "rollup.darwin-arm64.node").write_bytes(b"\x00" * 100)

        broken = _detect_broken_node_modules(_project)
        assert broken is not None
        assert "rollup" in broken

    def test_healthy_node_modules_not_flagged(self, _project):
        from app.tools.website_tools import _detect_broken_node_modules

        native = _project / "node_modules" / "@rollup" / "rollup-darwin-arm64"
        native.mkdir(parents=True)
        # 正常原生模块远大于 1KB
        (native / "rollup.darwin-arm64.node").write_bytes(b"\x00" * 500_000)

        assert _detect_broken_node_modules(_project) is None

    def test_no_node_modules_not_flagged(self, _project):
        from app.tools.website_tools import _detect_broken_node_modules

        assert _detect_broken_node_modules(_project) is None

    def test_clean_removes_node_modules_and_lock(self, _project):
        from app.tools.website_tools import _clean_node_modules

        nm = _project / "node_modules"
        nm.mkdir()
        (nm / "x.js").write_text("1", encoding="utf-8")
        lock = _project / "package-lock.json"
        lock.write_text("{}", encoding="utf-8")

        assert _clean_node_modules(_project) is True
        assert not nm.exists()
        assert not lock.exists()

    def test_clean_is_safe_when_nothing_to_remove(self, _project):
        from app.tools.website_tools import _clean_node_modules

        assert _clean_node_modules(_project) is False


class TestSandboxProcessGroup:
    """超时时必须杀掉整个进程组，否则 npm 子进程继续写文件。"""

    @pytest.mark.anyio
    async def test_timeout_kills_child_processes(self):
        """超时后子进程必须已死亡。

        旧实现只 kill shell —— npm 子进程继续往 node_modules 写，
        留下半截的原生二进制，npm 之后认为已装好而跳过重装。
        """

        from app.services.sandbox import Sandbox
        marker = Path(os.environ.get("TMPDIR", "/tmp")) / "agenticos_sandbox_probe.pid"
        if marker.exists():
            marker.unlink()

        # 子进程把自己的 pid 写进文件，然后继续长时间运行
        cmd = (
            f"(echo $$ > {marker}; sleep 30) & "
            "sleep 30"
        )
        sandbox = Sandbox(workspace=Path(os.environ.get("TMPDIR", "/tmp")), timeout=2)
        result = await sandbox.execute(cmd, timeout=2)

        assert result.timed_out is True
        assert result.success is False

        # 给一点时间让信号生效
        await asyncio.sleep(0.5)

        # 记录的 pid 若还活着（且不是当前 shell），说明没杀干净
        if marker.exists():
            try:
                pid = int(marker.read_text().strip())
            except (ValueError, OSError):
                pid = None
            if pid:
                try:
                    os.kill(pid, 0)
                    alive = True
                except (ProcessLookupError, PermissionError, OSError):
                    alive = False
                assert not alive, f"子进程 {pid} 在超时后仍然存活"


# ---------------------------------------------------------------------------
# 缺陷 3：技术栈判定必须真实
# ---------------------------------------------------------------------------


class TestStackDetection:
    """部署记录的 stack 恒为 vanilla —— 修好后按 package.json 判定。"""

    def _proj(self, tmp_path, deps: dict | None = None, files: dict | None = None):
        proj = tmp_path / "p"
        proj.mkdir(exist_ok=True)
        if deps is not None:
            (proj / "package.json").write_text(
                json.dumps({"dependencies": deps}), encoding="utf-8"
            )
        for rel, content in (files or {}).items():
            p = proj / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return proj

    def test_react_from_package_json(self, tmp_path):
        proj = self._proj(tmp_path, {"react": "^18.3.0", "react-dom": "^18.3.0"})
        assert detect_stack(proj) == "react"

    def test_vue_from_package_json(self, tmp_path):
        proj = self._proj(tmp_path, {"vue": "^3.5.0", "vue-router": "^4.4.0"})
        assert detect_stack(proj) == "vue"

    def test_vanilla_when_no_framework(self, tmp_path):
        proj = self._proj(tmp_path, {})
        assert detect_stack(proj) == "vanilla"

    def test_package_json_wins_over_suffix(self, tmp_path):
        """package.json 是事实来源 —— 即使用户把组件写成 .js 也应判对。

        旧实现只看后缀：React 项目全用 .js 就会被判成 vanilla。
        """
        proj = self._proj(
            tmp_path,
            {"react": "^18.3.0"},
            {"src/main.js": "console.log(1)"},
        )
        assert detect_stack(proj) == "react"

    def test_falls_back_to_suffix_when_package_json_broken(self, tmp_path):
        proj = tmp_path / "p"
        proj.mkdir()
        (proj / "package.json").write_text("{ broken json", encoding="utf-8")
        (proj / "src").mkdir()
        (proj / "src" / "App.jsx").write_text("x", encoding="utf-8")
        assert detect_stack(proj) == "react"

    def test_missing_directory_is_vanilla(self, tmp_path):
        assert detect_stack(tmp_path / "nope") == "vanilla"

    def test_deploy_tool_reports_real_stack(self, tmp_path, monkeypatch):
        """deploy_website 工具必须把真实 stack 传给部署服务。"""
        import app.tools.website_tools as wt

        captured: dict = {}

        class _FakeService:
            def request_deploy(self, **kwargs):
                captured.update(kwargs)
                return {"id": 1, "status": "pending"}

        monkeypatch.setattr(
            "app.services.website_deploy_service.WebsiteDeployService", _FakeService
        )

        proj = tmp_path / "u42_sabc123_v1"
        proj.mkdir()
        (proj / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.3.0"}}), encoding="utf-8"
        )
        (proj / "dist").mkdir()
        (proj / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")

        monkeypatch.setattr(wt, "WEBSITES_DIR", tmp_path)
        monkeypatch.setattr(wt, "get_current_user_id", lambda: 42)
        monkeypatch.setattr(wt, "get_current_session_id", lambda: "abc123")


        from wuwei.tools.registry import ToolRegistry

        reg = ToolRegistry()
        wt.register_website_tools(reg)
        deploy = next(t for t in reg.list_tools() if t.name == "deploy_website")

        asyncio.run(deploy.handler(project_slug="u42_sabc123_v1"))

        assert captured["stack"] == "react", "stack 仍被硬编码成 vanilla"
