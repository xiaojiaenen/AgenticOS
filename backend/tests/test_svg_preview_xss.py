"""PPT 预览 SVG 白名单净化回归（存储型 XSS 防护）。

旧实现用正则剥 `<script>` / `on*` / `javascript:`，可被 HTML 实体编码、
`<script x=">">`、`xlink:href` 等绕过；现在走 lxml 元素/属性白名单。
"""

from __future__ import annotations

from app.api.v1.endpoints.agent import _sanitize_svg


def test_script_element_and_children_removed():
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><rect width="10" height="10"/></svg>'
    out = _sanitize_svg(svg)
    assert "<script" not in out.lower()
    assert "alert(1)" not in out
    assert "<rect" in out


def test_event_attrs_and_encoded_js_url_removed():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        '<a href="javascript&#58;alert(1)">x</a>'
        '<use xlink:href="data:text/html;base64,PHNjcmlwdD4="/>'
        '</svg>'
    )
    out = _sanitize_svg(svg)
    assert "onload" not in out.lower()
    assert "javascript" not in out.lower()
    assert "data:text/html" not in out.lower()


def test_foreignobject_and_animate_removed():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<foreignObject><div xmlns="http://www.w3.org/1999/xhtml">evil</div></foreignObject>'
        '<animate attributeName="x" values="1;2"/><circle cx="1" cy="1" r="1"/>'
        '</svg>'
    )
    out = _sanitize_svg(svg)
    assert "foreignObject" not in out
    assert "animate" not in out.lower()
    assert "evil" not in out
    assert "<circle" in out


def test_legit_svg_survives():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">'
        '<defs><linearGradient id="g"><stop offset="0" stop-color="#fff"/></linearGradient></defs>'
        '<rect width="1280" height="720" fill="url(#g)"/>'
        '<text x="10" y="20" font-size="24" fill="#000">标题</text></svg>'
    )
    out = _sanitize_svg(svg)
    assert "viewBox" in out
    assert "<rect" in out and "<text" in out and "标题" in out
    assert "linearGradient" in out


def test_malformed_svg_degrades_to_safe_text():
    out = _sanitize_svg('<svg onload="alert(1)"><rect>')
    # 退化路径：剥掉所有标签后转义（本例标签占满整串 → 结果是空串）。
    # 关键是绝不能让不可信内容原样进 HTML。
    assert "<svg" not in out.lower()
    assert "onload" not in out.lower()
    assert "<rect" not in out
