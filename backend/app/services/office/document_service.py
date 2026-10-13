"""文档（Word 能力）的服务层：生命周期 + 快照落盘。

与表格的服务层同构：模型不产出内容本身，而是通过工具写入一个常驻
Univer 单元，build 时落一份 IDocumentData 快照。浏览器端编辑器读这份
快照，用户改完再存回来。

快照是 Univer 的 IDocumentData 原始 JSON，整体存整体读——body.dataStream
的段落分隔符、textLengths 的逐字符长度表都是内部约定，挑字段改必坏。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app.core.data_path import DOCUMENTS_DIR, next_version_dir
from app.services.office.runtime import OfficeRuntimeError, get_office_runtime

logger = logging.getLogger("agent.office.doc")

#: 同表格：常驻单元上限 + 空闲回收
MAX_LIVE_DOCUMENTS = 32
IDLE_TTL = 30 * 60

#: session_id → {key, user_id, dir, unit_id, title, last_used}
_sessions: dict[str, dict[str, Any]] = {}

#: 单个文档允许的最大块数。文档不是表格，块数超过这个值说明模型在灌水。
MAX_BLOCKS = 500


class DocumentServiceError(RuntimeError):
    """文档服务层的可预期错误（原样回给 LLM 修正）。"""


def _session_key(session_id: str) -> str:
    # 与表格的 key 空间区分开：同一个会话可以同时有一张表和一份文档
    return f"doc:{session_id}"


def _prune() -> None:
    now = time.monotonic()
    for sid in [s for s, m in _sessions.items() if now - m["last_used"] > IDLE_TTL]:
        _sessions.pop(sid, None)
    overflow = len(_sessions) - MAX_LIVE_DOCUMENTS
    if overflow > 0:
        oldest = sorted(_sessions.items(), key=lambda kv: kv[1]["last_used"])[:overflow]
        for sid, _meta in oldest:
            _sessions.pop(sid, None)


def forget_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def _require(session_id: str) -> dict[str, Any]:
    meta = _sessions.get(session_id)
    if meta is None:
        raise DocumentServiceError("当前会话还没有文档。请先调用 create_document 新建。")
    meta["last_used"] = time.monotonic()
    return meta


async def _call(op: str, **args: Any) -> dict[str, Any]:
    try:
        return await get_office_runtime().call(op, **args)
    except OfficeRuntimeError as exc:
        raise DocumentServiceError(str(exc)) from exc


async def create_document(
    session_id: str,
    user_id: int,
    title: str,
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    """新建（或重建）当前会话的文档。"""
    _prune()
    if not blocks:
        raise DocumentServiceError("blocks 不能为空，至少写一段正文再建文档")
    if len(blocks) > MAX_BLOCKS:
        raise DocumentServiceError(f"一次最多 {MAX_BLOCKS} 个块，收到 {len(blocks)} 个，请精简")

    directory = next_version_dir(DOCUMENTS_DIR, user_id, session_id)
    directory.mkdir(parents=True, exist_ok=True)
    unit_id = directory.name

    result = await _call(
        "create_document", key=_session_key(session_id), id=unit_id, title=title, blocks=blocks
    )
    _sessions[session_id] = {
        "key": _session_key(session_id),
        "user_id": user_id,
        "dir": directory,
        "unit_id": unit_id,
        "title": title,
        "last_used": time.monotonic(),
    }
    logger.info("文档已创建: %s (%s)", unit_id, title)
    return {**result, "title": title, "directory": directory.name}


async def read_document(session_id: str) -> dict[str, Any]:
    meta = _require(session_id)
    return await _call("read_document", key=meta["key"])


async def build_document(session_id: str) -> dict[str, Any]:
    """产出快照：写到会话的下一个版本目录。"""
    meta = _require(session_id)
    result = await _call("build_document", key=meta["key"])
    snapshot: dict[str, Any] = result["snapshot"]
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))

    directory = next_version_dir(DOCUMENTS_DIR, meta["user_id"], session_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "document.json").write_text(serialized, encoding="utf-8")

    body = snapshot.get("body") or {}
    # 段落符 \r 与收尾的 \n 都不是正文字数
    text = (body.get("dataStream") or "").replace("\r", "").replace("\n", "")
    return {
        "document_id": meta["unit_id"],
        "title": result.get("title") or meta["title"],
        "directory": directory.name,
        "snapshot": serialized,
        "char_count": len(text),
    }


# ── 磁盘快照读取（供产物重建用）──────────────────────────────────────────


def list_document_dirs(user_id: int, session_id: str) -> list[Path]:
    if not DOCUMENTS_DIR.exists():
        return []
    prefix = f"u{user_id}_s{session_id}_v"
    found: list[tuple[int, Path]] = []
    for child in DOCUMENTS_DIR.iterdir():
        if not child.is_dir() or not child.name.startswith(prefix):
            continue
        try:
            found.append((int(child.name[len(prefix):]), child))
        except ValueError:
            continue
    return [directory for _, directory in sorted(found)]


def read_snapshot(directory: Path) -> dict[str, Any] | None:
    path = directory / "document.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取文档快照失败 %s: %s", path, exc)
        return None


def write_snapshot(directory: Path, snapshot: dict[str, Any]) -> None:
    """原子写回：先写临时文件再 rename，进程被杀也不会留下半个 JSON。"""
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
    temp = directory / "document.json.tmp"
    temp.write_text(serialized, encoding="utf-8")
    temp.replace(directory / "document.json")
