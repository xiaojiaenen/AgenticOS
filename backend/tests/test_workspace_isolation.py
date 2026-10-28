"""会话工作区隔离测试。

覆盖本次改动的核心承诺：
- 工作区按 user + session 隔离，路径里不含源码目录
- 文件工具的 workspace 兜底不再是 "."（即不再等于进程 cwd）
- PPT slides 落在工作区内，且按 session 分键（不跨用户串台）
- 上传落在工作区 uploads/
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest


def _isolate(monkeypatch, tmpdir: str) -> None:
    """把 WORKSPACES_DIR 指到临时目录，避免污染真实 data/。"""
    from app.core import data_path

    monkeypatch.setattr(data_path, "WORKSPACES_DIR", pathlib.Path(tmpdir))


def test_workspace_dir_is_user_and_session_scoped(monkeypatch) -> None:
    from app.core import data_path

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        a = data_path.workspace_dir(1, "sess-a", create=True)
        b = data_path.workspace_dir(2, "sess-a", create=True)
        c = data_path.workspace_dir(1, "sess-b", create=True)

        assert a.is_dir()
        # 三者互不相同：跨用户、跨会话都隔离
        assert len({a, b, c}) == 3
        assert a.name == "ssess-a"
        assert a.parent.name == "u1"


def test_workspace_path_never_contains_source_tree(monkeypatch) -> None:
    """工作区路径里不能出现 backend/app 这类源码目录。"""
    from app.core import data_path

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        path = data_path.workspace_dir(1, "s1", create=True)
        assert "backend" not in path.parts
        assert "app" not in path.parts


def test_session_id_with_path_separators_cannot_escape(monkeypatch) -> None:
    """session_id 里带 ../ 或 / 时不能拼出越界路径。"""
    from app.core import data_path

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        evil = data_path.workspace_dir(1, "../../etc", create=True)
        root = pathlib.Path(tmp).resolve()
        assert root in evil.resolve().parents, f"escaped workspace root: {evil}"


def test_workspace_subdirs(monkeypatch) -> None:
    from app.core import data_path

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        uploads = data_path.uploads_dir(1, "s1", create=True)
        outputs = data_path.outputs_dir(1, "s1", create=True)
        slides = data_path.slides_dir(1, "s1", create=True)

        assert uploads.name == "uploads" and uploads.is_dir()
        assert outputs.name == "outputs" and outputs.is_dir()
        assert slides.name == "slides" and slides.is_dir()
        assert uploads.parent == outputs.parent == slides.parent


def test_effective_workspace_falls_back_to_session_workspace(monkeypatch) -> None:
    """文件工具的 workspace 兜底必须是会话工作区，而不是 "."。

    这是本次修复的核心：`"."` 会被 wuwei 解析成进程 cwd（容器里是 /app，
    含后端源码与全部用户数据），于是 general 模式的 AI 一 list_files(".")
    就看到了源码树和别人的网站目录。
    """
    from app.core import data_path
    from app.tools import website_file_tools as wft

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        data_path.set_current_user_id(7)
        data_path.set_current_session_id("sess-7")
        monkeypatch.setattr(data_path, "_current_website_dir", type(data_path._current_website_dir)("t", default=""))

        ws = wft._effective_workspace()
        assert ws != "."
        assert ws == str(data_path.workspace_dir(7, "sess-7"))
        assert pathlib.Path(ws, "uploads").is_dir()
        assert pathlib.Path(ws, "outputs").is_dir()


def test_effective_workspace_prefers_website_project_dir(monkeypatch) -> None:
    """website 模式已绑定项目目录时，仍然用项目目录（建站链路依赖它）。"""
    from app.core import data_path
    from app.tools import website_file_tools as wft

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        data_path.set_current_user_id(7)
        data_path.set_current_session_id("sess-7")
        project = pathlib.Path(tmp, "proj")
        project.mkdir()
        monkeypatch.setattr(
            data_path, "_current_website_dir", type(data_path._current_website_dir)("t", default=str(project))
        )
        monkeypatch.setattr(wft, "get_current_website_dir", lambda: str(project))

        assert wft._effective_workspace() == str(project)


def test_effective_workspace_raises_without_session(monkeypatch) -> None:
    """没有会话上下文时明确报错，而不是悄悄回退到 cwd。"""
    from app.core import data_path
    from app.tools import website_file_tools as wft

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        data_path.set_current_session_id("")
        monkeypatch.setattr(wft, "get_current_website_dir", lambda: "")

        with pytest.raises(RuntimeError, match="会话上下文"):
            wft._effective_workspace()


def test_ppt_slides_are_isolated_per_session(monkeypatch) -> None:
    """PPT 幻灯片目录按 session 隔离（修复前是进程级单值缓存，会串台）。"""
    from app.core import data_path
    from app.tools import ppt_tools

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        ppt_tools.reset_slides_dir_cache()

        data_path.set_current_user_id(1)
        data_path.set_current_session_id("sess-x")
        dir_x = ppt_tools._get_slides_dir()

        data_path.set_current_session_id("sess-y")
        dir_y = ppt_tools._get_slides_dir()

        assert dir_x != dir_y, "不同会话必须拿到不同目录（否则跨用户串台）"
        assert dir_x.name == "slides"
        assert dir_x.parent.name == "ssess-x"
        assert dir_y.parent.name == "ssess-y"


def test_ppt_slides_cache_is_keyed_by_session(monkeypatch) -> None:
    from app.core import data_path
    from app.tools import ppt_tools

    with tempfile.TemporaryDirectory() as tmp:
        _isolate(monkeypatch, tmp)
        ppt_tools.reset_slides_dir_cache()

        data_path.set_current_user_id(1)
        data_path.set_current_session_id("s1")
        first = ppt_tools._get_slides_dir()

        # 同会话重复调用命中缓存
        assert ppt_tools._get_slides_dir() == first

        # 清指定会话只影响该会话
        ppt_tools.reset_slides_dir_cache("s1")
        assert "s1" not in ppt_tools._slides_dir_cache
        assert ppt_tools._get_slides_dir() == first
