"""SVG 属性引号冲突修复回归。

真实故障（用户报「PPT 导出每一页都空白」）：

模型写出

    font-family=''Noto Serif SC','Playfair Display',serif'

外层单引号包属性值，值内部又嵌了单引号。XML 解析器读到第一个内层单引号
就认定属性结束，后面的 ``Noto Serif SC`` 成了游离 token，整个文档
not well-formed → 导出时 ``ET.parse`` 抛错、该页被 skip → pptx 每页空白。

``sanitize_svg_xml`` 原本只处理**文本内容**里的 ``&``/``<``，属性值里的
引号冲突没人管，所以这类 SVG 能落库、能预览，就是导不出。
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from app.services.ppt_artifact_service import (
    _fix_attribute_quote_conflicts,
    sanitize_svg_xml,
)


class TestQuoteConflictRepair:
    def test_single_quoted_font_family_list(self):
        """最典型的现场：单引号属性值里含字体名的单引号。"""
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg'>"
            "<text font-family=''Noto Serif SC','Playfair Display',serif' font-size='20'>标题</text>"
            "</svg>"
        )
        fixed = _fix_attribute_quote_conflicts(svg)
        # 必须能被 XML 解析器接受
        ET.fromstring(fixed)
        # 内层引号变实体，字体名信息不丢
        assert "Noto Serif SC" in fixed
        assert "&apos;" in fixed

    def test_double_quoted_with_inner_double(self):
        svg = '<svg><text font-family=""Inter","Noto Sans SC",sans-serif">x</text></svg>'
        fixed = _fix_attribute_quote_conflicts(svg)
        ET.fromstring(fixed)
        assert "Inter" in fixed

    def test_healthy_svg_untouched(self):
        """正常 SVG 不能被改动（误伤比不修更糟）。"""
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<text x='10' y='20' font-family='Inter'>ok</text>"
            "</svg>"
        )
        assert _fix_attribute_quote_conflicts(svg) == svg
        ET.fromstring(svg)

    def test_value_ending_before_slash_or_gt(self):
        """结束引号后面可能是 '/' 或 '>'（自闭合标签），不能被当成内层引号。"""
        svg = "<svg><rect fill='#fff'/><text y='1'>t</text></svg>"
        assert _fix_attribute_quote_conflicts(svg) == svg
        ET.fromstring(svg)

    def test_text_content_is_not_touched(self):
        """标签外的正文里出现引号不能被改（只处理属性值）。"""
        svg = "<svg><text x='1'>他说'你好'</text></svg>"
        fixed = _fix_attribute_quote_conflicts(svg)
        # 正文保持原样（引号冲突只发生在属性内）
        assert "他说'你好'" in fixed


class TestSanitizeIntegration:
    def test_sanitize_repairs_quotes_and_parses(self):
        """sanitize_svg_xml 走完必须产出合法 XML。"""
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<text font-family=''Noto Serif SC',serif' font-size='20'>A &amp; B</text>"
            "</svg>"
        )
        fixed = sanitize_svg_xml(svg)
        ET.fromstring(fixed)

    def test_sanitize_still_escapes_text_specials(self):
        """原有的文本转义能力不能被引号修复破坏。"""
        svg = "<svg><text x='1'>a < b & c</text></svg>"
        fixed = sanitize_svg_xml(svg)
        ET.fromstring(fixed)


class TestQualityGateSeesRepairedContent:
    """质量门必须看到修复后的磁盘内容，否则整份 PPT 生成失败。

    踩过的坑：第一版只在内存里 ``svg = sanitize_svg_xml(svg)``，但质量门
    走 ``checker.check_file(str(f))`` **重新读磁盘**，内存改动对它不可见 ——
    测试照样报 ``Invalid XML``、产物创建返回 None。必须在质检前写回磁盘。
    """

    def test_repaired_svg_passes_quality_gate(self, tmp_path):
        from app.services.ppt.svg_quality_checker import SVGQualityChecker

        broken = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720'>"
            "<rect x='0' y='0' width='1280' height='720' fill='#fff'/>"
            "<text x='120' y='360' font-family=''Noto Serif SC','Playfair Display',serif' "
            "font-size='56'>标题</text>"
            "</svg>"
        )
        f = tmp_path / "slide_1.svg"
        f.write_text(broken, encoding="utf-8")

        checker = SVGQualityChecker()
        # 未修复：直接报 Invalid XML
        before = checker.check_file(str(f), "ppt169")
        assert any("Invalid XML" in e for e in before.get("errors", []))

        # 修复并写回磁盘后：不再有 XML 错误
        f.write_text(sanitize_svg_xml(broken), encoding="utf-8")
        after = checker.check_file(str(f), "ppt169")
        assert not any("Invalid XML" in e for e in after.get("errors", [])), after.get("errors")

    def test_create_from_slides_dir_repairs_before_gate(self, tmp_path):
        """端到端：坏 SVG 也能创建成功，且预览里有内容。"""
        import asyncio

        from app.services.ppt_artifact_service import PptArtifactService

        broken = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1280 720' data-theme='apple'>"
            "<rect x='0' y='0' width='1280' height='720' fill='#fff'/>"
            "<text x='120' y='360' font-family=''Noto Serif SC',serif' "
            "font-size='56'>冬季发布会</text>"
            "</svg>"
        )
        (tmp_path / "slide_1.svg").write_text(broken, encoding="utf-8")
        (tmp_path / "slide_2.svg").write_text(broken.replace("冬季发布会", "产品矩阵"), encoding="utf-8")

        svc = PptArtifactService()
        artifact = asyncio.run(svc.create_from_slides_dir("test-quote-repair", tmp_path))
        assert artifact is not None, svc.get_quality_feedback("test-quote-repair")
        assert artifact["slide_count"] == 2
        assert artifact["artifact_id"]
        # 预览 HTML 里能看到文字（不是空壳）
        assert "冬季发布会" in artifact["html"] or "产品矩阵" in artifact["html"]
