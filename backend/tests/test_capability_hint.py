"""能力边界提示（动态生成，跟随实际注册工具）。

真实故障（2026-11-16）：通用助手里说「改一下风格」，模型调用了
read_slide / load_skill / save_slides_batch，全部 ToolNotFound。

**修法必须动态**：管理员随时可能在「智能体配置」里开/关任意工具，
写死提示词（「你没有 PPT 工具」）在配置变更后就是假话。
本模块从**最终注册表**推导能力边界，工具开了就不再提示切换。
"""
from __future__ import annotations

from app.services.agent.capability_hint import build_capability_hint


class TestCapabilityHint:
    def test_general_mode_without_ppt_tools(self):
        """通用助手没有 PPT 工具 → 提示去切换，而不是让模型硬调。"""
        hint = build_capability_hint(
            registry_tool_names={"calc", "time", "read_text_file", "write_text_file"},
            response_mode="general",
        )
        assert "能力边界" in hint
        assert "通用助手" in hint
        assert "生成/修改 PPT 幻灯片" in hint
        assert "PPT 设计师" in hint
        assert "ToolNotFound" in hint

    def test_general_mode_with_ppt_tools_enabled(self):
        """管理员给通用助手开了 save_slide → 提示必须变成「可以完成」。"""
        hint = build_capability_hint(
            registry_tool_names={"calc", "save_slide", "read_slide"},
            response_mode="general",
        )
        assert "你当前**可以**完成" in hint
        assert "生成/修改 PPT 幻灯片" in hint
        # 不能再提示「切换到 PPT 设计师」—— 它现在自己能做
        assert "切换到「PPT 设计师」" not in hint

    def test_ppt_mode_does_not_suggest_switching_to_itself(self):
        """PPT 设计师不该提示自己「去切换成 PPT 设计师」。"""
        hint = build_capability_hint(
            registry_tool_names={"save_slide", "read_slide", "save_slides_batch"},
            response_mode="ppt",
        )
        assert "你当前**可以**完成" in hint
        assert "切换到「PPT 设计师」" not in hint
        # 其他能力仍然提示
        assert "网站工程师" in hint

    def test_office_mode_with_sheet_tools(self):
        hint = build_capability_hint(
            registry_tool_names={"create_workbook", "set_range", "build_sheet"},
            response_mode="office",
        )
        assert "编辑电子表格" in hint
        assert "切换到「办公助手」" not in hint

    def test_email_mode_with_email_tool(self):
        hint = build_capability_hint(
            registry_tool_names={"email"},
            response_mode="email",
        )
        assert "收发邮件" in hint
        assert "切换到「邮箱助手」" not in hint

    def test_empty_registry_returns_empty(self):
        assert build_capability_hint(registry_tool_names=set(), response_mode="general") == ""

    def test_multiple_capabilities_grouped_by_agent(self):
        """多条能力属于同一智能体时合并成一行，不重复刷屏。"""
        hint = build_capability_hint(
            registry_tool_names={"calc"},
            response_mode="general",
        )
        # 生成网站 + 部署网站 都属于网站工程师
        website_lines = [ln for ln in hint.split("\n") if "网站工程师" in ln]
        assert len(website_lines) == 1
        assert "生成网站" in website_lines[0] and "部署网站" in website_lines[0]

    def test_hint_states_tool_list_is_authoritative(self):
        """提示必须说明「以上下文 tools 为准」，避免配置变更后又说假话。"""
        hint = build_capability_hint(
            registry_tool_names={"calc"},
            response_mode="general",
        )
        assert "以你上下文的 tools 定义为准" in hint
        assert "随时可能变化" in hint
