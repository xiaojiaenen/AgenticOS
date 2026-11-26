"""代码数据分析工具回归：白名单沙箱 + pandas 分析 + 导出。"""

from __future__ import annotations

import pytest

from app.services.agent.native.tool_registry import ToolRegistry
from app.tools.dataframe_tools import CodeRejected, _validate_code, register_dataframe_tools


@pytest.fixture()
def tool():
    registry = ToolRegistry()
    register_dataframe_tools(registry)
    return registry.get("analyze_with_pandas")


SAMPLE_DATA = '[{"部门":"销售","金额":100},{"部门":"技术","金额":200},{"部门":"销售","金额":50}]'


def test_registered():
    registry = ToolRegistry()
    register_dataframe_tools(registry)
    t = registry.get("analyze_with_pandas")
    assert t is not None
    assert "pandas" in t.description.lower()


def test_basic_analysis(tool):
    """分组聚合代码能正确执行并 print 结果。"""
    import asyncio

    result = asyncio.run(tool.invoke({
        "code": "out = df.groupby('部门')['金额'].sum()\nprint(out)",
        "data": SAMPLE_DATA,
    }))
    assert result["ok"] is True, result
    assert "销售" in result["stdout"]
    assert "150" in result["stdout"]
    assert "技术" in result["stdout"]


def test_numpy_available(tool):
    import asyncio

    result = asyncio.run(tool.invoke({
        "code": "import numpy as np\nprint(round(float(np.mean(df['金额'])), 2))",
        "data": SAMPLE_DATA,
    }))
    assert result["ok"] is True, result
    assert "116.67" in result["stdout"]


@pytest.mark.parametrize("bad_code", [
    "import os\nprint(os.getcwd())",           # 非白名单模块
    "import subprocess",                        # 非白名单模块
    "open('/etc/passwd').read()",               # 危险内置
    "print((1).__class__)",                     # 私有属性逃逸
    "exec('print(1)')",                         # 危险内置
    "__import__('os')",                         # 危险内置
    "print(__builtins__)",                      # builtins 泄露
    "from pathlib import Path",                 # 非白名单模块
    "while True:\n    pass",                    # 无界循环（防卡死）
    # 实测越界向量：pandas IO 可读取宿主机任意文件
    "import pandas as pd\npd.read_csv('/etc/hosts', sep='\\x00', engine='python')",
    "import pandas as pd\npd.read_excel('/etc/passwd')",
    # 格式化字符串 gadget：属性表达式藏在字符串常量里枚举 object 子类
    "print('{0.__class__.__base__.__subclasses__}'.format(1))",
    "print(f'{df.__class__}')",
])
def test_dangerous_code_rejected(bad_code):
    with pytest.raises(CodeRejected):
        _validate_code(bad_code)


def test_tool_rejects_dangerous_code(tool):
    import asyncio

    result = asyncio.run(tool.invoke({
        "code": "import os\nprint(os.getcwd())",
        "data": SAMPLE_DATA,
    }))
    assert result["ok"] is False
    assert result["error"]["type"] == "CodeRejected"


def test_execution_error_reported(tool):
    import asyncio

    result = asyncio.run(tool.invoke({
        "code": "raise ValueError('boom')",
        "data": SAMPLE_DATA,
    }))
    assert result["ok"] is False
    assert result["error"]["type"] == "ExecutionError"
    assert "boom" in result["error"]["message"]


def test_export_csv(tool):
    """导出 CSV 到会话 workspace（需 contextvar 注入 user/session）。"""
    import asyncio

    from app.core import data_path

    data_path.set_current_user_id(99999)
    data_path.set_current_session_id("test-dataframe-export")
    try:
        result = asyncio.run(tool.invoke({
            "code": "result = df.groupby('部门')['金额'].sum().reset_index()\nprint(result)",
            "data": SAMPLE_DATA,
            "export": "csv",
            "filename": "summary",
        }))
        assert result["ok"] is True, result
        assert result["exports"], result
        assert result["exports"][0]["filename"] == "summary.csv"
        assert result["exports"][0]["size_bytes"] > 0
    finally:
        data_path.set_current_user_id(0)
        data_path.set_current_session_id("")
