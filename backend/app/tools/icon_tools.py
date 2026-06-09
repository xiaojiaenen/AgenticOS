"""图标搜索工具 — 基于文件系统的零依赖图标查找"""

from pathlib import Path
from wuwei.tools import ToolRegistry

from app.core.data_path import DATA_DIR

_ICONS_DIR = DATA_DIR / "icons"
_INDEX_CACHE: dict[str, list[str]] | None = None


def _build_index() -> dict[str, list[str]]:
    """扫描图标目录，构建 {library: [icon_name, ...]} 索引。"""
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE

    if not _ICONS_DIR.exists():
        _INDEX_CACHE = {}
        return _INDEX_CACHE

    index: dict[str, list[str]] = {}
    for entry in sorted(_ICONS_DIR.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            names = sorted(f.stem for f in entry.iterdir() if f.suffix == ".svg")
            if names:
                index[entry.name] = names

    _INDEX_CACHE = index
    return index


def _search(keyword: str, limit: int = 30) -> list[str]:
    kw = keyword.lower().strip()
    if not kw:
        return []
    index = _build_index()
    results: list[str] = []
    for lib, names in index.items():
        for name in names:
            if kw in name.lower():
                results.append(f"{lib}/{name}")
    return results[:limit]


def _search_multi(keywords: list[str], limit: int = 30) -> list[str]:
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

        index = _build_index()
        if not index:
            return (
                "错误：图标库未初始化。请运行 scripts/setup_icons.sh 安装图标资源。\n"
                "跳过图标搜索，使用纯文字排版（<text> 元素代替图标）。"
            )

        kw_list = [k.strip() for k in re.split(r"[,，\s]+", keywords) if k.strip()]
        if not kw_list:
            return "请提供至少一个搜索关键词。"

        results = _search_multi(kw_list)
        if not results:
            return (
                f"未找到匹配 {kw_list} 的图标。请尝试更通用的英文关键词。\n"
                "如果连续多次未找到，使用纯文字排版代替图标。"
            )

        lines = [f"搜索 {kw_list} 找到 {len(results)} 个图标：", ""]
        for r in results:
            lines.append(f"  - {r}")
        if len(results) >= 30:
            lines.append("")
            lines.append("（结果已截断，请使用更精确的关键词缩小范围）")
        return "\n".join(lines)

    @registry.tool(display_name="列出图标库")
    async def list_icons() -> str:
        """
        列出所有可用的图标库及图标数量。用于确认图标库是否可用。
        """
        index = _build_index()
        if not index:
            return (
                "错误：图标库未初始化。请运行 scripts/setup_icons.sh 安装图标资源。\n"
                "当前无可用图标，使用纯文字排版。"
            )

        total = sum(len(names) for names in index.values())
        lines = [f"可用图标库（共 {total} 个图标）：", ""]
        for lib, names in index.items():
            lines.append(f"  {lib}: {len(names)} 个图标")
        lines.append("")
        lines.append('使用 <use data-icon="库名/图标名" .../> 引用图标。')
        lines.append("每套 PPT 只选一个风格库，禁止混用。")
        return "\n".join(lines)
