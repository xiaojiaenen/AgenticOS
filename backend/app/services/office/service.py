"""表格工作簿的服务层（办公模式 Excel 部分）：生命周期管理 + 快照落盘。

职责边界：
  runtime.py  — 进程与 IPC（只认 op/args，不认业务）
  service.py  — 本文件，业务语义（工作簿属于谁、快照存哪、怎么找回来）
  tools/      — 暴露给 LLM 的工具

快照格式是 Univer 的 `IWorkbookData` 原始 JSON。整体存、整体读，不挑字段：
`appVersion` / `rev` / 内部化的 `styles` 引用表手改会破坏前向兼容。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.core.data_path import SHEETS_DIR, next_version_dir
from app.services.office.runtime import OfficeRuntimeError, get_office_runtime

logger = logging.getLogger("agent.office.sheet")

#: 运行时里同时保留的工作簿上限。超出按最后访问时间淘汰，防止长跑进程
#: 因为 agent 反复建表而无限吃内存。
MAX_LIVE_WORKBOOKS = 32

#: 运行时工作簿的空闲回收时间（秒）。
IDLE_TTL = 30 * 60

#: session_id → {key, dir, workbook_id, title, last_used}
_sessions: dict[str, dict[str, Any]] = {}


class SheetServiceError(RuntimeError):
    """表格服务层的可预期错误（会原样回给 LLM 修正）。"""


def _session_key(session_id: str) -> str:
    return f"sheet:{session_id}"


def _prune() -> None:
    """淘汰超时或超量的工作簿。"""
    now = time.monotonic()
    stale = [sid for sid, meta in _sessions.items() if now - meta["last_used"] > IDLE_TTL]
    for sid in stale:
        _sessions.pop(sid, None)
    overflow = len(_sessions) - MAX_LIVE_WORKBOOKS
    if overflow > 0:
        oldest = sorted(_sessions.items(), key=lambda kv: kv[1]["last_used"])[:overflow]
        for sid, _meta in oldest:
            _sessions.pop(sid, None)


def forget_session(session_id: str) -> None:
    """丢弃内存中的工作簿（对话结束或切换产物时调用）。不删磁盘快照。"""
    _sessions.pop(session_id, None)


def _require_session(session_id: str) -> dict[str, Any]:
    meta = _sessions.get(session_id)
    if meta is None:
        raise SheetServiceError(
            "当前会话还没有表格。请先调用 create_workbook 新建一个工作簿。"
        )
    meta["last_used"] = time.monotonic()
    return meta


async def _call(op: str, **args: Any) -> dict[str, Any]:
    try:
        return await get_office_runtime().call(op, **args)
    except OfficeRuntimeError as exc:
        raise SheetServiceError(str(exc)) from exc


# ── 工作簿操作（供 tools 层调用）──────────────────────────────────────────


async def create_workbook(
    session_id: str, user_id: int, name: str, sheet_name: str = "Sheet1"
) -> dict[str, Any]:
    """新建（或重建）当前会话的工作簿。"""
    _prune()
    directory = next_version_dir(SHEETS_DIR, user_id, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    workbook_id = directory.name

    result = await _call(
        "create_workbook",
        key=_session_key(session_id),
        id=workbook_id,
        name=name,
        sheetName=sheet_name,
    )
    _sessions[session_id] = {
        "key": _session_key(session_id),
        "user_id": user_id,
        "dir": directory,
        "workbook_id": workbook_id,
        "title": name,
        "last_used": time.monotonic(),
    }
    logger.info("表格已创建: %s (%s)", workbook_id, name)
    return {**result, "title": name, "directory": directory.name}


async def set_range(
    session_id: str, sheet: str | None, range_: str, values: list[list[Any]]
) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call(
        "set_range", key=meta["key"], sheet=sheet, range=range_, values=values
    )


async def set_formula(
    session_id: str, sheet: str | None, range_: str, formula: str
) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call(
        "set_formula", key=meta["key"], sheet=sheet, range=range_, formula=formula
    )


async def add_sheet(
    session_id: str, name: str, rows: int = 200, columns: int = 26
) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call("add_sheet", key=meta["key"], name=name, rows=rows, columns=columns)


async def rename_sheet(session_id: str, sheet: str, name: str) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call("rename_sheet", key=meta["key"], sheet=sheet, name=name)


async def read_range(
    session_id: str, sheet: str | None, range_: str | None
) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call("read_range", key=meta["key"], sheet=sheet, range=range_)


async def set_layout(
    session_id: str,
    sheet: str | None,
    column_widths: dict[str, int] | None = None,
    frozen_rows: int | None = None,
    row_heights: dict[str, int] | None = None,
) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call(
        "set_layout",
        key=meta["key"],
        sheet=sheet,
        columnWidths=column_widths,
        frozenRows=frozen_rows,
        rowHeights=row_heights,
    )


async def describe(session_id: str) -> dict[str, Any]:
    meta = _require_session(session_id)
    return await _call("describe", key=meta["key"])


async def build(session_id: str) -> dict[str, Any]:
    """产出快照：写到会话的下一个版本目录，返回产物描述。"""
    meta = _require_session(session_id)
    result = await _call("build", key=meta["key"])
    snapshot: dict[str, Any] = result["snapshot"]
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))

    directory = next_version_dir(SHEETS_DIR, meta["user_id"], session_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "workbook.json").write_text(serialized, encoding="utf-8")

    sheets = snapshot.get("sheets", {})
    order = snapshot.get("sheetOrder", [])
    return {
        "workbook_id": meta["workbook_id"],
        "title": result.get("title") or meta["title"],
        "directory": directory.name,
        "snapshot": serialized,
        "sheet_names": [
            sheets[s].get("name", s) for s in order if s in sheets
        ],
        "sheet_count": len(order),
    }


# ── 磁盘快照读取（供产物重建用）──────────────────────────────────────────


def list_sheet_dirs(user_id: int, session_id: str) -> list[Path]:
    """列出某会话的全部表格版本目录，按版本号升序。"""
    if not SHEETS_DIR.exists():
        return []
    prefix = f"u{user_id}_s{session_id}_v"
    found: list[tuple[int, Path]] = []
    for child in SHEETS_DIR.iterdir():
        if not child.is_dir() or not child.name.startswith(prefix):
            continue
        try:
            version = int(child.name[len(prefix):])
        except ValueError:
            continue
        found.append((version, child))
    return [directory for _, directory in sorted(found)]


def latest_sheet_dir(user_id: int, session_id: str) -> Path | None:
    directories = list_sheet_dirs(user_id, session_id)
    return directories[-1] if directories else None


def read_snapshot(directory: Path) -> dict[str, Any] | None:
    path = directory / "workbook.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取表格快照失败 %s: %s", path, exc)
        return None


def write_snapshot(directory: Path, snapshot: dict[str, Any]) -> None:
    """把编辑器回传的快照原子写回磁盘。

    先写临时文件再 rename：保存过程中进程被杀也不会留下半个 JSON，
    否则下次打开就是「该表格产物已损坏」。
    """
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    target = directory / "workbook.json"
    temp = directory / "workbook.json.tmp"
    temp.write_text(serialized, encoding="utf-8")
    temp.replace(target)
