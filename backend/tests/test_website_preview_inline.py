"""网站预览内联资源回归：剥离 type="module" / crossorigin。

真实故障（用户截图：预览面板全白，dist 明明构建成功）：
Vite 产出的 index.html 是
    <script type="module" crossorigin src="./assets/index-xxx.js"></script>
后端 _inline_dist_assets 把 JS 内联成 <script>，但**保留了 type="module"**
——内联 module script 在 srcdoc iframe 里走延迟执行 + 严格模式，
Vite 产物虽是 IIFE 但 module 语义下会受 currentScript/import 约束影响，
实测整段不执行 → 白屏。crossorigin 在内联脚本上也无意义且可能触发额外检查。

修复：内联时剥掉这两个属性并压掉多余空白。
"""
from __future__ import annotations

from pathlib import Path

from app.services.agent.artifacts import ArtifactFactory


class _Dummy(ArtifactFactory):
    """只借用静态方法，不构造宿主依赖。"""


def _make_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("(function(){console.log('ok')})()", encoding="utf-8")
    (dist / "assets" / "app.css").write_text("body{color:#333}", encoding="utf-8")
    return dist


def test_strips_module_and_crossorigin(tmp_path):
    dist = _make_dist(tmp_path)
    html = (
        '<!DOCTYPE html><html><head>'
        '<script type="module" crossorigin src="./assets/app.js"></script>'
        '<link rel="stylesheet" crossorigin href="./assets/app.css">'
        '</head><body><div id="app"></div></body></html>'
    )
    out = _Dummy._inline_dist_assets(dist, html)

    # 脚本被内联且不再带 module / crossorigin
    assert "type=\"module\"" not in out
    assert "<script>" in out
    assert "(function(){console.log('ok')})()" in out
    # 不再残留外部 src 引用（srcdoc 里解析不了）
    assert 'src="./assets/app.js"' not in out
    # CSS 同样内联
    assert "<style>body{color:#333}</style>" in out
    assert 'href="./assets/app.css"' not in out


def test_strips_module_with_absolute_path(tmp_path):
    """绝对路径（base: '/'）形态同样处理。"""
    dist = _make_dist(tmp_path)
    html = '<html><head><script type="module" src="/assets/app.js"></script></head><body></body></html>'
    out = _Dummy._inline_dist_assets(dist, html)
    assert 'type="module"' not in out
    assert 'src="/assets/app.js"' not in out
    assert "<script>(function()" in out


def test_keeps_external_scripts_untouched(tmp_path):
    """外链脚本（http/https/data:）保持原样 —— 它们能自己解析。"""
    dist = _make_dist(tmp_path)
    html = '<html><head><script src="https://cdn.example.com/x.js"></script></head><body></body></html>'
    out = _Dummy._inline_dist_assets(dist, html)
    assert 'src="https://cdn.example.com/x.js"' in out


def test_missing_asset_leaves_tag(tmp_path):
    """资源不存在时不吞掉标签（保留原始引用便于排查）。"""
    dist = _make_dist(tmp_path)
    html = '<html><head><script src="./assets/nope.js"></script></head><body></body></html>'
    out = _Dummy._inline_dist_assets(dist, html)
    assert "./assets/nope.js" in out
