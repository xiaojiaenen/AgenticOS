"""技术检查器 - 必须通过才能导出

检查 SVG 的技术规范，确保能正确导出为 PPTX。
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger("ppt.checkers.technical")


@dataclass
class CheckResult:
    """检查结果"""
    passed: bool
    rule: str
    message: str
    fix: Optional[str] = None


class TechnicalChecker:
    """技术检查器 - 必须通过才能导出"""

    def check(self, svg: str, expected_viewbox: str = "0 0 1280 720") -> list[CheckResult]:
        """检查 SVG 技术规范

        参数:
            svg: SVG 内容
            expected_viewbox: 期望的 viewBox

        返回:
            错误列表，空列表表示通过
        """
        results: list[CheckResult] = []

        # 1. 检查 viewBox
        results.append(self._check_viewbox(svg, expected_viewbox))

        # 2. 检查 XML 格式
        results.append(self._check_xml_format(svg))

        # 3. 检查禁止元素
        results.append(self._check_forbidden_elements(svg))

        # 4. 检查 rgba 颜色
        results.append(self._check_rgba_colors(svg))

        # 5. 检查 data-theme
        results.append(self._check_data_theme(svg))

        # 过滤掉通过的检查
        return [r for r in results if not r.passed]

    def _check_viewbox(self, svg: str, expected: str) -> CheckResult:
        """检查 viewBox 属性"""
        match = re.search(r'viewBox="([^"]+)"', svg)
        if not match:
            return CheckResult(
                passed=False,
                rule="viewbox_missing",
                message="缺少 viewBox 属性",
                fix='添加 viewBox="0 0 1280 720"'
            )

        actual = " ".join(match.group(1).split())
        expected_normalized = " ".join(expected.split())

        if actual != expected_normalized:
            return CheckResult(
                passed=False,
                rule="viewbox_mismatch",
                message=f"viewBox 不匹配: {actual} (期望: {expected})",
                fix=f'修改 viewBox="{expected}"'
            )

        return CheckResult(passed=True, rule="viewbox", message="OK")

    def _check_xml_format(self, svg: str) -> CheckResult:
        """检查 XML 格式"""
        try:
            from xml.etree import ElementTree as ET
            ET.fromstring(svg)
            return CheckResult(passed=True, rule="xml_format", message="OK")
        except ET.ParseError as e:
            return CheckResult(
                passed=False,
                rule="invalid_xml",
                message=f"XML 格式错误: {str(e)[:100]}",
                fix="检查未闭合标签或特殊字符"
            )

    def _check_forbidden_elements(self, svg: str) -> CheckResult:
        """检查禁止的 SVG 元素"""
        forbidden = ['<mask', '<foreignObject', '<script', '<animate', '<iframe']
        found = [tag for tag in forbidden if tag in svg]

        if found:
            return CheckResult(
                passed=False,
                rule="forbidden_elements",
                message=f"包含禁止的元素: {', '.join(found)}",
                fix=f"移除 {', '.join(found)} 等元素"
            )

        return CheckResult(passed=True, rule="forbidden_elements", message="OK")

    def _check_rgba_colors(self, svg: str) -> CheckResult:
        """检查 rgba() 颜色"""
        if 'rgba(' in svg:
            return CheckResult(
                passed=False,
                rule="rgba_color",
                message="使用了 rgba() 颜色",
                fix="改用 var(--token) 或 HEX 颜色，透明度用 fill-opacity/stroke-opacity"
            )

        return CheckResult(passed=True, rule="rgba_color", message="OK")

    def _check_data_theme(self, svg: str) -> CheckResult:
        """检查 data-theme 属性"""
        if 'data-theme=' not in svg:
            return CheckResult(
                passed=False,
                rule="missing_theme",
                message="缺少 data-theme 属性",
                fix='添加 data-theme="主题名" 到 <svg> 标签'
            )

        return CheckResult(passed=True, rule="data_theme", message="OK")


def has_critical_errors(svg: str) -> bool:
    """快速检查：是否有必须修复的错误"""
    checker = TechnicalChecker()
    errors = checker.check(svg)
    return len(errors) > 0
