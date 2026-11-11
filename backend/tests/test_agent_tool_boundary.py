"""智能体工具越界防线：不得使用 profile 未配置的工具 / skill。

## 背景

注册表里有两类工具来源，管控方式原本不一致：

1. **builtin 插件类**（calc / time / file / python / git / npm）：受 profile
   的 enabled 开关控制，通过 builtin_tools 下发。
2. **模式注册类**（website_tools / sheet_tools / doc_tools / email_tools /
   website_file_tools）：按 response_mode **整体注册**，此前完全绕过
   profile 配置。

后果实测：通用助手的 builtin_tools 只有 calc/file/time，但注册表里带着
`write_text_file` / `delete_file` / `deploy_website`；管理员在界面上关掉
「文件工具」，写文件工具照样可用。

## 修复

`AgentProfileService._compute_allowed_tools` 产出权威白名单，注册表构建后
按它裁剪（`AgentFactory._build_tool_registry`）。

规则：一个具体工具能被下发，当且仅当
- 它在某个**已启用**的 catalog 条目下（sub_tools / approval_scope / builtin_name），或
- 它是**纯模式级**工具（没有 catalog 归属，如 create_workbook）。
"""

from __future__ import annotations

import pytest

from app.services.agent_profile_service import AgentProfileService


def _allowed(mode: str, enabled: set[str]) -> frozenset[str]:
    return AgentProfileService._compute_allowed_tools(
        mode, enabled_catalog_names=enabled
    )


class TestFileToolBoundary:
    """file 条目是越界的核心案例：它的子工具在所有模式无条件注册。"""

    def test_file_enabled_allows_its_sub_tools(self):
        allowed = _allowed("general", {"calc", "time", "file", "decision"})
        for name in (
            "read_text_file",
            "write_text_file",
            "append_text_file",
            "replace_text_in_file",
            "delete_file",
            "list_files",
        ):
            assert name in allowed, f"file 启用时 {name} 应放行"

    def test_file_disabled_blocks_all_sub_tools(self):
        allowed = _allowed("general", {"calc", "time", "decision"})
        for name in (
            "read_text_file",
            "write_text_file",
            "append_text_file",
            "replace_text_in_file",
            "delete_file",
            "list_files",
        ):
            assert name not in allowed, f"file 关闭时 {name} 必须不放行"

    def test_disabling_file_does_not_affect_other_tools(self):
        allowed = _allowed("general", {"calc", "time", "decision"})
        assert "calculate" in allowed, "关掉 file 不该影响 calc"
        assert "get_now" in allowed, "关掉 file 不该影响 time"


class TestWebsiteToolBoundary:
    def test_deploy_requires_its_own_entry(self):
        """deploy_website 有独立 catalog 条目，必须单独启用。"""
        with_deploy = _allowed("website", {"file", "build_website", "deploy_website"})
        without = _allowed("website", {"file", "build_website"})
        assert "deploy_website" in with_deploy
        assert "deploy_website" not in without

    def test_website_mode_does_not_leak_office_tools(self):
        """网站工程师不该拿到表格/文档工具。"""
        allowed = _allowed("website", {"file", "build_website", "deploy_website"})
        for name in ("create_workbook", "create_document", "set_range"):
            assert name not in allowed, f"网站模式不应有 {name}"

    def test_website_mode_does_not_leak_email_tools(self):
        allowed = _allowed("website", {"file", "build_website"})
        for name in ("send_email", "read_emails", "search_emails"):
            assert name not in allowed, f"网站模式不应有 {name}"


class TestOfficeToolBoundary:
    def test_office_gets_sheet_and_doc_tools(self):
        """办公模式的表格/文档工具是纯模式级工具（无 catalog 归属）。"""
        allowed = _allowed("office", {"file", "file_to_md", "decision"})
        for name in ("create_workbook", "create_document", "set_range", "read_range"):
            assert name in allowed, f"办公模式应有 {name}"

    def test_office_does_not_leak_deploy(self):
        allowed = _allowed("office", {"file", "file_to_md"})
        assert "deploy_website" not in allowed


class TestEmailToolBoundary:
    def test_email_mode_gets_mail_tools(self):
        allowed = _allowed("email", {"file", "email", "decision"})
        for name in ("send_email", "read_emails", "search_emails"):
            assert name in allowed, f"邮箱模式应有 {name}"

    def test_email_disabled_blocks_mail_tools(self):
        allowed = _allowed("email", {"file", "decision"})
        for name in ("send_email", "read_emails", "search_emails"):
            assert name not in allowed, f"email 关闭时 {name} 必须不放行"


class TestGeneralBoundary:
    def test_general_mode_has_no_mode_specific_tools(self):
        """通用助手不该拿到任何网站/办公/邮箱专属工具。"""
        allowed = _allowed("general", {"calc", "time", "file", "decision"})
        for name in (
            "deploy_website", "build_website", "copy_template",
            "create_workbook", "create_document",
            "send_email", "read_emails",
        ):
            assert name not in allowed, f"通用模式不应有 {name}"
