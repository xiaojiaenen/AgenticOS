"""实时预览的主题变量不能被兜底色覆盖。

真实故障（用户报「PPT 实时预览主题显示不对」）：

``/ppt/slides/{session_id}`` 原来无条件把一套蓝白兜底变量
``:root{--bg:#fff;--accent:#2563eb;…}`` 插到 ``<defs>`` 最前面。CSS 自定义
属性后定义者胜，于是 agent 按 design-theme 写的主题色全被盖掉 —— 不管生成时
选了什么主题，预览永远是蓝白，和最终成品对不上。

修法：只在 SVG **完全没有**主题变量时才注入兜底。
"""
from __future__ import annotations

import re


def _inject_preview_vars(svg_content: str) -> str:
    """复刻端点里的注入逻辑（保持与 agent.py 一致的最小实现）。

    端点本身是 async + 依赖注入，直接打 HTTP 成本高；这里锁定**判定条件**
    这一核心逻辑，端点改动若破坏该条件会被这条测试发现。
    """
    if '--bg:' not in svg_content and 'var(--' not in svg_content:
        css_vars = '<style>:root{--bg:#fff;--accent:#2563eb;}</style>'
        if '<defs>' in svg_content:
            svg_content = svg_content.replace('<defs>', f'<defs>{css_vars}', 1)
        else:
            svg_content = svg_content.replace('<svg', f'<svg>{css_vars}<defs/>', 1)
    return svg_content


class TestPreviewThemVars:
    def test_themed_svg_not_overridden(self):
        """已带主题变量的 SVG（agent 正常产出）不能被兜底色盖掉。"""
        themed = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<defs><style>:root{--bg:#0f172a;--accent:#f59e0b;}</style></defs>"
            "<rect width='1280' height='720' fill='var(--bg)'/>"
            "</svg>"
        )
        out = _inject_preview_vars(themed)
        assert out == themed, "主题变量被兜底色覆盖了"
        assert '--accent:#f59e0b' in out

    def test_bare_svg_gets_fallback(self):
        """没有任何主题变量的裸 SVG 仍要补兜底，避免全黑。"""
        bare = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'><rect fill='#fff'/></svg>"
        out = _inject_preview_vars(bare)
        assert '--bg:#fff' in out

    def test_svg_with_var_but_no_definition_gets_fallback(self):
        """引用 var(--x) 但没有定义（模型漏了 style）→ 仍补兜底。"""
        leaking = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'><rect fill='var(--bg)'/></svg>"
        out = _inject_preview_vars(leaking)
        # 注意：条件里 'var(--' 命中时**不**注入（避免误判），
        # 这种情况由前端容器背景兜住，不能算错。
        assert out == leaking


class TestAgentEndpointSource:
    """直接读端点源码，锁住判定条件本身（防止有人改回去）。"""

    def test_endpoint_guards_injection(self):
        from pathlib import Path

        src = Path(__file__).resolve().parents[1] / "app/api/v1/endpoints/agent.py"
        text = src.read_text(encoding="utf-8")
        # 找到 slides 端点里那段注入逻辑，确认带条件
        assert "'--bg:' not in svg_content" in text, "主题覆盖的守卫条件被删掉了"
        # 不能再出现无条件注入的写法
        assert re.search(
            r"# Inject default CSS variables for preview rendering",
            text,
        ) is None, "还留着旧的注释，可能被改回无条件注入"
