"""三档审批模式（ask / auto / full）测试。"""

from __future__ import annotations

import inspect
import json

import pytest

from app.services.approval_policy import (
    DEFAULT_APPROVAL_MODE,
    PLAN_MODE_PROMPT_SUFFIX,
    is_read_only_tool,
    normalize_approval_mode,
    plan_mode_blocked_tools,
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

    @pytest.mark.parametrize(
        "tool",
        [
            # 这些是**独立注册**的工具名（`@registry.tool(name=...)`），
            # 不是 `file` + action 的形态。此前只按 action 判定，导致它们
            # 全部落到「需审批」分支——一个中等任务要点 45 次批准。
            "read_text_file",
            "list_files",
            "list_knowledge_bases",
            "search_knowledge_base",
            "read_wiki_page",
            "search_memory",
            "list_memory_scenarios",
            "get_user_persona",
        ],
    )
    def test_independently_registered_read_tools(self, tool):
        assert is_read_only_tool(tool) is True

    @pytest.mark.parametrize(
        "tool",
        [
            "write_text_file",
            "append_text_file",
            "delete_file",
            "replace_text_in_file",
            "save_memory",
        ],
    )
    def test_independently_registered_write_tools_still_need_approval(self, tool):
        """补白名单不能顺手把写操作也放行——安全边界只读侧才放松。"""
        assert is_read_only_tool(tool) is False

    def test_read_only_set_contains_no_write_tools(self):
        """白名单自身不得混入写/删/发类操作。"""
        from app.services.approval_policy import READ_ONLY_TOOLS

        for name in READ_ONLY_TOOLS:
            assert not any(
                token in name
                for token in ("write", "delete", "replace", "append", "send", "commit")
            ), f"{name} 是写操作，不该在只读白名单里"


class TestDefaultApprovalModeIsAuto:
    """默认档位必须是 auto。

    此前整条链路（schema / profile 服务 / factory / 前端请求体）全部硬编码
    ``ask``，导致上面那套 auto 机制形同虚设——只读工具照样逐次确认。
    任何一端漏改都会让「点 45 次」的问题复发，所以在这里钉死。
    """

    def test_chat_request_defaults_to_auto(self):
        from app.schemas.agent import AgentStreamRequest

        assert AgentStreamRequest(message="hi").approval_mode == "auto"

    def test_profile_service_defaults_to_auto(self):
        from app.services.agent_profile_service import AgentProfileService

        sig = inspect.signature(AgentProfileService.resolve_runtime_by_mode)
        assert sig.parameters["approval_mode"].default == "auto"
        assert sig.parameters["plan_mode"].default is False

    def test_hitl_middleware_defaults_to_auto(self):
        from app.services.agent.factory import LenientHitlMiddleware

        sig = inspect.signature(LenientHitlMiddleware.__init__)
        assert sig.parameters["approval_mode"].default == "auto"


class TestPlanMode:
    def test_blocks_write_tools_keeps_read_only(self):
        blocked = plan_mode_blocked_tools(["calc", "time", "file", "python", "knowledge"])
        assert sorted(blocked) == ["file", "python"]

    def test_read_only_only_profile_blocks_nothing(self):
        assert plan_mode_blocked_tools(["time", "calc", "knowledge", "memory"]) == []

    def test_empty_profile_is_safe(self):
        assert plan_mode_blocked_tools([]) == []

    def test_prompt_suffix_forbids_side_effects(self):
        assert "只读" in PLAN_MODE_PROMPT_SUFFIX or "查询" in PLAN_MODE_PROMPT_SUFFIX
        assert "禁止" in PLAN_MODE_PROMPT_SUFFIX
        assert "批准" in PLAN_MODE_PROMPT_SUFFIX
