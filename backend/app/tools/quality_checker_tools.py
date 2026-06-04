from wuwei.tools import ToolRegistry

from app.core.data_path import PPT_SESSIONS_DIR, get_current_session_id, get_current_user_id


def _find_slides_dir():
    """Resolve the current session's slides directory using versioned naming."""
    from app.core.data_path import _parse_dir_name
    session_id = get_current_session_id()
    if not session_id:
        return None
    user_id = get_current_user_id()
    if not PPT_SESSIONS_DIR.exists():
        return None
    for child in sorted(PPT_SESSIONS_DIR.iterdir()):
        if not child.is_dir():
            continue
        parsed = _parse_dir_name(child.name)
        if parsed and parsed[0] == user_id and parsed[1] == session_id:
            return child
    return None


def register_quality_checker_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="检查SVG质量")
    async def check_svg_quality(slide_num: int | None = None) -> str:
        """检查已生成幻灯片的 SVG 质量，返回错误和警告。

        如果不指定 slide_num，则检查所有已保存的幻灯片。
        检查项目包括：XML 合法性、viewBox 一致性、禁止元素检测、
        字体安全性、尺寸一致性、文本溢出等。
        """
        from app.services.ppt.svg_quality_checker import SVGQualityChecker

        slides_dir = _find_slides_dir()
        if slides_dir is None:
            return "错误：无法获取当前会话的幻灯片目录"

        if not slides_dir.exists():
            return f"会话目录不存在：{slides_dir}"

        checker = SVGQualityChecker()
        results = []

        if slide_num is not None:
            svg_file = slides_dir / f"slide_{slide_num}.svg"
            if not svg_file.exists():
                return f"文件不存在：{svg_file}"
            result = checker.check_file(str(svg_file), "ppt169")
            results.append(result)
        else:
            svg_files = sorted(slides_dir.glob("slide_*.svg"))
            if not svg_files:
                return "没有找到已保存的幻灯片"
            for f in svg_files:
                result = checker.check_file(str(f), "ppt169")
                results.append(result)

        # Build summary
        lines = ["### SVG 质量检查结果\n"]
        total_errors = 0
        total_warnings = 0
        for r in results:
            status = "✓" if r["passed"] else "✗"
            lines.append(f"- **{r['file']}** {status}")
            for e in r.get("errors", []):
                lines.append(f"  - ❌ {e}")
                total_errors += 1
            for w in r.get("warnings", []):
                lines.append(f"  - ⚠️ {w}")
                total_warnings += 1

        lines.insert(1, f"检查 {len(results)} 个文件：{total_errors} 个错误，{total_warnings} 个警告\n")
        return "\n".join(lines)
