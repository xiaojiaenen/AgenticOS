"""图表模板选型（给 agent 在「该用哪种图」时查）。

本地 ``data/charts/`` 已有 71 个 SVG 模板，且 ``charts_index.json`` 里每条
都带一句话选型规则（"Pick for X. Skip if Y（use other_key）."）。缺的只是
一个可调用的查询入口 —— agent 此前只能靠猜模板名。

本模块提供：
- ``list_chart_templates``：按关键词/全部列出候选（含选型规则）；
- ``get_chart_template``：取某个模板的 SVG 源，照着它的结构改数据。

设计取舍：**不做语义向量检索**。上游用 370 行解析索引 + 关键词打分，但
71 条规则一次性列出也就两千字，直接全文给模型做语义匹配更准、更省代码。
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger("agent.ppt.charts")

_CHARTS_DIR_NAME = "charts"


def _charts_dir() -> Path | None:
    """定位 data/charts。

    三个候选按序尝试：
    1. ``app.core.data_path.DATA_DIR`` —— 运行时配置的目录（容器内是 /app/data）；
    2. 仓库根的 ``data/charts`` —— 测试环境会把 DATA_DIR 重定向到临时目录，
       那里没有图表库；回退到真实仓库目录让工具在单测里也能工作；
    3. ``/app/data/charts`` —— 容器兜底。
    """
    try:
        from app.core.data_path import DATA_DIR

        candidate = DATA_DIR / _CHARTS_DIR_NAME
        if candidate.is_dir():
            return candidate
    except Exception:  # noqa: BLE001
        pass

    # backend/app/services/ppt/chart_catalog.py → 上溯 5 层到仓库根
    repo_data = Path(__file__).resolve().parents[4] / "data" / _CHARTS_DIR_NAME
    if repo_data.is_dir():
        return repo_data

    container_data = Path("/app/data") / _CHARTS_DIR_NAME
    if container_data.is_dir():
        return container_data
    return None


_INDEX_CACHE: dict | None = None


def _load_index() -> dict[str, dict]:
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    directory = _charts_dir()
    if directory is None:
        _INDEX_CACHE = {}
        return _INDEX_CACHE
    index_file = directory / "charts_index.json"
    if not index_file.exists():
        _INDEX_CACHE = {}
        return _INDEX_CACHE
    try:
        payload = json.loads(index_file.read_text(encoding="utf-8"))
        charts = payload.get("charts") or {}
        if isinstance(charts, dict):
            _INDEX_CACHE = charts
        else:
            _INDEX_CACHE = {}
    except Exception:  # noqa: BLE001 -- 索引坏了不该让工具挂掉
        logger.warning("charts_index.json 解析失败", exc_info=True)
        _INDEX_CACHE = {}
    return _INDEX_CACHE


#: 中文意图 → 英文模板关键词（索引本身是英文，中文查询需要这层映射）
_ZH_TO_EN: dict[str, list[str]] = {
    "趋势": ["trend", "line", "area"],
    "走势": ["trend", "line"],
    "时间": ["time", "timeline", "gantt"],
    "时间线": ["timeline", "gantt"],
    "甘特": ["gantt"],
    "占比": ["share", "proportion", "pie", "donut", "percentage"],
    "比例": ["share", "proportion", "ratio"],
    "饼图": ["pie", "donut"],
    "环形": ["donut", "circular"],
    "对比": ["comparison", "compare", "bar", "column"],
    "比较": ["comparison", "compare"],
    "排名": ["ranking", "bar", "horizontal"],
    "排行": ["ranking", "bar"],
    "分布": ["distribution", "histogram", "scatter"],
    "相关": ["correlation", "scatter", "bubble"],
    "流程": ["process", "flow", "chevron", "funnel"],
    "步骤": ["process", "step", "chevron"],
    "漏斗": ["funnel"],
    "转化": ["funnel", "conversion"],
    "组织": ["org", "hierarchy", "tree"],
    "层级": ["hierarchy", "layered", "tree"],
    "架构": ["architecture", "layered"],
    "矩阵": ["matrix", "quadrant"],
    "四象限": ["quadrant"],
    "鱼骨": ["fishbone"],
    "因果": ["fishbone", "cause"],
    "竞品": ["comparison", "matrix", "feature"],
    "功能": ["feature", "matrix"],
    "指标": ["kpi", "metric", "gauge"],
    "仪表": ["gauge", "dashboard"],
    "热力": ["heatmap"],
    "地图": ["map", "journey"],
    "旅程": ["journey", "map"],
    "循环": ["circular", "cycle", "hub"],
    "闭环": ["circular", "cycle"],
    "列表": ["list", "agenda"],
    "议程": ["agenda"],
    "财务": ["financial", "statement"],
    "预算": ["budget", "financial"],
    "表格": ["table"],
    "卡片": ["card", "kpi"],
}


def _keywords(text: str) -> list[str]:
    """把查询拆成小写关键词（英文按词、中文按映射 + 2-字滑窗）。"""
    text = (text or "").lower()
    words = re.findall(r"[a-z0-9_]+", text)
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]+", text))

    # 中文意图映射：命中词表就补上对应英文关键词
    mapped: list[str] = []
    for zh, ens in _ZH_TO_EN.items():
        if zh in cjk:
            mapped.extend(ens)

    grams = [cjk[i : i + 2] for i in range(max(0, len(cjk) - 1))]
    # 英文映射词权重靠前（更准），滑窗只是兜底
    return mapped + words + grams


def search_chart_templates(query: str = "", limit: int = 12) -> list[dict]:
    """按关键词搜图表模板，返回 ``[{"key", "summary", "score"}]``（按相关度降序）。

    空查询返回全部（按 key 排序）—— 71 条规则整份给模型做语义匹配，
    比任何关键词打分都准。
    """
    index = _load_index()
    if not index:
        return []
    if not query.strip():
        return [
            {"key": k, "summary": (v or {}).get("summary", "")}
            for k, v in sorted(index.items())
        ][: max(limit, len(index))]

    keys = _keywords(query)
    scored: list[tuple[int, str, str]] = []
    for key, meta in index.items():
        summary = (meta or {}).get("summary", "") or ""
        haystack = f"{key} {summary}".lower()
        score = 0
        for kw in keys:
            if kw and kw in haystack:
                # key 命中权重更高（模板名就是结构名）
                score += 3 if kw in key.lower() else 1
        if score > 0:
            scored.append((score, key, summary))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [{"key": k, "summary": s, "score": sc} for sc, k, s in scored[:limit]]


def get_chart_template(key: str) -> str | None:
    """读取某个模板的 SVG 源（供 agent 照结构改数据）。"""
    directory = _charts_dir()
    if directory is None:
        return None
    index = _load_index()
    if key not in index:
        return None
    svg_file = directory / f"{key}.svg"
    if not svg_file.exists():
        return None
    try:
        return svg_file.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        logger.warning("读取图表模板失败: %s", key, exc_info=True)
        return None


def catalog_size() -> int:
    return len(_load_index())
