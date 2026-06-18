"""数据可视化工具 — LLM 调用后渲染 ECharts 图表。"""

from __future__ import annotations

import json
from typing import Any

from wuwei.tools import ToolRegistry

# 特殊标记，前端检测到此标记就知道是图表数据，不需要依赖 LLM 输出格式
_CHART_MARKER = "__ECHART_JSON__"


def register_chart_render_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="渲染数据图表")
    async def render_chart(
        chart_type: str,
        title: str,
        data: str,
        x_field: str = "",
        y_field: str = "",
    ) -> str:
        """渲染数据图表。调用后会在聊天中自动展示可视化图表，无需额外操作。

        支持的图表类型：
        - bar: 柱状图（分类对比）
        - line: 折线图（趋势变化）
        - area: 面积图（趋势+占比）
        - pie: 饼图（占比分析）
        - scatter: 散点图（相关性分析）
        - funnel: 漏斗图（转化分析）
        - gauge: 仪表盘（指标展示）
        - radar: 雷达图（多维对比）
        - table: 表格（原始数据展示）

        参数：
        - chart_type: 图表类型（上面列表中的一个）
        - title: 图表标题
        - data: JSON 数组字符串，如 '[{"部门":"销售","金额":100},{"部门":"技术","金额":200}]'
        - x_field: X 轴/分类字段名（不填自动推断：第一个非数值字段）
        - y_field: Y 轴/数值字段名（不填自动推断：第一个数值字段；支持逗号分隔多字段如 "金额,数量"）
        """
        try:
            rows = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            return json.dumps({"error": "data 参数必须是合法的 JSON 数组"}, ensure_ascii=False)

        if not isinstance(rows, list) or len(rows) == 0:
            return json.dumps({"error": "data 不能为空"}, ensure_ascii=False)

        supported = ("bar", "line", "area", "pie", "scatter", "funnel", "gauge", "radar", "table")
        if chart_type not in supported:
            return json.dumps({"error": f"不支持的图表类型: {chart_type}，可选: {', '.join(supported)}"}, ensure_ascii=False)

        # 自动推断字段
        first = rows[0]
        keys = list(first.keys())

        if not x_field:
            for k in keys:
                if not isinstance(first[k], (int, float)):
                    x_field = k
                    break
            if not x_field:
                x_field = keys[0]

        if not y_field:
            for k in keys:
                if isinstance(first[k], (int, float)):
                    y_field = k
                    break
            if not y_field:
                y_field = keys[-1] if len(keys) > 1 else keys[0]

        y_fields = [f.strip() for f in y_field.split(",") if f.strip()]

        # 生成 ECharts option
        echarts_option = _build_echarts_option(chart_type, title, rows, x_field, y_fields)

        # 包裹特殊标记，前端直接检测渲染，不依赖 LLM 输出格式
        return f"{_CHART_MARKER}\n{json.dumps(echarts_option, ensure_ascii=False)}\n{_CHART_MARKER}"


def _build_echarts_option(
    chart_type: str,
    title: str,
    rows: list[dict],
    x_field: str,
    y_fields: list[str],
) -> dict[str, Any]:
    """根据图表类型生成 ECharts option。"""

    categories = [str(r.get(x_field, "")) for r in rows]

    # ── 表格 ──
    if chart_type == "table":
        return {"columns": list(rows[0].keys()), "data": rows}

    # ── 饼图 ──
    if chart_type == "pie":
        data = [{"name": str(r.get(x_field, "")), "value": r.get(y_fields[0], 0)} for r in rows]
        return {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"orient": "vertical", "left": "left"},
            "series": [{"type": "pie", "radius": ["40%", "65%"], "data": data, "emphasis": {"itemStyle": {"shadowBlur": 10, "shadowOffsetX": 0, "shadowColor": "rgba(0,0,0,0.5)"}}],
        }

    # ── 散点图 ──
    if chart_type == "scatter":
        if len(y_fields) >= 2:
            series_data = [[r.get(y_fields[0], 0), r.get(y_fields[1], 0)] for r in rows]
        else:
            series_data = [[i, r.get(y_fields[0], 0)] for i, r in enumerate(rows)]
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "item"},
            "xAxis": {"type": "value", "name": y_fields[0] if len(y_fields) >= 2 else ""},
            "yAxis": {"type": "value", "name": y_fields[-1]},
            "series": [{"type": "scatter", "data": series_data, "symbolSize": 12}],
        }

    # ── 漏斗图 ──
    if chart_type == "funnel":
        data = [{"name": str(r.get(x_field, "")), "value": r.get(y_fields[0], 0)} for r in rows]
        # 按值降序排列
        data.sort(key=lambda x: x["value"], reverse=True)
        return {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
            "series": [{"type": "funnel", "left": "10%", "width": "80%", "sort": "descending", "gap": 2, "label": {"show": True, "position": "inside"}, "data": data}],
        }

    # ── 仪表盘 ──
    if chart_type == "gauge":
        val = rows[0].get(y_fields[0], 0)
        return {
            "title": {"text": title, "left": "center"},
            "series": [{"type": "gauge", "progress": {"show": True}, "detail": {"valueAnimation": True, "formatter": "{value}"}, "data": [{"value": val, "name": str(rows[0].get(x_field, ""))}]}],
        }

    # ── 雷达图 ──
    if chart_type == "radar":
        indicators = [{"name": str(r.get(x_field, "")), "max": max(r.get(yf, 0) for yf in y_fields) * 1.2 or 100} for r in rows]
        series_data = []
        for yf in y_fields:
            series_data.append({"value": [r.get(yf, 0) for r in rows], "name": yf})
        option: dict[str, Any] = {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item"},
            "radar": {"indicator": indicators},
            "series": [{"type": "radar", "data": series_data}],
        }
        if len(y_fields) > 1:
            option["legend"] = {"data": y_fields, "bottom": 0}
        return option

    # ── 面积图（line + areaStyle）──
    if chart_type == "area":
        series = []
        for yf in y_fields:
            series.append({"name": yf, "type": "line", "stack": "total", "areaStyle": {}, "data": [r.get(yf, 0) for r in rows]})
        option = {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "boundaryGap": False, "data": categories},
            "yAxis": {"type": "value"},
            "series": series,
        }
        if len(y_fields) > 1:
            option["legend"] = {"data": y_fields}
        return option

    # ── bar / line ──
    series = []
    for yf in y_fields:
        series.append({"name": yf, "type": chart_type, "data": [r.get(yf, 0) for r in rows]})

    option = {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "xAxis": {"type": "category", "data": categories},
        "yAxis": {"type": "value"},
        "series": series,
    }
    if len(y_fields) > 1:
        option["legend"] = {"data": y_fields}

    return option
