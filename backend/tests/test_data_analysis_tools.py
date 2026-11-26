"""analyze_data 工具回归：9 种操作 + 严格 JSON 输出（NaN/Inf 归 null）。

此前该工具零测试覆盖，实测发现含空值的数据会输出裸 `NaN` —— 非法 JSON，
JS JSON.parse / 严格解析器直接失败。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.agent.native.tool_registry import ToolRegistry
from app.tools.data_analysis_tools import register_data_analysis_tools


@pytest.fixture()
def tool():
    registry = ToolRegistry()
    register_data_analysis_tools(registry)
    return registry.get("analyze_data")


def _strict_parse(text: str):
    """按 JS JSON.parse 的严格度解析（拒绝 NaN / Infinity）。"""
    return json.loads(text, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {x}")))


DATA = '[{"部门":"销售","金额":100},{"部门":"技术","金额":200},{"部门":"销售","金额":50}]'


def test_all_analysis_types(tool):
    # 单数值列的 correlation 按契约返回 error（至少需要 2 个数值列），其余正常。
    for kind in ("summary", "describe", "top", "bottom", "group_sum", "group_count", "null_check", "trend"):
        out = asyncio.run(tool.invoke({"data": DATA, "analysis_type": kind, "column": "金额"}))
        result = _strict_parse(out)
        assert "error" not in result, f"{kind} 意外失败: {result}"

    corr = _strict_parse(asyncio.run(tool.invoke({"data": DATA, "analysis_type": "correlation"})))
    assert "error" in corr and "至少" in corr["error"]


def test_top_and_bottom_order(tool):
    top = _strict_parse(asyncio.run(tool.invoke({"data": DATA, "analysis_type": "top", "column": "金额"})))
    bottom = _strict_parse(asyncio.run(tool.invoke({"data": DATA, "analysis_type": "bottom", "column": "金额"})))
    assert top["结果"][0]["金额"] == 200
    assert bottom["结果"][0]["金额"] == 50


def test_null_and_inf_become_json_null(tool):
    """含 null / 缺失值的数据：输出必须是严格合法 JSON，NaN → null。"""
    data = '[{"金额":1},{"金额":null},{"金额":2}]'
    for kind in ("summary", "top", "bottom", "describe", "trend"):
        out = asyncio.run(tool.invoke({"data": data, "analysis_type": kind}))
        result = _strict_parse(out)  # 严格解析，若仍有裸 NaN 会抛 ValueError
        assert isinstance(result, dict)


def test_invalid_inputs(tool):
    for bad in ("", "not json", "{}", "[]"):
        result = _strict_parse(asyncio.run(tool.invoke({"data": bad})))
        assert "error" in result, f"{bad!r} 应报错"

    result = _strict_parse(asyncio.run(tool.invoke({"data": DATA, "analysis_type": "bogus"})))
    assert "error" in result
