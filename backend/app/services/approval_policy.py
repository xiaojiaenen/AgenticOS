"""工具审批模式（会话级三档）。

背景
----
此前只有「按工具勾选是否需要审批」，导致两难：全都要确认 → 啰嗦，
要���都放开 → 危险。借鉴 Open WebUI 的三档设计：

- ``ask``（默认，维持旧行为）：被标记需审批的工具逐次询问
- ``auto``：**只读工具自动放行**，写/执行类仍逐次确认
- ``full``：全部自动放行（仅管理员可用）

只读判定是**保守白名单**：未列入的一律视为"需要审批"，
新增工具在未被显式归类前默认走最严格路径。
"""

from __future__ import annotations

APPROVAL_MODES = ("ask", "auto", "full")
DEFAULT_APPROVAL_MODE = "ask"

# 只读工具：只读取/查询，不改变系统状态
READ_ONLY_TOOLS: frozenset[str] = frozenset({
    # 基础计算与时间
    "time", "calc",
    # 检索类
    "knowledge", "memory", "file_to_md",
    # 幻灯片只读操作
    "read_slide", "read_notes", "check_ppt_progress", "check_svg_quality",
    "calc_chart_positions", "analyze_template",
    # 图片/图标检索
    "search_images", "get_image_info", "search_icons", "list_icons",
    # 技能说明加载（只读）
    "skill",
    # 数据分析：产出结果给用户看，不落盘
    "analyze_data",
})

# 只读子操作（粒度更细的工具：file / email）
READ_ONLY_SUB_TOOLS: frozenset[str] = frozenset({
    "read_text_file",
    "list_files",
    # 邮件侧只读动作
    "list_email_folders", "list_emails", "read_email", "search_emails",
})


def normalize_approval_mode(mode: str | None) -> str:
    """归一化审批模式，非法值回退到默认 ask。"""
    value = (mode or "").strip().lower()
    return value if value in APPROVAL_MODES else DEFAULT_APPROVAL_MODE


def is_read_only_tool(tool_name: str, arguments: dict | None = None) -> bool:
    """判断一次工具调用是否只读。

    细粒度工具（file / email）按 ``action`` 参数判断子操作；
    其余按工具名白名单判断。
    """
    if tool_name in READ_ONLY_TOOLS:
        return True

    if arguments and isinstance(arguments, dict):
        action = arguments.get("action") or arguments.get("operation")
        if isinstance(action, str) and action.strip().lower() in READ_ONLY_SUB_TOOLS:
            return True

    return False


def plan_mode_blocked_tools(
    enabled_tools: list[str] | tuple[str, ...],
) -> list[str]:
    """计划模式下应当被剥离的工具（非只读能力）。

    计划模式只允许"读和调研"，产出一份计划；写/执行能力在用户批准前
    一律不下发给模型，从源头避免误操作，而不是靠事后拦截。
    """
    return [name for name in enabled_tools if not is_read_only_tool(name)]


PLAN_MODE_PROMPT_SUFFIX = """

---
## 当前处于「计划模式」

你只能调用查询与检索类工具（读取文件、查知识库、算数据等）来了解现状，
**禁止**修改文件、执行脚本、发送邮件、部署或任何产生副作用的操作。

请先调研清楚，再输出一份**可执行的计划**，包含：
1. 现状与约束（调研到的关键事实）
2. 步骤拆解（每步做什么、用什么手段）
3. 风险与需要用户确认的点

用户批准计划后，才会切回正常模式执行。计划要具体到可执行，不要泛泛而谈。
"""
