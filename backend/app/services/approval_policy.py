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
