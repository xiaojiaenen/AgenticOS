"""模板套用服务

将新内容填充到现有 PPTX 模板中，保留模板的样式和布局。
"""

from __future__ import annotations

import re
import json
import logging
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

_logger = logging.getLogger("ppt.template_fill")


@dataclass
class TemplateAnalysis:
    """模板分析结果"""
    slide_count: int
    colors: dict[str, str]
    fonts: dict[str, str]
    layouts: list[str]
    raw_svgs: list[str]
    canvas_width: int = 1280
    canvas_height: int = 720


@dataclass
class SlideContent:
    """单页内容"""
    slide_num: int
    title: Optional[str] = None
    body: Optional[str] = None
    items: Optional[list[str]] = None
    data: Optional[dict] = None


class TemplateWorkflow:
    """模板套用工作流"""

    def analyze_template(self, pptx_path: str) -> TemplateAnalysis:
        """分析 PPTX 模板，提取设计参数

        参数:
            pptx_path: PPTX 文件路径

        返回:
            模板分析结果
        """
        from app.services.ppt.pptx_to_svg.converter import (
            ConvertOptions,
            convert_pptx_to_svg,
        )

        pptx_path = Path(pptx_path)
        if not pptx_path.exists():
            raise FileNotFoundError(f"文件不存在: {pptx_path}")

        # 转换为 SVG
        output_dir = Path(tempfile.mkdtemp(prefix="template_analyze_"))
        options = ConvertOptions(inheritance_mode="flat")
        result = convert_pptx_to_svg(pptx_path, output_dir, options)

        # 提取颜色
        colors = result.theme_colors or {}

        # 提取字体
        fonts = self._extract_fonts(result)

        # 提取布局类型
        layouts = self._extract_layouts(result)

        # 读取 SVG 内容 - 直接从 SlideArtifact.svg 获取
        raw_svgs = []
        for slide in result.slides:
            if slide.svg:
                raw_svgs.append(slide.svg)

        return TemplateAnalysis(
            slide_count=len(result.slides),
            colors=colors,
            fonts=fonts,
            layouts=layouts,
            raw_svgs=raw_svgs,
            canvas_width=result.canvas_px[0] if result.canvas_px else 1280,
            canvas_height=result.canvas_px[1] if result.canvas_px else 720,
        )

    def fill_template(
        self,
        template_svgs: list[str],
        new_content: list[SlideContent],
        keep_style: bool = True,
    ) -> list[str]:
        """用新内容填充模板

        参数:
            template_svgs: 模板的 SVG 列表
            new_content: 新内容列表
            keep_style: 是否保留模板样式

        返回:
            填充后的 SVG 列表
        """
        filled_svgs = []

        for i, (svg, content) in enumerate(zip(template_svgs, new_content)):
            # 替换文字内容
            filled = self._replace_text(svg, content)

            # 替换数据（图表类）
            if content.data:
                filled = self._replace_chart_data(filled, content.data)

            filled_svgs.append(filled)

        return filled_svgs

    def _extract_fonts(self, result) -> dict[str, str]:
        """提取字体信息"""
        fonts = {}

        # 从 SVG 中提取字体 - 直接使用 slide.svg
        for slide in result.slides:
            if slide.svg:
                # 提取 font-family
                font_matches = re.findall(r'font-family="([^"]+)"', slide.svg)
                for font in font_matches:
                    if ',' in font:
                        # 取第一个字体
                        font = font.split(',')[0].strip()
                    if font and font not in fonts:
                        fonts[font] = font

        return fonts

    def _extract_layouts(self, result) -> list[str]:
        """提取布局类型"""
        layouts = []

        for i, slide in enumerate(result.slides):
            # 根据 SVG 结构推断布局类型 - 直接使用 slide.svg
            if slide.svg:
                layout = self._infer_layout(slide.svg)
                layouts.append(layout)

        return layouts

    def _infer_layout(self, svg_content: str) -> str:
        """推断布局类型"""
        # 简单的启发式推断
        if '<image' in svg_content:
            # 有图片
            if 'full-bleed' in svg_content or 'hero' in svg_content:
                return "cover"
            else:
                return "imageText"
        elif 'chart' in svg_content or 'rect' in svg_content:
            # 有图表
            return "chart"
        elif len(re.findall(r'<text', svg_content)) > 10:
            # 很多文字
            return "bullets"
        else:
            return "content"

    def _replace_text(self, svg: str, content: SlideContent) -> str:
        """替换文字内容"""
        result = svg

        # 替换标题
        if content.title:
            # 查找第一个大字号文本作为标题
            title_pattern = r'(<text[^>]*font-size="[4-6]\d"[^>]*>)(.*?)(</text>)'
            title_match = re.search(title_pattern, result, re.DOTALL)
            if title_match:
                result = result.replace(
                    title_match.group(0),
                    f"{title_match.group(1)}{content.title}{title_match.group(3)}"
                )

        # 替换正文
        if content.body:
            # 查找较小字号的文本块
            body_pattern = r'(<text[^>]*font-size="[12]\d"[^>]*>)(.*?)(</text>)'
            body_match = re.search(body_pattern, result, re.DOTALL)
            if body_match:
                result = result.replace(
                    body_match.group(0),
                    f"{body_match.group(1)}{content.body}{body_match.group(3)}"
                )

        # 替换列表项
        if content.items:
            # 查找 tspan 元素
            tspan_pattern = r'(<tspan[^>]*>)(.*?)(</tspan>)'
            tspan_matches = list(re.finditer(tspan_pattern, result, re.DOTALL))

            for i, item in enumerate(content.items):
                if i < len(tspan_matches):
                    result = result.replace(
                        tspan_matches[i].group(0),
                        f"{tspan_matches[i].group(1)}{item}{tspan_matches[i].group(3)}"
                    )

        return result

    def _replace_chart_data(self, svg: str, data: dict) -> str:
        """替换图表数据"""
        from app.services.ppt.chart_calibration import calibrate_chart

        # 检测图表类型
        if 'bar' in svg.lower() or 'rect' in svg:
            chart_type = "bar"
        elif 'pie' in svg.lower() or 'circle' in svg:
            chart_type = "pie"
        elif 'line' in svg.lower() or 'polyline' in svg:
            chart_type = "line"
        else:
            return svg

        # 转换数据格式
        data_list = []
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    data_list.append({"label": key, "value": value})
                elif isinstance(value, dict):
                    data_list.append({"label": key, **value})

        if data_list:
            return calibrate_chart(svg, chart_type, json.dumps(data_list))

        return svg


def analyze_template(pptx_path: str) -> TemplateAnalysis:
    """便捷函数：分析模板"""
    workflow = TemplateWorkflow()
    return workflow.analyze_template(pptx_path)


def fill_template(
    template_svgs: list[str],
    new_content: list[dict],
    keep_style: bool = True,
) -> list[str]:
    """便捷函数：填充模板

    参数:
        template_svgs: 模板 SVG 列表
        new_content: 新内容列表（字典格式）
        keep_style: 是否保留样式

    返回:
        填充后的 SVG 列表
    """
    workflow = TemplateWorkflow()

    # 转换为 SlideContent
    contents = []
    for i, content_dict in enumerate(new_content):
        contents.append(SlideContent(
            slide_num=i + 1,
            title=content_dict.get("title"),
            body=content_dict.get("body"),
            items=content_dict.get("items"),
            data=content_dict.get("data"),
        ))

    return workflow.fill_template(template_svgs, contents, keep_style)
