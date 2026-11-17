"""视觉风格层与内容工具（风格注册表 / LaTeX 校验 / 文字测量 / 图表选型）。

用户提问「主题只是改了颜色吗，我觉得有的样式也不一样啊」—— 确认了本地
缺一层：上游 ppt-master 把「配色主题」和「视觉风格」明确分开，风格管
形状语言 / 装饰密度 / 留白节奏 / 纹理层次。本文件锁住这层的关键契约。
"""
from __future__ import annotations

import pytest


class TestVisualStyles:
    def test_all_styles_have_required_fields(self):
        from app.services.ppt.visual_styles_data import VISUAL_STYLES

        assert len(VISUAL_STYLES) >= 18
        for sid, s in VISUAL_STYLES.items():
            assert s["id"] == sid
            assert s.get("label_zh"), f"{sid} 缺中文标签"
            assert s.get("category") in {
                "corporate", "editorial", "expressive", "hand_drawn", "specialty"
            }, f"{sid} 分类异常: {s.get('category')}"
            # 四个规则维度必须都有内容（否则风格形同虚设）
            assert s.get("shape"), f"{sid} 缺形状规则"
            assert s.get("typography"), f"{sid} 缺字体规则"
            assert s.get("color_usage"), f"{sid} 缺配色纪律"
            assert s.get("texture"), f"{sid} 缺纹理规则"

    def test_style_carries_no_hex_colors(self):
        """风格只管形态，**不得携带色值** —— 配色一律来自主题，否则两层会打架。"""
        import re

        from app.services.ppt.visual_styles_data import VISUAL_STYLES

        hex_re = re.compile(r"#[0-9a-fA-F]{6}\b")
        for sid, s in VISUAL_STYLES.items():
            blob = " ".join(
                [s.get("summary", "")]
                + s.get("shape", [])
                + s.get("typography", [])
                + s.get("color_usage", [])
                + s.get("texture", [])
            )
            found = hex_re.findall(blob)
            assert not found, f"{sid} 的规则里出现了色值 {found[:3]}（应引用主题而非写死）"

    def test_prompt_block_has_real_newlines(self):
        """提示词块必须是真换行 —— 转义层数写错会输出字面量 \\n。"""
        from app.services.ppt.visual_styles_data import style_prompt_block

        block = style_prompt_block("swiss-minimal")
        assert block
        assert "\\n" not in block, "提示词块里出现字面量反斜杠 n（转义层数错了）"
        assert "\n" in block
        assert "瑞士极简" in block

    def test_unknown_style_returns_empty(self):
        from app.services.ppt.visual_styles_data import style_prompt_block

        assert style_prompt_block("no-such-style") == ""


class TestDesignCatalogInjection:
    def test_unselected_injects_catalog(self):
        from app.services.agent.prompts import inject_design_catalog

        injected = inject_design_catalog("做个ppt")
        assert "视觉风格目录" in injected
        assert "swiss-minimal" in injected

    def test_selected_injects_full_rules(self):
        from app.services.agent.prompts import inject_design_catalog

        injected = inject_design_catalog("做个ppt", visual_style="memphis")
        assert "已选定的视觉风格" in injected
        assert "孟菲斯" in injected
        # 选定的风格不该再注入整份目录让模型自己挑
        assert "视觉风格目录" not in injected

    def test_unknown_id_degrades_to_catalog(self):
        from app.services.agent.prompts import inject_design_catalog

        injected = inject_design_catalog("x", visual_style="not-exist")
        assert "未知 id: not-exist" in injected
        assert "swiss-minimal" in injected

    def test_strip_still_works_with_style_injected(self):
        """注入风格不能破坏原有的「剥掉注入段」能力（用户消息回显依赖它）。"""
        from app.services.agent.prompts import inject_design_catalog, strip_injected_catalog

        raw = "做个 3 页的 PPT"
        assert strip_injected_catalog(inject_design_catalog(raw, visual_style="editorial")) == raw


class TestLatexValidation:
    def test_valid_formula(self):
        from app.services.ppt.latex_render import validate_latex

        ok, err = validate_latex(r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}")
        assert ok, err

    def test_invalid_formula_reports_error(self):
        from app.services.ppt.latex_render import validate_latex

        ok, err = validate_latex(r"\frac{a}{b")
        assert not ok
        assert err

    def test_empty_formula_rejected(self):
        from app.services.ppt.latex_render import validate_latex

        ok, _ = validate_latex("   ")
        assert not ok


class TestTextMeasure:
    def test_cjk_is_one_em(self):
        from app.services.ppt.text_measure import measure_text

        text = "中文测试文字"
        assert measure_text(text, 20) == pytest.approx(len(text) * 20)

    def test_latin_narrower_than_cjk(self):
        from app.services.ppt.text_measure import measure_text

        # 同样字符数，英文应更窄
        assert measure_text("abcdefghij", 20) < measure_text("一二三四五六七八九十", 20)

    def test_wrap_respects_max_width(self):
        from app.services.ppt.text_measure import measure_text, wrap_text

        text = "AgenticOS 是一个通用 AI 智能体平台，支持多模式对话与审批流程。"
        lines = wrap_text(text, 20, 300)
        assert len(lines) > 1
        for line in lines:
            assert measure_text(line, 20) <= 300 + 20  # 允许一个字的误差

    def test_no_closing_punctuation_at_line_start(self):
        """标点禁则：收尾标点不能被推到行首。"""
        from app.services.ppt.text_measure import wrap_text

        text = "这是一个测试，用来检查标点禁则是否正确处理"
        for line in wrap_text(text, 20, 180):
            assert not line.startswith(("，", "。", "、", ",", ".")), f"行首出现标点: {line!r}"

    def test_fits_reports_overflow(self):
        """高度不够时必须报溢出（宽度可以靠换行解决，高度不能）。"""
        from app.services.ppt.text_measure import fits

        text = "这是一个很长的标题需要换行显示"
        ok, detail = fits(text, 40, 200, max_height=100)
        assert not ok
        assert detail["lines"] > 1
        assert detail["overflow_height"] > 0

    def test_fits_ok_when_wrapping_suffices(self):
        """宽度不够但换行能装下 → 算放得下。"""
        from app.services.ppt.text_measure import fits

        ok, detail = fits("这是一个标题", 30, 100)
        assert ok, detail
        assert detail["lines"] > 1


class TestChartCatalog:
    def test_catalog_loaded(self):
        from app.services.ppt.chart_catalog import catalog_size

        assert catalog_size() >= 60

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("占比", "pie"),
            ("趋势", "line"),
            ("流程", "chevron"),
            ("四象限", "quadrant"),
        ],
    )
    def test_chinese_query_maps_to_english_templates(self, query, expected):
        from app.services.ppt.chart_catalog import search_chart_templates

        keys = [r["key"] for r in search_chart_templates(query, limit=5)]
        assert any(expected in k for k in keys), f"「{query}」没命中 {expected}: {keys}"

    def test_get_template_svg(self):
        from app.services.ppt.chart_catalog import get_chart_template

        svg = get_chart_template("bar_chart")
        assert svg and svg.lstrip().startswith("<svg")

    def test_unknown_template_returns_none(self):
        from app.services.ppt.chart_catalog import get_chart_template

        assert get_chart_template("no_such_chart") is None
