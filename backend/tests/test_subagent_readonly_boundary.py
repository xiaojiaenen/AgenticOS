"""子代理工具边界回归：DeepAgents 子代理不共享主 agent 的审批通道，
因此只能暴露无副作用的只读工具。

背景：排查发现 `_native_tools_for()` 曾把 run_python_script / git_add /
write_text_file 等工具原样交给子代理，提示注入可借 task() 派单给子代理，
以服务进程权限零审批执行任意脚本 / 写任意路径。
"""

from __future__ import annotations

from app.services.agent.factory import AgentFactory


def _factory() -> AgentFactory:
    # _native_tools_for 不依赖实例状态；用 __new__ 绕过构造时的 DB/LLM 初始化。
    return AgentFactory.__new__(AgentFactory)


def test_subagent_tools_are_read_only_only():
    factory = _factory()
    tools = factory._native_tools_for(["calc", "python", "git", "file"])
    names = {t.name for t in tools}

    assert "run_python_script" not in names, "脚本执行不得交给无审批通道的子代理"
    assert "git_add" not in names and "git_commit" not in names
    assert "write_text_file" not in names and "append_text_file" not in names
    assert "delete_file" not in names and "replace_text_in_file" not in names
    # 只读工具应保留
    assert {"calculate", "git_status", "git_diff"}.issubset(names)


def test_subagent_read_only_tools_have_no_side_effect_flag():
    """暴露给子代理的每一个工具都必须是无副作用、不需审批的。"""
    from app.services.agent.native.tool_registry import ToolRegistry
    from app.services.agent.native.plugins import PluginContext

    factory = _factory()
    # 直接检查 factory 过滤后的工具来源：重新构建原始注册表对照
    reg = ToolRegistry()
    ctx = PluginContext(tool_registry=reg)
    for name in ("calc", "python", "git", "file"):
        mod = __import__(f"app.services.agent.native.builtin.{name}", fromlist=["setup"])
        mod.setup(ctx)
    exposed = {t.name for t in factory._native_tools_for(["calc", "python", "git", "file"])}
    for tool in reg.list_tools():
        if tool.name not in exposed:
            continue
        execution = getattr(tool, "execution", None)
        assert not getattr(execution, "side_effect", False)
        assert not getattr(execution, "requires_approval", False)
