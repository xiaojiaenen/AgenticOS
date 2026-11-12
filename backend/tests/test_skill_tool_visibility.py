"""技能工具（load_skill / list_skills）必须出现在智能体的工具白名单里。

## 背景（真实故障）

PPT / 网站智能体的系统提示词反复要求「生成前必须先 ``load_skill(...)``」，
但模型调用 ``load_skill`` 总是失败 —— 模型根本看不到这个工具。

根因不在 wuwei：``setup_skill_plugin`` 确实把 ``load_skill`` / ``list_skills``
注册进了工具表。是**我们自己的白名单**把它裁掉的：

``AgentProfileService._compute_allowed_tools`` 只放行「某个已启用的
catalog 条目管辖的具体工具名」（条目 → ``sub_tools`` / ``approval_scope``）。
而 catalog 的 ``skill`` 条目当时只声明了 ``run_skill_python_script`` ——
``load_skill`` / ``list_skills`` 不在里面，于是被 factory 的白名单裁剪
（``_unregister_if_exists``）注销掉。

结果：工具注册了但模型看不见，模型只能对着提示词空喊，工具调用直接失败。
"""
from __future__ import annotations

from app.services.tool_config_service import TOOL_CATALOG


def test_skill_catalog_declares_load_and_list_skills() -> None:
    """catalog 的 skill 条目必须声明 load_skill / list_skills。

    漏了会被 allowed_tools 白名单裁掉 —— 工具注册了但模型看不见。
    """
    entry = TOOL_CATALOG["skill"]
    sub_tools = entry.get("sub_tools", {})
    assert "load_skill" in sub_tools, (
        "catalog 的 skill 条目缺少 load_skill：它会被 allowed_tools 白名单裁剪，"
        "模型看不到这个工具，提示词里的 load_skill(...) 必然失败"
    )
    assert "list_skills" in sub_tools, (
        "catalog 的 skill 条目缺少 list_skills：同上"
    )
    # 加载技能是只读动作，不该要人工审批
    assert "load_skill" not in entry.get("approval_scope", [])
    assert "list_skills" not in entry.get("approval_scope", [])


def test_load_skill_is_in_allowed_tools_for_skill_enabled_profile() -> None:
    """skill 条目启用时，load_skill / list_skills 必须进白名单。"""
    from app.services.agent_profile_service import AgentProfileService

    allowed = AgentProfileService._compute_allowed_tools(
        "ppt",
        enabled_catalog_names={"skill"},
    )
    assert "load_skill" in allowed
    assert "list_skills" in allowed


def test_load_skill_not_allowed_when_skill_tool_disabled() -> None:
    """skill 条目关闭时，load_skill 也不该放行（管理员关了就是关了）。"""
    from app.services.agent_profile_service import AgentProfileService

    allowed = AgentProfileService._compute_allowed_tools(
        "ppt",
        enabled_catalog_names=set(),
    )
    assert "load_skill" not in allowed
