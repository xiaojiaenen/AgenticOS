from wuwei.tools import ToolRegistry


def register_template_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="导入PPTX模板")
    async def import_pptx_template(file_path: str) -> str:
        """将 PPTX 文件作为设计模板导入，提取主题颜色、布局结构和媒体资源。

        参数:
          file_path: PPTX 文件的绝对路径

        返回模板摘要，包括幻灯片数量、主题颜色、页面类型分类和可用资源。
        """
        from pathlib import Path as _Path
        import json as _json

        from app.services.ppt.pptx_to_svg.converter import convert_pptx_to_svg as _convert
        from app.services.ppt.template_import.manifest import build_manifest as _build_manifest

        pptx_path = _Path(file_path)
        if not pptx_path.exists():
            return f"文件不存在：{file_path}"
        if not pptx_path.suffix.lower() in (".pptx",):
            return f"不是 PPTX 文件：{file_path}"

        import tempfile

        output_dir = _Path(tempfile.mkdtemp(prefix="template_import_"))

        try:
            # Step 1: Convert PPTX to layered SVG
            result = _convert(pptx_path, output_dir)

            # Step 2: Build manifest from PPTX structure
            manifest = _build_manifest(pptx_path, output_dir)

            # Step 3: Save manifest
            manifest_path = output_dir / "manifest.json"
            manifest_path.write_text(_json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            # Step 4: Build summary
            slide_size = manifest["slideSize"]
            theme = manifest["theme"]
            slides = manifest["slides"]
            page_types = manifest.get("pageTypeCandidates", {})
            assets = manifest["assets"]
            layouts = manifest.get("layouts", [])
            masters = manifest.get("masters", [])

            lines = [
                f"### 模板导入完成",
                f"",
                f"**源文件**：{pptx_path.name}",
                f"**画布尺寸**：{slide_size['width_px']} × {slide_size['height_px']} px",
                f"**幻灯片数**：{len(slides)}",
                f"**布局数**：{len(layouts)}",
                f"**母版数**：{len(masters)}",
                f"**可复用资源**：{len(assets['commonAssets'])} 个",
                f"",
                f"**主题颜色**：",
            ]
            colors = theme.get("colors", {})
            if colors:
                for name, value in sorted(colors.items()):
                    lines.append(f"  - {name}: {value}")
            else:
                lines.append("  - (未检测到)")

            lines.append("")
            lines.append("**主题字体**：")
            fonts = theme.get("fonts", {})
            if fonts:
                for name, value in sorted(fonts.items()):
                    lines.append(f"  - {name}: {value}")
            else:
                lines.append("  - (未检测到)")

            lines.append("")
            lines.append("**页面类型推断**：")
            if page_types:
                for ptype, indexes in sorted(page_types.items()):
                    lines.append(f"  - {ptype}: 幻灯片 {', '.join(str(i) for i in indexes)}")
            else:
                lines.append("  - (未分类)")

            lines.append("")
            lines.append(f"**输出目录**：{output_dir}")
            lines.append(f"**清单文件**：{manifest_path}")

            return "\n".join(lines)
        except Exception as e:
            import traceback
            return f"模板导入失败：{e}\n\n```\n{traceback.format_exc()}\n```"
