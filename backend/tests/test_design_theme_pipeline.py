"""设计主题链路回归：对比度审计 / apply_design_theme / 换肤一致性。

三条链路共用一份资产（data/design-themes/*.css，236 个主题）：

- **PPT**：theme_token_resolver 读 css → svg 变量替换；
- **网站**：``apply_design_theme`` 把主题 :root 整块写进入口样式表，
  页面里所有 var(--token) 自动换肤 —— AI 不再自己发明颜色。

对比度是设计质量的一等公民（来源 guanmo-ai/design-style 的实测哲学）：
主题在生成时就按对比度选色（convert_design_style），工具返回时再审计一次。
"""
from __future__ import annotations

import shutil

import pytest

from app.services.ppt.contrast import (
    audit_theme_tokens,
    contrast_ratio,
    grade,
    parse_theme_css,
    relative_luminance,
)


@pytest.fixture(autouse=True)
def real_themes_dir(monkeypatch):
    """测试环境的 AGENT_DATA_DIR 会把 data/ 重定向到临时目录 ——
    这里把主题目录指回真仓库的 data/design-themes（只读使用）。"""
    from pathlib import Path as _P

    from app.services.ppt import theme_token_resolver

    real = _P(__file__).resolve().parents[2] / "data" / "design-themes"
    monkeypatch.setattr(theme_token_resolver, "_THEMES_DIR", real)
    yield real


class TestContrastMath:
    def test_official_wcag_samples(self) -> None:
        """WCAG 2.1 官方样例值 —— 算错对比度等于没查。"""
        # 黑/白 = 21:1（规范上限）
        assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
        # 规范样例：#777 vs #fff ≈ 4.48（文档引用值）
        assert 4.4 < contrast_ratio("#777777", "#ffffff") < 4.6

    def test_relative_luminance_bounds(self) -> None:
        assert relative_luminance("#000000") == 0.0
        assert round(relative_luminance("#ffffff"), 4) == 1.0

    def test_grade_thresholds(self) -> None:
        assert grade(21.0) == "AAA"
        assert grade(4.5) == "AA"
        assert grade(4.4) == "AA-Large"
        assert grade(3.0) == "AA-Large"
        assert grade(2.9) == "FAIL"


class TestThemeParsing:
    def test_parse_real_theme(self, real_themes_dir) -> None:
        """真实主题文件能解析出全部 token（ink-wash 是自动转换的）。"""
        from app.services.ppt.theme_token_resolver import list_available_themes

        themes = list_available_themes()
        assert len(themes) > 200, "主题库应有 200+ 主题"
        assert "ink-wash" in themes and "art-deco" in themes, "design-style 新风格应已入库"

        css_file = real_themes_dir / "ink-wash.css"
        tokens = parse_theme_css(css_file.read_text(encoding="utf-8"))
        for key in ("--bg", "--fg" if "--fg" in tokens else "--text-1", "--accent", "--font-sans"):
            assert key in tokens, f"主题缺 {key}"
        # 水墨风格的底是米纸色、正文是墨色（风格保真）
        assert tokens.get("--bg", "").lower() == "#f2ede1"
        assert tokens.get("--text-1", "").lower() == "#141413"


class TestAudit:
    def test_dark_theme_passes(self, real_themes_dir) -> None:
        """art-deco 黑底金字 —— 自动转换后对比度必须达标（AAA 级背景）。"""
        tokens = parse_theme_css((real_themes_dir / "art-deco.css").read_text(encoding="utf-8"))
        audit = audit_theme_tokens(tokens)
        assert audit["pass"] is True, f"art-deco 审计未通过: {audit['summary']}"
        # 黑底正文字对比度必须 AAA
        fg_pair = next(p for p in audit["pairs"] if p["pair"] == "--text-1 on --bg")
        assert fg_pair["ratio"] >= 7.0

    def test_audit_flags_illegible_combo(self) -> None:
        """正文与背景对比不足 → 必须标 FAIL（这是审计存在的意义）。"""
        tokens = {
            "--bg": "#ffffff",
            "--surface": "#fefefe",
            "--text-1": "#bbbbbb",  # 白底浅灰字 —— 读不清
            "--text-2": "#999999",
            "--accent": "#3b82f6",
        }
        audit = audit_theme_tokens(tokens)
        assert audit["pass"] is False
        assert any(not p["pass"] for p in audit["pairs"])


