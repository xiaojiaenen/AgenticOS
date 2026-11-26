"""审批改参安全回归：modified_arguments 不得绕过服务端约束。

实测越权面：file 工具把 `workspace` 暴露成模型可见参数，审批改参可提交
`{"workspace": "/etc", "path": "passwd"}` 读取宿主机任意文件。现在改参在
执行前必须重跑 jsonschema/signature 校验 + workspace 越权防护。
"""

from __future__ import annotations

import pytest

from app.services.agent.langgraph_engine.tools_adapter import (
    _validate_modified_arguments,
)
from app.services.agent.native.tool_registry import ToolRegistry
from app.tools.website_file_tools import register_website_file_tools


@pytest.fixture()
def file_tool():
    registry = ToolRegistry()
    register_website_file_tools(registry)
    return registry.get("read_text_file") or registry.get("file_to_md")


def test_absolute_workspace_rejected(file_tool):
    with pytest.raises(ValueError, match="绝对路径|workspace"):
        _validate_modified_arguments(file_tool, {"path": "passwd", "workspace": "/etc"})


def test_relative_workspace_traversal_rejected(file_tool):
    with pytest.raises(ValueError, match="\\.\\.|穿越"):
        _validate_modified_arguments(file_tool, {"path": "x", "workspace": "../../etc"})


def test_valid_path_accepted(file_tool):
    # 不传 workspace → 走 _effective_workspace()，完全合法
    _validate_modified_arguments(file_tool, {"path": "uploads/notes.txt"})


def test_unknown_argument_rejected(file_tool):
    # jsonschema / signature.bind 必须拒绝未声明的参数
    with pytest.raises(ValueError):
        _validate_modified_arguments(file_tool, {"path": "x", "totally_unknown": 1})
