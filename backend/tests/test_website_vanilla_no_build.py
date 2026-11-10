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
    """源码里有裸模块导入 → 浏览器无法直接跑，必须打包。

    判据是「浏览器能不能直接执行」，不是「有没有 package.json 依赖」。
    裸导入（``import { ref } from 'vue'``）才真正需要打包器解析。
    """
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    _write(tmp_path / "js" / "main.js", "import { ref } from 'vue'\nconsole.log(ref)")
    assert _is_vanilla_static(tmp_path) is False


def test_template_shipped_vite_config_does_not_force_build(tmp_path: Path) -> None:
    """模板自带 package.json(vite) + vite.config.js，但页面是纯静态的 → 免构建。

    回归背景：内网报 ``npm install`` 失败（EAI_AGAIN registry.npmmirror.com）。
    vanilla 模板的 ``package.json`` 只有 ``vite`` 这个 devDependency
    （用于本地 dev server），``vite.config.js`` 里 ``import ... from 'vite'``
    也只是 Node 侧配置 —— 页面本身一行裸模块导入都没有。早先按「有任何
    依赖就走 npm」判定，于是纯静态站也去下载依赖，内网必挂。
    """
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    _write(tmp_path / "css" / "style.css", "h1{color:red}")
    _write(tmp_path / "js" / "main.js", "document.querySelector('h1')")
    _write(
        tmp_path / "package.json",
        '{"name":"x","devDependencies":{"vite":"^6.0.0"}}',
    )
    _write(tmp_path / "vite.config.js", "import { defineConfig } from 'vite'\nexport default defineConfig({})")
    assert _is_vanilla_static(tmp_path) is True


def test_relative_imports_are_still_static(tmp_path: Path) -> None:
    """相对路径导入浏览器自己能取，不算裸模块。"""
    _write(tmp_path / "index.html", '<script type="module" src="./js/main.js"></script>')
    _write(tmp_path / "js" / "main.js", "import { helper } from './helper.js'\nhelper()")
    _write(tmp_path / "js" / "helper.js", "export const helper = () => {}")
    assert _is_vanilla_static(tmp_path) is True


def test_node_only_config_files_are_ignored(tmp_path: Path) -> None:
    """构建工具配置文件只在 Node 侧执行，不构成「需要打包」的证据。"""
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    _write(tmp_path / "tailwind.config.js", "module.exports = {}")
    _write(tmp_path / "postcss.config.js", "import x from 'autoprefixer'\nexport default {}")
    assert _is_vanilla_static(tmp_path) is True


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
