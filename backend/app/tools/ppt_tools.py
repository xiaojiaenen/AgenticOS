"""PPT 生成工具 — save_slide 将 SVG 写入会话工作目录"""

import contextvars
import os
from pathlib import Path

from wuwei.tools import ToolRegistry

# ---------------------------------------------------------------------------
# 项目根目录（用于构建 data/ 路径）
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# session 上下文（由 agent_service 在创建 agent 前注入）
# ---------------------------------------------------------------------------
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ppt_session_id", default="",
)


def set_current_session_id(session_id: str) -> None:
    _current_session_id.set(session_id)


def _get_slides_dir() -> Path:
    session_id = _current_session_id.get()
    if not session_id:
        raise RuntimeError("save_slide: session_id 未设置，无法确定写入目录")
    slides_dir = _PROJECT_ROOT / "data" / "ppt-sessions" / session_id
    slides_dir.mkdir(parents=True, exist_ok=True)
    return slides_dir


def _count_slides(slides_dir: Path) -> int:
    if not slides_dir.exists():
        return 0
    return len([f for f in slides_dir.iterdir() if f.suffix == ".svg"])


# ---------------------------------------------------------------------------
# 工具注册
# ---------------------------------------------------------------------------
def register_ppt_tools(registry: ToolRegistry) -> None:

    @registry.tool(display_name="保存幻灯片")
    async def save_slide(slide_num: int, svg: str) -> str:
        """将一页 SVG 幻灯片写入会话工作目录。每页调用一次，调用完所有页后停止即可。

        参数:
          slide_num: 页码（从 1 开始递增）
          svg: 完整的单个 <svg>...</svg> 元素，必须包含 viewBox="0 0 1280 720"
        """
        if not svg.strip().startswith("<svg"):
            return "错误：svg 参数必须以 <svg> 开头"
        if "viewBox" not in svg:
            return "错误：svg 必须包含 viewBox 属性，例如 viewBox=\"0 0 1280 720\""

        slides_dir = _get_slides_dir()
        file_path = slides_dir / f"slide_{slide_num}.svg"
        file_path.write_text(svg, encoding="utf-8")

        count = _count_slides(slides_dir)
        return f"第 {slide_num} 页已保存（共 {count} 页）"

    if "save_slide" in os.environ.get("PPT_TOOLS_DISABLED", "").split(","):
        del registry._tools["save_slide"]
