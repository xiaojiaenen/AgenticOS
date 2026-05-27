"""PPT 生成工具 — save_slide 将 SVG 写入会话工作目录"""

import os
from pathlib import Path

from wuwei.tools import ToolRegistry

from app.core.data_path import (
    PPT_SESSIONS_DIR,
    get_current_session_id,
    get_current_user_id,
    next_version_dir,
)

# ---------------------------------------------------------------------------
# slides directory — uses versioned naming: u<user_id>_s<session_id>_v<N>
# ---------------------------------------------------------------------------
_slides_dir_cache: Path | None = None


def reset_slides_dir_cache() -> None:
    """Reset the cached slides dir (called at the start of each stream)."""
    global _slides_dir_cache
    _slides_dir_cache = None


def _get_slides_dir() -> Path:
    global _slides_dir_cache
    if _slides_dir_cache is not None and _slides_dir_cache.exists():
        return _slides_dir_cache

    session_id = get_current_session_id()
    if not session_id:
        raise RuntimeError("save_slide: session_id 未设置，无法确定写入目录")

    user_id = get_current_user_id()
    # Check if there's already a directory for this user+session
    if PPT_SESSIONS_DIR.exists():
        for child in sorted(PPT_SESSIONS_DIR.iterdir()):
            if not child.is_dir():
                continue
            parts = child.name.split("_v", 1)
            if len(parts) == 2 and parts[0] == f"u{user_id}_s{session_id}":
                _slides_dir_cache = child
                child.mkdir(parents=True, exist_ok=True)
                return child

    # No existing dir — create next version
    slides_dir = next_version_dir(PPT_SESSIONS_DIR, user_id, session_id)
    slides_dir.mkdir(parents=True, exist_ok=True)
    _slides_dir_cache = slides_dir
    return slides_dir


def _count_slides(slides_dir: Path) -> int:
    if not slides_dir.exists():
        return 0
    return len([f for f in slides_dir.iterdir() if f.suffix == ".svg"])


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------
def register_ppt_tools(registry: ToolRegistry) -> None:

    @registry.tool(display_name="读取幻灯片")
    async def read_slide(slide_num: int) -> str:
        """读取已有幻灯片的 SVG 内容，用于修改前查看。

        参数:
          slide_num: 要读取的页码（从 1 开始）
        """
        slides_dir = _get_slides_dir()
        file_path = slides_dir / f"slide_{slide_num}.svg"
        if not file_path.exists():
            existing = _count_slides(slides_dir)
            return f"第 {slide_num} 页不存在（当前共 {existing} 页）"
        return file_path.read_text(encoding="utf-8")

    @registry.tool(display_name="保存幻灯片")
    async def save_slide(slide_num: int, svg: str) -> str:
        """将一页 SVG 幻灯片写入会话工作目录。新建或覆盖已有页。每页调用一次，调用完所有页后停止即可。

        参数:
          slide_num: 页码（从 1 开始递增）
          svg: 完整的单个 <svg>...</svg> 元素，必须包含 viewBox="0 0 1280 720"
        """
        if not svg.strip().startswith("<svg"):
            return "错误：svg 参数必须以 <svg> 开头"
        if "viewBox" not in svg:
            return '错误：svg 必须包含 viewBox 属性，例如 viewBox="0 0 1280 720"'

        slides_dir = _get_slides_dir()
        file_path = slides_dir / f"slide_{slide_num}.svg"
        existed = file_path.exists()
        file_path.write_text(svg, encoding="utf-8")
        count = _count_slides(slides_dir)
        action = "已更新" if existed else "已保存"
        return f"第 {slide_num} 页{action}（共 {count} 页）"

    if "save_slide" in os.environ.get("PPT_TOOLS_DISABLED", "").split(","):
        del registry._tools["save_slide"]
