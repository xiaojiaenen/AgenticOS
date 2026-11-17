"""两处修复的回归。

## 1. 通用助手 render 系列全部执行失败

用户报「通用助手为啥 render 相关的都执行失败」。根因是**白名单算法漏了
一类工具**：`_compute_allowed_tools` 只从 catalog 条目的 `sub_tools` /
`approval_scope` / `builtin_name` 收集工具名，而 render_ui / render_form /
render_components / update_interface / generate_image 这类工具在目录里是
「条目名即工具名」（没有 sub_tools，因为是单个动作而不是一组）。

于是它们两头都不沾：
- 不在 `managed_by_catalog`（sub_tools 为空）
- 不在 `_discover_all_mode_tools()`（a2ui / image_gen 是 factory 直接注册的，
  不在 per-mode registrar 里）

结果永远进不了白名单，注册表被裁掉后模型调用就 ToolNotFound。

## 2. 创建智能体不能选上架

编辑器把 `listed: false` 写死了，没有任何 UI；后端 update 也不拦普通用户
改 listed（有权限洞）。现在：管理员能在编辑器勾选，普通用户看到说明文字；
后端两条路径（create / update）都拦住非管理员。
"""

from __future__ import annotations

import pytest


class TestRenderToolsAllowed:
    """render 系列必须在通用助手的白名单里。"""

    @staticmethod
    def _allowed_for_general() -> frozenset[str]:
        from app.services.agent_profile_service import AgentProfileService
        from app.services.tool_config_service import DEFAULT_MODE_TOOLS

        enabled = {
            name
            for name, cfg in DEFAULT_MODE_TOOLS["general"].items()
            if cfg.get("enabled")
        }
        return AgentProfileService._compute_allowed_tools(
            "general", enabled_catalog_names=enabled
        )

    @pytest.mark.parametrize(
        "tool",
        [
            "render_ui",
            "render_form",
            "render_components",
            "update_interface",
            "generate_image",
            "render_chart",
            "analyze_data",
        ],
    )
    def test_global_tool_is_whitelisted(self, tool):
        allowed = self._allowed_for_general()
        assert tool in allowed, (
            f"{tool} 不在通用助手白名单里 —— 模型调用会 ToolNotFound，"
            "表现为「render 相关的都执行失败」"
        )

    def test_disabling_entry_blocks_the_tool(self):
        """关掉条目后必须被拦住 —— 不能为了修 bug 变成无条件放行。"""
        from app.services.agent_profile_service import AgentProfileService
        from app.services.tool_config_service import DEFAULT_MODE_TOOLS

        enabled = {
            name
            for name, cfg in DEFAULT_MODE_TOOLS["general"].items()
            if cfg.get("enabled")
        } - {"render_ui", "render_form", "render_components", "update_interface"}
        allowed = AgentProfileService._compute_allowed_tools(
            "general", enabled_catalog_names=enabled
        )
        assert "render_ui" not in allowed, "关掉 a2ui 条目后 render_ui 仍放行"

    def test_file_tools_still_gated_by_switch(self):
        """回归：file 类工具仍必须看 file 条目的开关（别把上一轮的修复弄坏）。"""
        from app.services.agent_profile_service import AgentProfileService
        from app.services.tool_config_service import DEFAULT_MODE_TOOLS

        # general 里 file 是启用的 → 文件工具应放行
        enabled = {
            name
            for name, cfg in DEFAULT_MODE_TOOLS["general"].items()
            if cfg.get("enabled")
        }
        allowed = AgentProfileService._compute_allowed_tools(
            "general", enabled_catalog_names=enabled
        )
        assert "write_text_file" in allowed

        # 关掉 file → 文件工具全不放行
        allowed_off = AgentProfileService._compute_allowed_tools(
            "general", enabled_catalog_names=enabled - {"file"}
        )
        for tool in ("write_text_file", "read_text_file", "delete_file"):
            assert tool not in allowed_off, f"关掉 file 后 {tool} 仍放行"


class TestListedPermission:
    """上架是平台级动作：管理员可以，普通用户不行。"""

    def test_creator_can_list_only_for_admin(self):
        from app.services.agent_profile_service import AgentProfileService

        class _U:
            def __init__(self, role):
                self.role = role

        assert AgentProfileService._creator_can_list(_U("admin")) is True
        assert AgentProfileService._creator_can_list(_U("superadmin")) is True
        assert AgentProfileService._creator_can_list(_U("user")) is False
        assert AgentProfileService._creator_can_list(_U("operator")) is False

    def test_update_guards_listed_for_normal_user(self):
        """源码层断言：update 里 listed 的写入有角色检查。

        真正跑端点需要造用户 + 建 profile，这里用源码断言守住"检查还在"
        （这个洞之前确实存在：前端藏了开关，但直接调 API 能改）。
        """
        src = open(
            "app/services/agent_profile_service.py", encoding="utf-8"
        ).read()
        # 定位 listed 的 update 分支
        idx = src.index("if request.listed is not None:")
        block = src[idx : idx + 700]
        assert "is_admin_like" in block, "update 里没有对 listed 做角色检查"
        assert "PermissionError" in block, "update 里 listed 越权时未拒绝"

    def test_create_guards_listed(self):
        src = open(
            "app/services/agent_profile_service.py", encoding="utf-8"
        ).read()
        assert "_creator_can_list" in src, "create 路径未使用 _creator_can_list 把关"
        # create 里的 listed 赋值必须经过它
        idx = src.index("listed=bool(request.listed and self._creator_can_list")
        assert idx > 0
