from wuwei.tools import ToolRegistry


def register_pptx_reverse_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="转换PPTX为SVG")
    async def convert_pptx_to_svg(file_path: str) -> str:
        """将上传的 PPTX 文件转换为 SVG，提取幻灯片中的矢量图形用于设计参考。

        参数:
          file_path: PPTX 文件的绝对路径

        返回每个幻灯片的 SVG 内容和提取的主题颜色方案。
        """
        from pathlib import Path as _Path

        from app.services.ppt.pptx_to_svg.converter import convert_pptx_to_svg as _convert

        pptx_path = _Path(file_path)
        if not pptx_path.exists():
            return f"文件不存在：{file_path}"
        if not pptx_path.suffix.lower() in (".pptx",):
            return f"不是 PPTX 文件：{file_path}"

        # Create output in a temp directory alongside the input file
        import tempfile
        output_dir = _Path(tempfile.mkdtemp(prefix="pptx2svg_"))

        try:
            result = _convert(pptx_path, output_dir)
            slide_count = len(result.slides)
            canvas = result.canvas_px
            colors = result.theme_colors

            lines = [
                f"### PPTX 转换完成",
                f"",
                f"- **幻灯片数**：{slide_count}",
                f"- **画布尺寸**：{canvas[0]} × {canvas[1]} px",
                f"- **输出目录**：{output_dir}",
                f"",
                f"**主题颜色**：",
            ]
            for name, value in list(colors.items())[:12]:
                lines.append(f"  - {name}: {value}")

            lines.append("")
            lines.append("**幻灯片 SVG 文件**：")
            for i, slide in enumerate(result.slides, 1):
                svg_preview = slide.svg[:200].replace("\n", " ")
                lines.append(f"  - slide_{i:02d}.svg ({len(slide.svg)} 字符)")

            return "\n".join(lines)
        except Exception as e:
            return f"PPTX 转换失败：{e}"
