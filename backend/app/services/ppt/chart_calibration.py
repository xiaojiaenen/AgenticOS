"""图表数据校准

校准 SVG 图表中的数据和坐标，确保图表准确反映实际数据。
"""

from __future__ import annotations

import re
import logging
import json
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger("ppt.chart_calibration")


@dataclass
class BarData:
    """柱状图数据"""
    label: str
    value: float


@dataclass
class PieData:
    """饼图数据"""
    label: str
    value: float
    percentage: float


@dataclass
class LinePoint:
    """折线图数据点"""
    x: float
    y: float


class ChartCalibrator:
    """图表数据校准器"""

    def calibrate_bar_chart(self, svg: str, data: list[BarData], chart_height: int = 400) -> str:
        """校准柱状图

        参数:
            svg: 原始 SVG
            data: 柱状图数据
            chart_height: 图表高度

        返回:
            校准后的 SVG
        """
        # 提取现有柱子
        bars = self._extract_bars(svg)
        if not bars:
            _logger.warning("No bars found in SVG")
            return svg

        # 计算最大值
        max_value = max(d.value for d in data)
        if max_value == 0:
            max_value = 1

        # 更新每个柱子的高度
        for i, (bar, d) in enumerate(zip(bars, data)):
            if i >= len(data):
                break

            # 计算正确的高度
            correct_height = (d.value / max_value) * chart_height

            # 更新柱子高度
            svg = self._update_bar_height(svg, bar, correct_height)

            # 更新标签
            if 'label_id' in bar:
                svg = self._update_text(svg, bar['label_id'], d.label)

        return svg

    def calibrate_pie_chart(self, svg: str, data: list[PieData]) -> str:
        """校准饼图

        参数:
            svg: 原始 SVG
            data: 饼图数据（百分比）

        返回:
            校准后的 SVG
        """
        # 提取现有扇区
        sectors = self._extract_pie_sectors(svg)
        if not sectors:
            _logger.warning("No pie sectors found in SVG")
            return svg

        # 计算总值
        total = sum(d.value for d in data)
        if total == 0:
            total = 1

        # 计算累积角度
        current_angle = 0
        for i, (sector, d) in enumerate(zip(sectors, data)):
            if i >= len(data):
                break

            # 计算角度
            angle = (d.value / total) * 360

            # 更新扇区路径
            svg = self._update_pie_sector(svg, sector, current_angle, angle, d.percentage)

            current_angle += angle

        return svg

    def calibrate_line_chart(
        self,
        svg: str,
        data: list[LinePoint],
        chart_width: int = 1000,
        chart_height: int = 400,
        x_min: float = 0,
        x_max: float = 100,
        y_min: float = 0,
        y_max: float = 100,
    ) -> str:
        """校准折线图

        参数:
            svg: 原始 SVG
            data: 数据点
            chart_width: 图表宽度
            chart_height: 图表高度
            x_min: X 轴最小值
            x_max: X 轴最大值
            y_min: Y 轴最小值
            y_max: Y 轴最大值

        返回:
            校准后的 SVG
        """
        # 提取现有折线
        lines = self._extract_line_paths(svg)
        if not lines:
            _logger.warning("No line paths found in SVG")
            return svg

        # 计算数据范围
        x_range = x_max - x_min
        y_range = y_max - y_min
        if x_range == 0:
            x_range = 1
        if y_range == 0:
            y_range = 1

        # 生成新的路径
        points = []
        for d in data:
            x = ((d.x - x_min) / x_range) * chart_width
            y = chart_height - ((d.y - y_min) / y_range) * chart_height
            points.append(f"{x},{y}")

        new_path = "M " + " L ".join(points)

        # 更新路径
        for line in lines:
            svg = svg.replace(line['d'], new_path)

        return svg

    def _extract_bars(self, svg: str) -> list[dict]:
        """提取柱状图的柱子"""
        bars = []
        # 匹配 rect 元素，假设是柱子
        pattern = r'<rect[^>]*id="([^"]*)"[^>]*x="(\d+)"[^>]*y="(\d+)"[^>]*width="(\d+)"[^>]*height="(\d+)"[^>]*/>'
        for match in re.finditer(pattern, svg):
            bars.append({
                'id': match.group(1),
                'x': int(match.group(2)),
                'y': int(match.group(3)),
                'width': int(match.group(4)),
                'height': int(match.group(5)),
            })
        return bars

    def _update_bar_height(self, svg: str, bar: dict, new_height: int) -> str:
        """更新柱子高度"""
        # 计算新的 y 坐标（柱子底部对齐）
        new_y = bar['y'] + bar['height'] - new_height

        # 替换 height 和 y
        old_pattern = f'id="{bar["id"]}"[^>]*height="{bar["height"]}"'
        new_pattern = f'id="{bar["id"]}"[^>]*height="{int(new_height)}"'

        svg = re.sub(old_pattern, new_pattern, svg)

        old_pattern = f'id="{bar["id"]}"[^>]*y="{bar["y"]}"'
        new_pattern = f'id="{bar["id"]}"[^>]*y="{int(new_y)}"'

        svg = re.sub(old_pattern, new_pattern, svg)

        return svg

    def _update_text(self, svg: str, element_id: str, new_text: str) -> str:
        """更新文本内容"""
        pattern = f'id="{element_id}"[^>]*>([^<]*)</text>'
        replacement = f'id="{element_id}">{new_text}</text>'
        return re.sub(pattern, replacement, svg)

    def _extract_pie_sectors(self, svg: str) -> list[dict]:
        """提取饼图扇区"""
        sectors = []
        # 匹配 path 元素，假设是扇区
        pattern = r'<path[^>]*id="([^"]*)"[^>]*d="([^"]*)"[^>]*/>'
        for match in re.finditer(pattern, svg):
            sectors.append({
                'id': match.group(1),
                'd': match.group(2),
            })
        return sectors

    def _update_pie_sector(
        self,
        svg: str,
        sector: dict,
        start_angle: float,
        angle: float,
        percentage: float,
    ) -> str:
        """更新饼图扇区"""
        # 这里简化处理，实际需要根据 SVG 的坐标系计算扇区路径
        # 暂时返回原始 SVG
        return svg

    def _extract_line_paths(self, svg: str) -> list[dict]:
        """提取折线图路径"""
        lines = []
        # 匹配 path 元素，假设是折线
        pattern = r'<path[^>]*id="([^"]*)"[^>]*d="([^"]*)"[^>]*/>'
        for match in re.finditer(pattern, svg):
            lines.append({
                'id': match.group(1),
                'd': match.group(2),
            })
        return lines


def calibrate_chart(
    svg: str,
    chart_type: str,
    data_json: str,
) -> str:
    """便捷函数：校准图表

    参数:
        svg: SVG 内容
        chart_type: 图表类型 (bar/pie/line)
        data_json: 数据 JSON 字符串

    返回:
        校准后的 SVG
    """
    calibrator = ChartCalibrator()

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as e:
        _logger.error("Invalid JSON data: %s", e)
        return svg

    if chart_type == "bar":
        bar_data = [BarData(label=d.get("label", ""), value=d.get("value", 0)) for d in data]
        return calibrator.calibrate_bar_chart(svg, bar_data)

    elif chart_type == "pie":
        total = sum(d.get("value", 0) for d in data)
        pie_data = [
            PieData(
                label=d.get("label", ""),
                value=d.get("value", 0),
                percentage=(d.get("value", 0) / total * 100) if total > 0 else 0,
            )
            for d in data
        ]
        return calibrator.calibrate_pie_chart(svg, pie_data)

    elif chart_type == "line":
        line_data = [LinePoint(x=d.get("x", 0), y=d.get("y", 0)) for d in data]
        return calibrator.calibrate_line_chart(svg, line_data)

    else:
        _logger.warning("Unknown chart type: %s", chart_type)
        return svg
