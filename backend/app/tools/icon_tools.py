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


def _search_multi(keywords: list[str], limit: int = 30) -> list[str]:
    """Search for multiple keywords, deduplicate, return merged results."""
    seen: set[str] = set()
    results: list[str] = []
    for kw in keywords:
        for r in _search(kw, limit=999):
            if r not in seen:
                seen.add(r)
                results.append(r)
    return results[:limit]


def register_icon_tools(registry: ToolRegistry):
    @registry.tool(display_name="搜索图标")
    async def search_icons(keywords: str) -> str:
        """
        批量搜索可用图标，返回匹配的图标名列表。多个关键词用逗号或空格分隔。
        图标名可直接用于 <use data-icon="库名/图标名" .../> 语法。

        Args:
            keywords: 搜索关键词，多个用逗号或空格分隔，如 "rocket, chart, home"
                      也可以用中文描述，如 "火箭 图表 首页"
        """
        import re
        kw_list = [k.strip() for k in re.split(r'[,，\s]+', keywords) if k.strip()]
        if not kw_list:
            return "请提供至少一个搜索关键词。"

        results = _search_multi(kw_list)
        if not results:
            return f"未找到匹配的关键词。请尝试更通用的英文关键词。"

        lines = [f"搜索 {kw_list} 找到 {len(results)} 个图标：", ""]
        for r in results:
            lines.append(f"  - {r}")
        if len(results) >= 30:
            lines.append("")
            lines.append("（结果已截断，请使用更精确的关键词缩小范围）")
        return "\n".join(lines)