class TestApplyDesignTheme:
    @pytest.fixture()
    def project(self, tmp_path):
        """造一个 vanilla 项目（与真模板同构的入口 css）。"""
        src = tmp_path / "template"
        (src / "css").mkdir(parents=True)
        (src / "css" / "style.css").write_text(
            "/* === Design Tokens === */\n:root {\n  --bg: #ffffff;\n  --text-1: #1d1d1f;\n  --accent: #0071e3;\n}\n"
            "\nbody { color: var(--text-1); }\n",
            encoding="utf-8",
        )
        (src / "index.html").write_text("<html><body>hi</body></html>", encoding="utf-8")
        proj = tmp_path / "websites" / "u1_stest_v1"
        shutil.copytree(src, proj)
        return proj

    def test_replaces_tokens_block(self, project, monkeypatch):
        """应用主题后入口 css 的 :root 变量换成主题值，其余内容不动。"""
        from app.core import data_path as dp
        # 工具在 register_website_tools 闭包内 —— 用空 registry 实例化再取 handler
        from wuwei.tools import ToolRegistry
        from app.tools.website_tools import register_website_tools

        reg = ToolRegistry()
        register_website_tools(reg)
        tool = next(t for t in reg.list_tools() if t.name == "apply_design_theme")

        monkeypatch.setattr(dp, "get_current_website_dir", lambda: str(project))
        monkeypatch.setattr(dp, "get_current_user_id", lambda: 1)
        monkeypatch.setattr(dp, "get_current_session_id", lambda: "test")

        import asyncio

        result = asyncio.run(tool.handler(theme_name="ink-wash"))
        assert "已应用" in result and "WCAG" in result

        css = (project / "css" / "style.css").read_text(encoding="utf-8")
        assert "#f2ede1" in css, "水墨主题的米纸底应写进 :root"
        assert "var(--text-1)" in css, "主题块之外的引用代码不应被动"
        assert "--accent-3" in css, "主题的全部 token（含三级强调色）应一并写入"

    def test_unknown_theme_lists_candidates(self, project, monkeypatch):
        from app.core import data_path as dp
        from wuwei.tools import ToolRegistry
        from app.tools.website_tools import register_website_tools

        reg = ToolRegistry()
        register_website_tools(reg)
        tool = next(t for t in reg.list_tools() if t.name == "apply_design_theme")
        monkeypatch.setattr(dp, "get_current_website_dir", lambda: str(project))

        import asyncio

        result = asyncio.run(tool.handler(theme_name="不存在的主题xyz"))
        assert "没有名为" in result
        assert "ink-wash" in result, "错误信息要给出可用候选（工具即发现机制）"

    def test_no_project_gives_actionable_error(self, monkeypatch):
        from app.core import data_path as dp
        from wuwei.tools import ToolRegistry
        from app.tools.website_tools import register_website_tools

        reg = ToolRegistry()
        register_website_tools(reg)
        tool = next(t for t in reg.list_tools() if t.name == "apply_design_theme")
        monkeypatch.setattr(dp, "get_current_website_dir", lambda: "")
        monkeypatch.setattr(dp, "get_current_user_id", lambda: 0)
        monkeypatch.setattr(dp, "get_current_session_id", lambda: "")

        import asyncio

        result = asyncio.run(tool.handler(theme_name="ink-wash"))
        assert "copy_template" in result

    def test_tool_whitelisted_for_website_mode(self):
        """新工具必须进 website 模式的白名单 —— load_skill 的教训：
        注册了但被 allowed_tools 裁掉，模型就看不见。"""
        from app.services.agent_profile_service import AgentProfileService

        allowed = AgentProfileService._compute_allowed_tools(
            "website",
            enabled_catalog_names=set(),  # website 的模式级工具走自动发现
        )
        assert "apply_design_theme" in allowed, (
            "apply_design_theme 不在 website 白名单里：会被工厂裁剪，模型看不到"
        )
        assert "list_design_themes" in allowed
