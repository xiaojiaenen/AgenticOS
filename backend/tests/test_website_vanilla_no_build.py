"""vanilla 模板免构建：静态站直接把源文件镜像成 dist。

背景（用户原话）："构建网站，不需要吧" —— 纯 HTML/CSS/JS 的网站
本来就不该跑 npm install + vite build。
"""

from __future__ import annotations

from pathlib import Path

from app.tools.website_tools import _emit_static_dist, _is_vanilla_static


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_pure_static_project_is_vanilla(tmp_path: Path) -> None:
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    _write(tmp_path / "css" / "style.css", "h1{color:red}")
    _write(tmp_path / "js" / "main.js", "console.log(1)")
    assert _is_vanilla_static(tmp_path) is True


def test_project_with_real_bundler_is_not_vanilla(tmp_path: Path) -> None:
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    _write(
        tmp_path / "package.json",
        '{"name":"x","devDependencies":{"vite":"^5.0.0"}}',
    )
    assert _is_vanilla_static(tmp_path) is False


def test_static_entry_without_package_json_is_not_vanilla(tmp_path: Path) -> None:
    # 没有 index.html 就不算静态站点，避免把半成品当成品发布
    _write(tmp_path / "main.js", "console.log(1)")
    assert _is_vanilla_static(tmp_path) is False


def test_emit_static_dist_mirrors_sources(tmp_path: Path) -> None:
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    _write(tmp_path / "css" / "style.css", "h1{color:red}")
    _write(tmp_path / "js" / "main.js", "console.log(1)")

    message = _emit_static_dist(tmp_path)

    dist = tmp_path / "dist"
    assert (dist / "index.html").is_file()
    assert (dist / "css" / "style.css").is_file()
    assert (dist / "js" / "main.js").is_file()
    # 源码本身不该被搬进 dist，否则预览会重复一层目录
    assert not (dist / "dist").exists()
    assert "无需" in message or "静态" in message
