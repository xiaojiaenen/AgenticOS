"""数据分析工具 — 对查询结果进行自然语言分析。"""

from __future__ import annotations

import json
from typing import Any

from wuwei.tools import ToolRegistry


def register_data_analysis_tools(registry: ToolRegistry) -> None:
    @registry.tool(display_name="数据分析")
    async def analyze_data(
        data: str,
        analysis_type: str = "summary",
        column: str = "",
    ) -> str:
        """对数据进行统计分析。支持常用分析操作，无需写代码。

        分析类型 (analysis_type)：
        - summary: 数据概览（行数、列数、每列统计）
        - describe: 数值列统计（均值、中位数、最大最小值）
        - top: 按指定列降序取前 10（需指定 column）
        - bottom: 按指定列升序取前 10（需指定 column）
        - group_sum: 按第一列分组，对数值列求和
        - group_count: 按第一列分组，计数
        - null_check: 检查空值
        - correlation: 数值列相关性分析
        - trend: 按顺序分析数值列趋势（增/减/波动）

        参数：
        - data: JSON 数组字符串，如 '[{"部门":"销售","金额":100},{"部门":"技术","金额":200}]'
        - analysis_type: 分析类型（上面列表中的一个）
        - column: 用于 top/bottom 排序的列名
        """
        try:
            rows = json.loads(data) if isinstance(data, str) else data
        except json.JSONDecodeError:
            return json.dumps({"error": "data 必须是合法 JSON 数组"}, ensure_ascii=False)

        if not isinstance(rows, list) or len(rows) == 0:
            return json.dumps({"error": "data 不能为空"}, ensure_ascii=False)

        try:
            import pandas as pd
            df = pd.DataFrame(rows)
        except Exception as e:
            return json.dumps({"error": f"创建 DataFrame 失败: {e}"}, ensure_ascii=False)

        result = _run_analysis(df, analysis_type, column)
        return json.dumps(result, ensure_ascii=False, default=str)


def _run_analysis(df, analysis_type: str, column: str) -> dict[str, Any]:
    """执行分析并返回结构化结果。"""
    import pandas as pd

    try:
        if analysis_type == "summary":
            return _summary(df)
        elif analysis_type == "describe":
            return _describe(df)
        elif analysis_type == "top":
            return _top_n(df, column, ascending=False)
        elif analysis_type == "bottom":
            return _top_n(df, column, ascending=True)
        elif analysis_type == "group_sum":
            return _group_agg(df, "sum")
        elif analysis_type == "group_count":
            return _group_agg(df, "count")
        elif analysis_type == "null_check":
            return _null_check(df)
        elif analysis_type == "correlation":
            return _correlation(df)
        elif analysis_type == "trend":
            return _trend(df)
        else:
            return {"error": f"不支持的分析类型: {analysis_type}"}
    except Exception as e:
        return {"error": f"分析失败: {e}"}


def _summary(df) -> dict:
    """数据概览"""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    info = {
        "行数": len(df),
        "列数": len(df.columns),
        "列名": df.columns.tolist(),
        "数值列": numeric_cols,
        "文本列": df.select_dtypes(include=["object"]).columns.tolist(),
    }
    # 前 5 行预览
    info["前5行"] = df.head(5).to_dict(orient="records")
    return info


def _describe(df) -> dict:
    """数值列统计"""
    desc = df.describe().to_dict()
    # 简化输出
    result = {}
    for col, stats in desc.items():
        result[col] = {k: round(v, 2) if isinstance(v, float) else v for k, v in stats.items()}
    return {"统计": result}


def _top_n(df, column: str, ascending: bool = False) -> dict:
    """Top/Bottom N"""
    if not column:
        # 自动选第一个数值列
        numeric_cols = df.select_dtypes(include=["number"]).columns
        if len(numeric_cols) == 0:
            return {"error": "没有数值列可用于排序"}
        column = numeric_cols[0]

    if column not in df.columns:
        return {"error": f"列 '{column}' 不存在，可用列: {df.columns.tolist()}"}

    sorted_df = df.sort_values(column, ascending=ascending).head(10)
    direction = "升序" if ascending else "降序"
    return {
        "排序列": column,
        "方向": direction,
        "结果": sorted_df.to_dict(orient="records"),
    }


def _group_agg(df, agg_func: str) -> dict:
    """分组聚合"""
    cols = df.columns.tolist()
    if len(cols) < 2:
        return {"error": "至少需要 2 列（分组列 + 数值列）"}

    group_col = cols[0]
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()

    if not numeric_cols:
        # 尝试计数
        result = df.groupby(group_col).size().reset_index(name="count")
        return {"分组列": group_col, "聚合": "count", "结果": result.to_dict(orient="records")}

    result = df.groupby(group_col)[numeric_cols].agg(agg_func).reset_index()
    return {"分组列": group_col, "聚合": agg_func, "结果": result.to_dict(orient="records")}


def _null_check(df) -> dict:
    """空值检查"""
    null_counts = df.isnull().sum()
    total = len(df)
    result = {}
    for col in df.columns:
        count = int(null_counts[col])
        if count > 0:
            result[col] = {"空值数": count, "占比": f"{count/total*100:.1f}%"}

    if not result:
        return {"message": "没有空值"}
    return {"空值统计": result}


def _correlation(df) -> dict:
    """相关性分析"""
    numeric_df = df.select_dtypes(include=["number"])
    if len(numeric_df.columns) < 2:
        return {"error": "至少需要 2 个数值列"}

    corr = numeric_df.corr()
    # 找出高相关性的列对
    high_corr = []
    for i in range(len(corr.columns)):
        for j in range(i + 1, len(corr.columns)):
            val = corr.iloc[i, j]
            if abs(val) > 0.5:
                high_corr.append({
                    "列1": corr.columns[i],
                    "列2": corr.columns[j],
                    "相关系数": round(val, 3),
                    "关系": "强正相关" if val > 0.7 else "正相关" if val > 0.5 else "强负相关" if val < -0.7 else "负相关",
                })

    return {
        "相关性矩阵": {col: {k: round(v, 3) for k, v in row.items()} for col, row in corr.to_dict().items()},
        "显著相关": high_corr,
    }


def _trend(df) -> dict:
    """趋势分析"""
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    if not numeric_cols:
        return {"error": "没有数值列"}

    trends = {}
    for col in numeric_cols:
        values = df[col].dropna().tolist()
        if len(values) < 2:
            trends[col] = "数据不足"
            continue

        first = values[0]
        last = values[-1]
        change = last - first
        pct = (change / first * 100) if first != 0 else 0

        # 判断趋势
        increasing = sum(1 for i in range(1, len(values)) if values[i] > values[i-1])
        decreasing = sum(1 for i in range(1, len(values)) if values[i] < values[i-1])
        total = len(values) - 1

        if increasing > total * 0.7:
            direction = "持续上升"
        elif decreasing > total * 0.7:
            direction = "持续下降"
        elif abs(pct) < 5:
            direction = "基本持平"
        else:
            direction = "波动"

        trends[col] = {
            "趋势": direction,
            "起始值": first,
            "结束值": last,
            "变化量": round(change, 2),
            "变化率": f"{pct:.1f}%",
            "最大值": max(values),
            "最小值": min(values),
        }

    return {"趋势分析": trends}
