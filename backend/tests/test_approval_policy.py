"""三档审批模式（ask / auto / full）测试。"""

from __future__ import annotations

import json

import pytest

from app.services.approval_policy import (
    DEFAULT_APPROVAL_MODE,
    is_read_only_tool,
    normalize_approval_mode,
)


class TestNormalize:
    def test_valid_modes_pass_through(self):
        assert normalize_approval_mode("ask") == "ask"
        assert normalize_approval_mode("auto") == "auto"
        assert normalize_approval_mode("full") == "full"

    def test_case_and_space_tolerant(self):
        assert normalize_approval_mode("  AUTO ") == "auto"

    def test_invalid_falls_back_to_ask(self):
        assert normalize_approval_mode("yolo") == DEFAULT_APPROVAL_MODE
        assert normalize_approval_mode(None) == DEFAULT_APPROVAL_MODE
        assert normalize_approval_mode("") == DEFAULT_APPROVAL_MODE


class TestIsReadOnly:
    @pytest.mark.parametrize(
        "tool",
        ["time", "calc", "knowledge", "memory", "read_slide", "check_ppt_progress",
         "search_images", "list_icons", "analyze_data"],
    )
    def test_read_only_tools(self, tool):
        assert is_read_only_tool(tool) is True

    @pytest.mark.parametrize(
        "tool",
        ["file", "python", "git", "npm", "email", "save_slide", "build_website",
         "deploy_website", "unknown_future_tool"],
    )
    def test_write_or_unknown_tools_are_not_read_only(self, tool):
        """保守策略：未列入白名单的一律视为需要审批（含未来新增工具）。"""
        assert is_read_only_tool(tool) is False

    def test_file_read_subtool_is_read_only(self):
        assert is_read_only_tool("file", {"action": "read_text_file"}) is True
        assert is_read_only_tool("file", {"action": "list_files"}) is True

    def test_file_write_subtool_is_not_read_only(self):
        assert is_read_only_tool("file", {"action": "write_text_file"}) is False
        assert is_read_only_tool("file", {"action": "delete_file"}) is False

    def test_email_read_subtool_is_read_only(self):
        assert is_read_only_tool("email", {"action": "list_emails"}) is True
        assert is_read_only_tool("email", {"action": "send_email"}) is False

    def test_json_string_arguments_supported(self):
        args = json.loads(json.dumps({"action": "read_text_file"}))
        assert is_read_only_tool("file", args) is True
