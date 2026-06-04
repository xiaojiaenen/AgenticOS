from pathlib import Path as _Path

from wuwei.tools import ToolRegistry

from app.core.data_path import (
    PPT_SESSIONS_DIR,
    get_current_session_id,
    get_current_user_id,
    next_version_dir,
)


def register_pptx_reverse_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="转换PPTX为SVG")
    async def convert_pptx_to_svg(file_path: str) -> str:
        """将上传的 PPTX 文件转换为 SVG，提取幻灯片中的矢量图形用于设计参考。

        参数:
          file_path: PPTX 文件的绝对路径

        返回每个幻灯片的 SVG 内容和提取的主题颜色方案。
        转换后的 SVG 会自动写入会话工作目录，可直接用 read_slide 读取和 save_slide 修改。
        """
        from app.services.ppt.pptx_to_svg.converter import (
            ConvertOptions,
            convert_pptx_to_svg as _convert,
        )

        pptx_path = _Path(file_path)
        if not pptx_path.exists():
            return f"文件不存在：{file_path}"
        if not pptx_path.suffix.lower() in (".pptx",):
            return f"不是 PPTX 文件：{file_path}"

        import tempfile

        output_dir = _Path(tempfile.mkdtemp(prefix="pptx2svg_"))

        try:
            # Use "flat" mode so each slide is self-contained (no external refs needed)
            options = ConvertOptions(inheritance_mode="flat")
            result = _convert(pptx_path, output_dir, options)
            slide_count = len(result.slides)
            canvas = result.canvas_px
            colors = result.theme_colors

            # Write slides to session directory so Agent can read / modify them
            session_id = get_current_session_id()
            imported_count = 0
            if session_id:
                # Find or create versioned slides dir (same logic as ppt_tools)
                slides_dir = None
                user_id = get_current_user_id()
                if PPT_SESSIONS_DIR.exists():
                    for child in sorted(PPT_SESSIONS_DIR.iterdir()):
                        if not child.is_dir():
                            continue
                        parts = child.name.split("_v", 1)
                        if len(parts) == 2 and parts[0] == f"u{user_id}_s{session_id}":
                            slides_dir = child
                            break
                if slides_dir is None:
                    slides_dir = next_version_dir(PPT_SESSIONS_DIR, user_id, session_id)
                slides_dir.mkdir(parents=True, exist_ok=True)
                for slide in result.slides:
                    slide_file = slides_dir / f"slide_{slide.index}.svg"
                    slide_file.write_text(slide.svg, encoding="utf-8")
                    imported_count += 1

            lines = [
                f"### PPTX 转换完成",
                f"",
                f"- **幻灯片数**：{slide_count}",
                f"- **画布尺寸**：{canvas[0]:.0f} × {canvas[1]:.0f} px",
                f"- **输出目录**：{output_dir}",
            ]
            if imported_count > 0:
                lines.append(f"- **已导入会话**：{imported_count} 页写入工作目录，可用 read_slide / save_slide 修改")

            lines.append("")
            lines.append("**主题颜色**：")
            for name, value in list(colors.items())[:12]:
                lines.append(f"  - {name}: {value}")

            lines.append("")
            lines.append("**幻灯片 SVG 文件**：")
            for slide in result.slides:
                lines.append(f"  - slide_{slide.index:02d}.svg ({len(slide.svg)} 字符)")

            return "\n".join(lines)
        except Exception as e:
            return f"PPTX 转换失败：{e}"
