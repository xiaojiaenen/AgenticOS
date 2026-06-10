"""统一检查接口

整合技术检查和设计检查，提供统一的检查接口。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .technical_checker import TechnicalChecker, CheckResult
from .design_checker import DesignChecker, DesignCheckResult

_logger = logging.getLogger("ppt.checkers.unified")


@dataclass
class CheckReport:
    """单页检查报告"""
    slide_num: int
    errors: list[CheckResult]
    warnings: list[DesignCheckResult]
    passed: bool


@dataclass
class DeckCheckReport:
    """整个 deck 检查报告"""
    slides: list[CheckReport]
    consistency_errors: list[str]
    all_passed: bool

    def format(self) -> str:
        """格式化为可读字符串"""
        lines = []

        # 总结
        total_errors = sum(len(r.errors) for r in self.slides)
        total_warnings = sum(len(r.warnings) for r in self.slides)

        if self.all_passed:
            lines.append("✅ 所有检查通过！")
        else:
            lines.append(f"❌ 发现 {total_errors} 个错误，{total_warnings} 个警告")

        # 一致性错误
        if self.consistency_errors:
            lines.append("\n## 一致性问题")
            for error in self.consistency_errors:
                lines.append(f"  - {error}")

        # 各页详情
        for report in self.slides:
            if not report.errors and not report.warnings:
                continue

            lines.append(f"\n## 第 {report.slide_num} 页")

            if report.errors:
                lines.append("### 错误（必须修复）")
                for error in report.errors:
                    lines.append(f"  ❌ [{error.rule}] {error.message}")
                    if error.fix:
                        lines.append(f"     修复: {error.fix}")

            if report.warnings:
                lines.append("### 警告（建议修复）")
                for warning in report.warnings:
                    icon = "⚠️" if warning.severity == "warning" else "ℹ️"
                    lines.append(f"  {icon} [{warning.rule}] {warning.message}")
                    if warning.fix:
                        lines.append(f"     建议: {warning.fix}")

        return "\n".join(lines)


class PPTChecker:
    """统一检查接口"""

    def __init__(self):
        self.technical = TechnicalChecker()
        self.design = DesignChecker()

    def check_slide(
        self,
        svg: str,
        slide_num: int,
        expected_viewbox: str = "0 0 1280 720",
        check_design: bool = True,
    ) -> CheckReport:
        """检查单页

        参数:
            svg: SVG 内容
            slide_num: 页码
            expected_viewbox: 期望的 viewBox
            check_design: 是否检查设计质量

        返回:
            检查报告
        """
        errors = self.technical.check(svg, expected_viewbox)
        warnings = self.design.check(svg) if check_design else []

        return CheckReport(
            slide_num=slide_num,
            errors=errors,
            warnings=warnings,
            passed=len(errors) == 0,
        )

    def check_deck(
        self,
        svgs: list[str],
        expected_viewbox: str = "0 0 1280 720",
        check_design: bool = True,
    ) -> DeckCheckReport:
        """检查整个 deck

        参数:
            svgs: SVG 列表
            expected_viewbox: 期望的 viewBox
            check_design: 是否检查设计质量

        返回:
            deck 检查报告
        """
        reports = [
            self.check_slide(svg, i + 1, expected_viewbox, check_design)
            for i, svg in enumerate(svgs)
        ]

        # 一致性检查
        consistency_errors = self._check_consistency(svgs)

        return DeckCheckReport(
            slides=reports,
            consistency_errors=consistency_errors,
            all_passed=all(r.passed for r in reports) and len(consistency_errors) == 0,
        )

    def _check_consistency(self, svgs: list[str]) -> list[str]:
        """检查整个 deck 的一致性"""
        errors = []

        if len(svgs) < 3:
            errors.append(f"幻灯片不足 3 页（当前 {len(svgs)} 页）")

        # 检查 viewBox 一致性
        viewboxes = set()
        for i, svg in enumerate(svgs):
            import re
            match = re.search(r'viewBox="([^"]+)"', svg)
            if match:
                vb = " ".join(match.group(1).split())
                viewboxes.add(vb)

        if len(viewboxes) > 1:
            errors.append(f"viewBox 不一致: {', '.join(viewboxes)}")

        # 检查主题一致性
        themes = set()
        for svg in svgs:
            match = re.search(r'data-theme="([^"]+)"', svg)
            if match:
                themes.add(match.group(1))

        if len(themes) > 1:
            errors.append(f"主题不一致: {', '.join(themes)}")

        return errors


def check_ppt_quality(
    svgs: list[str],
    expected_viewbox: str = "0 0 1280 720",
    check_design: bool = True,
) -> DeckCheckReport:
    """便捷函数：检查 PPT 质量

    参数:
        svgs: SVG 列表
        expected_viewbox: 期望的 viewBox
        check_design: 是否检查设计质量

    返回:
        deck 检查报告
    """
    checker = PPTChecker()
    return checker.check_deck(svgs, expected_viewbox, check_design)
