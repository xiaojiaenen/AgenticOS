"""按**运行时实际注册的工具**生成能力边界说明，注入 system prompt。

**为什么不能写死在提示词里**：管理员随时可能在「智能体配置」里给任意智能体
开/关工具。写死的「你没有 PPT 工具」一旦被管理员打开就是假话 ——
模型会拒绝本该能做的事；反过来，写死的「你可以做 PPT」在工具被关掉后
会让模型去调用不存在的工具，用户看到一串 `ToolNotFound` 红卡片
（2026-11-16 真实故障：通用助手里说「改一下风格」，模型调
read_slide / load_skill / save_slides_batch 全部失败）。

**本模块的职责**：拿最终注册表里的工具名集合，推导出
1. 用户能在这个智能体里完成哪些任务类型（有工具支撑的）；
2. 哪些任务类型当前**没有**工具支撑 —— 明确告知用户去切换智能体，
   而不是让模型硬调一个不存在的工具名。

判断「某能力是否具备」用的是**工具名组的交集**，不是模式名：
所以管理员给通用助手开了 read_slide，它就会正确显示「可以读幻灯片」。
"""
from __future__ import annotations

#: 能力 → 支撑它的工具名（命中任意一个即视为具备该能力）
_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "生成/修改 PPT 幻灯片": (
        "save_slide",
        "save_slides_batch",
        "read_slide",
        "batch_edit_slides",
    ),
    "生成网站": ("build_website", "copy_template"),
    "部署网站": ("deploy_website",),
    "编辑电子表格": ("create_workbook", "set_range", "build_sheet"),
    "编辑文档": ("create_document", "set_document_text", "build_document"),
    "收发邮件": ("email",),
}

#: 各能力对应的、带该能力的内置智能体（用于「请切换到 X」的建议）
_CAPABILITY_AGENT: dict[str, str] = {
    "生成/修改 PPT 幻灯片": "PPT 设计师",
    "生成网站": "网站工程师",
    "部署网站": "网站工程师",
    "编辑电子表格": "办公助手",
    "编辑文档": "办公助手",
    "收发邮件": "邮箱助手",
}

#: 模式 → 人类可读的名称（注入文案里用）
_MODE_LABEL: dict[str, str] = {
    "general": "通用助手",
    "ppt": "PPT 设计师",
    "website": "网站工程师",
    "office": "办公助手",
    "email": "邮箱助手",
    "bigdata": "大数据运维",
}


def _has_any(registered: set[str], tools: tuple[str, ...]) -> bool:
    return any(t in registered for t in tools)


def build_capability_hint(*, registry_tool_names: set[str], response_mode: str) -> str:
    """生成能力边界段落；没有可说的内容时返回空串。

    ``registry_tool_names`` 必须是**白名单裁剪之后**的最终集合 —— 用原始
    注册表会把「模式注册了但被 profile 关掉」的工具也算进来，得出的
    「你能做 X」又是假话。
    """
    if not registry_tool_names:
        return ""

    available: list[str] = []
    missing: list[tuple[str, str]] = []  # (能力, 建议切换的智能体)

    for capability, tools in _CAPABILITIES.items():
        if _has_any(registry_tool_names, tools):
            available.append(capability)
        else:
            agent = _CAPABILITY_AGENT.get(capability)
            # 自己的能力不提示「去切换」（本模式不做这件事是正常的，
            # 例如邮箱助手不需要提示它不能生成 PPT）
            if agent and response_mode not in _modes_owning(capability):
                missing.append((capability, agent))

    if not available and not missing:
        return ""

    mode_label = _MODE_LABEL.get(response_mode, response_mode)
    lines = [f"## 能力边界（当前智能体：{mode_label}）", ""]

    if available:
        lines.append("你当前**可以**完成：" + "、".join(available) + "。")

    if missing:
        lines.append("")
        lines.append(
            "以下任务你**当前没有对应工具**（不要尝试调用不存在的工具名，"
            "那只会产生 ToolNotFound 失败卡片）："
        )
        # 同一智能体的多条能力合并成一行
        by_agent: dict[str, list[str]] = {}
        for capability, agent in missing:
            by_agent.setdefault(agent, []).append(capability)
        for agent, caps in by_agent.items():
            lines.append(f"- {'、'.join(caps)} → 请用户在输入框左侧切换到「{agent}」")

    lines.append("")
    lines.append(
        "工具清单以你上下文的 tools 定义为准（管理员的配置随时可能变化）。"
        "用户要求的能力不在其中时，**直接说明并给出切换建议**，"
        "不要假装已经完成，也不要说「我已经读到了第 N 页」。"
    )
    return "\n".join(lines)


def _modes_owning(capability: str) -> set[str]:
    """哪些模式天然拥有该能力（这些模式下不该提示「去切换」）。"""
    agent = _CAPABILITY_AGENT.get(capability)
    if not agent:
        return set()
    return {mode for mode, label in _MODE_LABEL.items() if label == agent}
