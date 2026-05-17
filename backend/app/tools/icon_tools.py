"""图标搜索工具 — 按关键词查找可用图标"""

from pathlib import Path
from wuwei.tools import ToolRegistry

_ICON_INDEX_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "icons" / "icon_index.json"


def _load_index() -> dict[str, list[str]]:
    import json
    if not _ICON_INDEX_PATH.exists():
        return {}
    with open(_ICON_INDEX_PATH) as f:
        return json.load(f)


def _search(keyword: str, limit: int = 30) -> list[str]:
    kw = keyword.lower().strip()
    index = _load_index()
    results: list[str] = []
    for lib, names in index.items():
        for name in names:
            if kw in name.lower():
                results.append(f"{lib}/{name}")
    return results[:limit]


def register_icon_tools(registry: ToolRegistry):
    @registry.tool(display_name="搜索图标")
    async def search_icons(keyword: str) -> str:
        """
        按关键词搜索可用图标，返回匹配的图标名列表。
        图标名可直接用于 <use data-icon="库名/图标名" .../> 语法。

        Args:
            keyword: 搜索关键词，如 "rocket"、"chart"、"home"、"arrow"
        """
        results = _search(keyword)
        if not results:
            return f"未找到匹配 '{keyword}' 的图标。请尝试更通用的关键词（英文）。"
        lines = [f"搜索 '{keyword}' 找到 {len(results)} 个图标：", ""]
        for r in results:
            lines.append(f"  - {r}")
        if len(results) >= 30:
            lines.append("")
            lines.append("（结果已截断，请使用更精确的关键词缩小范围）")
        return "\n".join(lines)
