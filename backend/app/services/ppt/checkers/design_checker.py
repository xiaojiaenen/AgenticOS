"""设计检查器 - 警告为主，不阻断

检查 SVG 的设计质量，提供建议但不阻断导出。
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger("ppt.checkers.design")


@dataclass
class DesignCheckResult:
    """设计检查结果"""
    passed: bool
    rule: str
    message: str
    severity: str  # "warning" or "info"
    fix: Optional[str] = None


class DesignChecker:
    """设计检查器 - 警告为主，不阻断"""

    def check(self, svg: str) -> list[DesignCheckResult]:
        """检查 SVG 设计质量

        参数:
            svg: SVG 内容

        返回:
            警告列表
        """
        results: list[DesignCheckResult] = []

        # 1. 检查 accent 使用
        results.append(self._check_accent_usage(svg))

        # 2. 检查字号种类
        results.append(self._check_font_size_variety(svg))

        # 3. 检查 <g> 分组
        results.append(self._check_groups(svg))

        # 4. 检查演讲者备注
        results.append(self._check_notes(svg))

        # 5. 检查图片
        results.append(self._check_image(svg))

        # 6. 检查动画标记
        results.append(self._check_animation_markers(svg))

        # 7. 检查留白平衡
        results.append(self._check_whitespace_balance(svg))

        # 8. 检查对齐
        results.append(self._check_alignment(svg))

        # 过滤掉通过的检查
        return [r for r in results if not r.passed]

    def _check_accent_usage(self, svg: str) -> DesignCheckResult:
        """检查 accent 颜色使用"""
        count = len(re.findall(r'var\(--accent\)', svg))
        if count > 3:
            return DesignCheckResult(
                passed=False,
                rule="accent_overuse",
                message=f"accent 颜色使用过多（{count}次，建议≤3次）",
                severity="warning",
                fix="减少 var(--accent) 的使用次数"
            )
        return DesignCheckResult(passed=True, rule="accent", message="OK", severity="info")

    def _check_font_size_variety(self, svg: str) -> DesignCheckResult:
        """检查字号种类"""
        sizes = re.findall(r'font-size="(\d+)"', svg)
        unique_sizes = set(sizes)
        if len(unique_sizes) > 5:
            return DesignCheckResult(
                passed=False,
                rule="font_size_variety",
                message=f"字号种类过多（{len(unique_sizes)}种，建议≤5种）",
                severity="warning",
                fix="统一字号，使用 3-5 种字号层级"
            )
        return DesignCheckResult(passed=True, rule="font_size", message="OK", severity="info")

    def _check_groups(self, svg: str) -> DesignCheckResult:
        """检查 <g> 分组"""
        # 检查 <svg> 根下是否有裸元素
        svg_inner = re.search(r'<svg[^>]*>(.*)</svg>', svg, re.DOTALL)
        if svg_inner:
            inner = svg_inner.group(1).strip()
            # 移除注释
            inner_no_comment = re.sub(r'<!--.*?-->', '', inner, flags=re.DOTALL).strip()
            if inner_no_comment and not re.match(r'<g[\s>]', inner_no_comment):
                return DesignCheckResult(
                    passed=False,
                    rule="no_groups",
                    message="<svg> 根下有裸元素，应使用 <g id='...'> 分组",
                    severity="info",
                    fix="为主要内容块添加 <g id=\"...\"> 分组"
                )
        return DesignCheckResult(passed=True, rule="groups", message="OK", severity="info")

    def _check_notes(self, svg: str) -> DesignCheckResult:
        """检查演讲者备注"""
        # 检查 SVG 注释中的 notes
        if '<!-- notes:' in svg:
            return DesignCheckResult(passed=True, rule="notes", message="OK", severity="info")

        # 检查独立的 notes 文件（需要外部调用）
        return DesignCheckResult(
            passed=False,
            rule="no_notes",
            message="缺少演讲者备注",
            severity="info",
            fix="添加 <!-- notes: ... --> 注释或 save_slide 时传入 notes 参数"
        )

    def _check_image(self, svg: str) -> DesignCheckResult:
        """检查图片"""
        if '<image' in svg:
            return DesignCheckResult(passed=True, rule="image", message="OK", severity="info")

        return DesignCheckResult(
            passed=False,
            rule="no_image",
            message="缺少图片",
            severity="info",
            fix="封面和章节页必须有图片，调用 search_images 搜索"
        )

    def _check_animation_markers(self, svg: str) -> DesignCheckResult:
        """检查动画标记"""
        if 'data-animate=' in svg:
            return DesignCheckResult(passed=True, rule="animation", message="OK", severity="info")

        return DesignCheckResult(
            passed=False,
            rule="no_animation_markers",
            message="缺少动画标记",
            severity="info",
            fix="为关键元素添加 data-animate 属性"
        )

    def _check_whitespace_balance(self, svg: str) -> DesignCheckResult:
        """检查留白是否均匀"""
        # 提取 viewBox 尺寸
        viewBox_match = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        if not viewBox_match:
            return DesignCheckResult(passed=True, rule="whitespace", message="OK", severity="info")

        width = int(viewBox_match.group(1))
        height = int(viewBox_match.group(2))

        # 提取所有元素的 x, y 坐标
        x_coords = [int(x) for x in re.findall(r'x="(\d+)"', svg)]
        y_coords = [int(y) for y in re.findall(r'y="(\d+)"', svg)]

        if not x_coords or not y_coords:
            return DesignCheckResult(passed=True, rule="whitespace", message="OK", severity="info")

        # 计算左右边距
        min_x = min(x_coords)
        max_x = max(x_coords)
        left_margin = min_x
        right_margin = width - max_x

        # 边距差异超过 50% 视为不均匀
        if left_margin > 0 and right_margin > 0:
            ratio = max(left_margin, right_margin) / min(left_margin, right_margin)
            if ratio > 1.5:
                return DesignCheckResult(
                    passed=False,
                    rule="whitespace_imbalance",
                    message="留白不均匀（左右边距差异过大）",
                    severity="warning",
                    fix="调整元素位置使左右边距均匀"
                )

        return DesignCheckResult(passed=True, rule="whitespace", message="OK", severity="info")

    def _check_alignment(self, svg: str) -> DesignCheckResult:
        """检查元素是否对齐到 8px 网格"""
        # 提取所有 x, y 坐标
        coords = re.findall(r'[xy]="(\d+)"', svg)
        if not coords:
            return DesignCheckResult(passed=True, rule="alignment", message="OK", severity="info")

        # 检查是否有坐标不是 8 的倍数
        misaligned = 0
        for coord in coords:
            val = int(coord)
            if val % 8 != 0 and val != 0:  # 0 除外
                misaligned += 1

        # 如果超过 30% 的坐标未对齐，视为问题
        if misaligned > len(coords) * 0.3:
            return DesignCheckResult(
                passed=False,
                rule="alignment_drift",
                message=f"元素未对齐到网格（{misaligned}/{len(coords)} 未对齐）",
                severity="info",
                fix="对齐到 8px 网格"
            )

        return DesignCheckResult(passed=True, rule="alignment", message="OK", severity="info")
