"""表格工具 — 让 agent 用 Univer 的 Facade 语义造表，而不是手拼 JSON。

设计要点：工具的错误信息是写给模型看的，必须可执行。「区域记法非法」没用，
「数据超出区域 A1:C1 的容量（1 行 × 3 列），收到 2 行 × 3 列，请扩大区域
记法」才有用——运行时已经这么回了，这里只做兜底。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from wuwei.tools import ToolRegistry

from app.core.data_path import get_current_session_id, get_current_user_id
from app.services.office import service as sheet

logger = logging.getLogger("agent.sheet.tools")

#: 一次写入允许的最大单元格数。防止模型误传一个 10 万行的数组把运行时打挂。
MAX_CELLS_PER_WRITE = 20_000


def _session_id() -> str:
    session_id = get_current_session_id()
    if not session_id:
        raise sheet.SheetServiceError("缺少会话 ID，无法操作表格")
    return session_id


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def register_sheet_tools(registry: ToolRegistry) -> None:
    """注册表格工具。由 tool_config_service 在 sheet 模式下自动发现。"""

    @registry.tool(display_name="新建表格")
    async def create_workbook(name: str, sheet_name: str = "Sheet1") -> str:
        """新建一个空白表格工作簿，作为本轮对话的表格起点。

        每次对话只能有一个活动工作簿；重复调用会覆盖之前的内容，所以只在
        真正要重新开始时使用。要给已有表格加内容，用 set_range / add_sheet。

        参数:
          name: 表格标题，例如「2026 上半年销售汇总」
          sheet_name: 第一个工作表的名称，默认 "Sheet1"

        返回:
          工作簿标识与已有工作表列表
        """
        try:
            result = await sheet.create_workbook(
                _session_id(), get_current_user_id(), name, sheet_name
            )
        except sheet.SheetServiceError as exc:
            return f"新建失败：{exc}"
        return _json(result)

    @registry.tool(display_name="写入单元格")
    async def set_range(
        range: str, values: list[list[Any]], sheet_name: str | None = None
    ) -> str:
        """把一块矩形区域的数据写进表格，会覆盖原有内容。

        参数:
          range: 区域记法，如 "A1:C3"（左上角:右下角）
          values: 二维数组，行列数必须与区域完全对应。
                  例如 range="A1:C3" 时，values 需要是 3 行、每行 3 个值。
                  数字直接写数字，不要带引号；留空用 null。
          sheet_name: 目标工作表名，省略则用当前工作表

        返回:
          写入结果，含工作表名
        """
        try:
            session_id = _session_id()
        except sheet.SheetServiceError as exc:
            return f"写入失败：{exc}"

        if not isinstance(values, list) or not values:
            return "写入失败：values 必须是非空二维数组，例如 [[\"季度\",\"销售额\"],[\"Q1\",120]]"
        if any(not isinstance(row, list) for row in values):
            return "写入失败：values 的每一项都必须是数组（表格的每一行）"
        cell_count = sum(len(row) for row in values)
        if cell_count > MAX_CELLS_PER_WRITE:
            return (
                f"写入失败：一次最多写 {MAX_CELLS_PER_WRITE} 个单元格，"
                f"收到 {cell_count} 个。请拆成多次调用。"
            )

        try:
            result = await sheet.set_range(session_id, sheet_name, range, values)
        except sheet.SheetServiceError as exc:
            return f"写入失败：{exc}"
        return _json(result)

    @registry.tool(display_name="设置公式")
    async def set_formula(
        range: str, formula: str, sheet_name: str | None = None
    ) -> str:
        """给一个或多个单元格设置 Excel 公式。

        公式会在写入后立刻计算，返回值里能看到算出来的结果——请核对结果是否
        符合预期，不符合就调整公式。

        参数:
          range: 区域记法，如 "B4" 或 "B2:B10"
          formula: 公式文本，必须以 = 开头，如 "=SUM(B2:B3)"、'=IF(A2>0,"是","否")'
          sheet_name: 目标工作表名，省略则用当前工作表

        返回:
          计算结果
        """
        try:
            session_id = _session_id()
            result = await sheet.set_formula(session_id, sheet_name, range, formula)
        except sheet.SheetServiceError as exc:
            return f"设置公式失败：{exc}"
        return _json(result)

    @registry.tool(display_name="新增工作表")
    async def add_sheet(
        name: str, rows: int = 200, columns: int = 26
    ) -> str:
        """在当前工作簿里新增一个工作表。

        参数:
          name: 工作表名称
          rows: 行数上限，默认 200
          columns: 列数上限，默认 26

        返回:
          新增后的全部工作表列表
        """
        try:
            result = await sheet.add_sheet(_session_id(), name, rows, columns)
        except sheet.SheetServiceError as exc:
            return f"新增工作表失败：{exc}"
        return _json(result)

    @registry.tool(display_name="读取单元格")
    async def read_range(
        range: str | None = None, sheet_name: str | None = None
    ) -> str:
        """读回表格内容，用于核对写入结果或取数继续计算。

        参数:
          range: 区域记法；省略则返回有数据的全部区域
          sheet_name: 工作表名，省略则用当前工作表

        返回:
          单元格原始值与格式化后的显示值
        """
        try:
            result = await sheet.read_range(_session_id(), sheet_name, range)
        except sheet.SheetServiceError as exc:
            return f"读取失败：{exc}"
        return _json(result)

    @registry.tool(display_name="设置版式")
    async def set_layout(
        frozen_rows: int | None = None,
        column_widths: dict[str, int] | None = None,
        sheet_name: str | None = None,
    ) -> str:
        """调整表格版式：冻结表头行、设置列宽。

        参数:
          frozen_rows: 冻结前 N 行（表头常用 1）
          column_widths: 列宽映射，键是 0 起的列号，值是像素宽度。
                         例如 {"0": 160, "1": 120}
          sheet_name: 工作表名，省略则用当前工作表

        返回:
          版式结果
        """
        try:
            result = await sheet.set_layout(
                _session_id(), sheet_name, column_widths, frozen_rows
            )
        except sheet.SheetServiceError as exc:
            return f"设置版式失败：{exc}"
        return _json(result)

    @registry.tool(display_name="查看表格结构")
    async def describe_workbook() -> str:
        """查看当前工作簿有哪些工作表、各自的数据范围和规模。

        返回:
          工作簿结构描述
        """
        try:
            result = await sheet.describe(_session_id())
        except sheet.SheetServiceError as exc:
            return f"查看失败：{exc}"
        return _json(result)

    @registry.tool(display_name="完成表格")
    async def build_sheet() -> str:
        """完成表格并产出预览。写完所有内容后必须调用一次，否则用户看不到成果。

        产出会作为可编辑的表格展示在对话右侧，用户可以直接改。

        返回:
          产物标识、工作表列表
        """
        try:
            result = await sheet.build(_session_id())
        except sheet.SheetServiceError as exc:
            return f"完成失败：{exc}"
        # 快照本体不进返回值：它会占满模型上下文，产物展示走 artifact 事件。
        return _json(
            {
                "workbook_id": result["workbook_id"],
                "title": result["title"],
                "sheet_names": result["sheet_names"],
                "sheet_count": result["sheet_count"],
            }
        )
