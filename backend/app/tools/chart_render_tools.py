"""数据可视化工具 — LLM 调用后渲染 ECharts 图表。"""

from __future__ import annotations

import json
from typing import Any

from wuwei.tools import ToolRegistry


def register_chart_render_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="渲染数据图表")
    async def render_chart(
        chart_type: str,
        title: str,
        data: str,
        x_field: str = "",
        y_field: str = "",
    ) -> str:
        """渲染数据图表。调用后会在聊天中展示可视化图表。

        重要：调用此工具后，将返回的 JSON 原样放入 ```echarts 代码块中，前端会自动渲染为图表。
        示例：
        ```echarts
        {"title":{"text":"xxx"},"xAxis":{...},"series":[...]}
        ```

        支持的图表类型：
        - bar: 柱状图（分类对比）
        - line: 折线图（趋势变化）
        - pie: 饼图（占比分析）
        - scatter: 散点图（相关性）
        - table: 表格（原始数据）

        参数：
        - chart_type: 图表类型
        - title: 图表标题
        - data: JSON 数组，如 [{"部门":"销售","金额":100}, {"部门":"技术","金额":200}]
        - x_field: X 轴字段名（饼图用 name_field 语义）
        - y_field: Y 轴字段名（支持逗号分隔多字段，如 "金额,数量"）
        """
        try:
            rows = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            return json.dumps({"error": "data 参数必须是合法的 JSON 数组"}, ensure_ascii=False)

        if not isinstance(rows, list) or len(rows) == 0:
            return json.dumps({"error": "data 不能为空"}, ensure_ascii=False)

        if chart_type not in ("bar", "line", "pie", "scatter", "table"):
            return json.dumps({"error": f"不支持的图表类型: {chart_type}"}, ensure_ascii=False)

        # 自动推断字段
        first = rows[0]
        keys = list(first.keys())

        if not x_field:
            # 第一个非数值字段作为 x_field
            for k in keys:
                if not isinstance(first[k], (int, float)):
                    x_field = k
                    break
            if not x_field:
                x_field = keys[0]

        if not y_field:
            # 第一个数值字段作为 y_field
            for k in keys:
                if isinstance(first[k], (int, float)):
                    y_field = k
                    break
            if not y_field:
                y_field = keys[-1] if len(keys) > 1 else keys[0]

        y_fields = [f.strip() for f in y_field.split(",") if f.strip()]

        # 生成 ECharts option
        echarts_option = _build_echarts_option(chart_type, title, rows, x_field, y_fields)

        # 返回 ECharts option JSON，前端检测 ```echarts 代码块并渲染
        return json.dumps(echarts_option, ensure_ascii=False)


def _build_echarts_option(
    chart_type: str,
    title: str,
    rows: list[dict],
    x_field: str,
    y_fields: list[str],
) -> dict[str, Any]:
    """根据图表类型生成 ECharts option。"""

    categories = [str(r.get(x_field, "")) for r in rows]

    if chart_type == "pie":
        data = []
        for r in rows:
            val = r.get(y_fields[0], 0)
            data.append({"name": str(r.get(x_field, "")), "value": val})
        return {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item"},
            "series": [{"type": "pie", "radius": "50%", "data": data}],
        }

    if chart_type == "table":
        columns = list(rows[0].keys())
        return {
            "columns": columns,
            "data": rows,
        }

    if chart_type == "scatter":
        if len(y_fields) < 2:
            # 散点图需要两个数值字段
            series_data = [[i, r.get(y_fields[0], 0)] for i, r in enumerate(rows)]
        else:
            series_data = [[r.get(y_fields[0], 0), r.get(y_fields[1], 0)] for r in rows]
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "item"},
            "xAxis": {"type": "value", "name": y_fields[0] if len(y_fields) >= 2 else ""},
            "yAxis": {"type": "value", "name": y_fields[-1]},
            "series": [{"type": "scatter", "data": series_data}],
        }

    # bar / line
    series = []
    for yf in y_fields:
        series.append({
            "name": yf,
            "type": chart_type,
            "data": [r.get(yf, 0) for r in rows],
        })

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
