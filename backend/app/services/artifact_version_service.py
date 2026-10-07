"""产物版本管理。

背景
----
- **PPT**：每轮生成/迭代都会写入一条新的 ``ppt_artifacts`` 记录，因此该表
  天然就是版本历史，直接查询即可（无需额外存储）。
- **网站**：项目目录是原地迭代的（``build_website`` 在同一目录改源码再构建），
  没有天然版本记录。这里在每轮产物生成完成时，把自包含的预览 HTML 快照成
  一个轻量文件（``data/website-versions/u{sid}_v{n}.html``），让用户可以回看
  之前每一轮的网站效果。

两个来源在 :func:`list_session_versions` 里合并成统一的版本列表（按时间倒序）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.data_path import DATA_DIR
from app.core.timezone import isoformat_app_timezone

logger = logging.getLogger("agent.versions")

WEBSITE_VERSIONS_DIR = DATA_DIR / "website-versions"

# u{session_id}_v{n}.html
_VERSION_FILE_RE = re.compile(r"^u(?P<session>.+)_v(?P<version>\d+)\.html$")


def _ensure_dir() -> Path:
    WEBSITE_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return WEBSITE_VERSIONS_DIR


def _session_files(session_id: str) -> list[tuple[int, Path]]:
    """返回该会话的 (版本号, 文件路径) 列表，按版本号倒序。"""
    if not WEBSITE_VERSIONS_DIR.exists():
        return []
    found: list[tuple[int, Path]] = []
    for child in WEBSITE_VERSIONS_DIR.iterdir():
        m = _VERSION_FILE_RE.match(child.name)
        if m and m.group("session") == session_id:
            found.append((int(m.group("version")), child))
    return sorted(found, key=lambda item: item[0], reverse=True)


def next_website_version(session_id: str) -> int:
    versions = _session_files(session_id)
    return (versions[0][0] + 1) if versions else 1


async def snapshot_website_version(session_id: str, preview_html: str, title: str = "") -> int | None:
    """把一轮的网站预览 HTML 快照为新版本，返回版本号。

    快照失败不影响主流程（只影响"回看历史版本"），因此内部吞掉异常只记日志。
    """
    if not preview_html or not session_id:
        return None

    def _write() -> int | None:
        try:
            version = next_website_version(session_id)
            path = _ensure_dir() / f"u{session_id}_v{version}.html"
            path.write_text(preview_html, encoding="utf-8")
            # 轻量元数据：标题 + 大小，供前端列表直接展示
            path.with_suffix(".json").write_text(
                json.dumps({"title": title, "bytes": len(preview_html)}, ensure_ascii=False),
                encoding="utf-8",
            )
            return version
        except OSError as exc:
            logger.warning("website version snapshot failed: session=%s error=%s", session_id, exc)
            return None

    return await asyncio.to_thread(_write)


def list_website_versions(session_id: str) -> list[dict[str, Any]]:
    """列出该会话的网站版本（版本号倒序 = 最新在前）。"""
    result: list[dict[str, Any]] = []
    for version, path in _session_files(session_id):
        meta_path = path.with_suffix(".json")
        title = ""
        try:
            if meta_path.exists():
                title = json.loads(meta_path.read_text(encoding="utf-8")).get("title", "") or ""
        except (OSError, json.JSONDecodeError):
            pass
        try:
            mtime = isoformat_app_timezone(datetime.fromtimestamp(path.stat().st_mtime))
        except OSError:
            mtime = None
        result.append({
            "kind": "website",
            "version": version,
            "title": title,
            "created_at": mtime,
            "reference": f"v{version}",
        })
    return result


def load_website_version(session_id: str, version: int) -> str | None:
    """读取指定版本的网站预览 HTML。"""
    path = _ensure_dir() / f"u{session_id}_v{version}.html"
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


async def list_session_versions(
    session_id: str, ppt_artifacts: Any | None = None
) -> list[dict[str, Any]]:
    """合并 PPT（来自 DB）、网站与表格（来自快照文件）的版本列表，按时间倒序。

    统一字段：``kind``(ppt|website|sheet)、``reference``(ppt 为 artifact_id /
    website 与 sheet 为 v{n})、``title``、``created_at``、``slide_count``(仅 PPT)。
    """
    versions: list[dict[str, Any]] = []

    if ppt_artifacts is not None:
        try:
            rows = await ppt_artifacts.list_for_session(session_id)
            for index, row in enumerate(rows):
                versions.append({
                    "kind": "ppt",
                    "version": index + 1,
                    "reference": row.get("artifact_id"),
                    "title": row.get("title") or "PPT 演示文稿",
                    "created_at": row.get("created_at"),
                    "slide_count": row.get("slide_count") or 0,
                })
        except Exception:
            logger.exception("list ppt versions failed: session=%s", session_id)

    try:
        versions.extend(await asyncio.to_thread(list_website_versions, session_id))
    except Exception:
        logger.exception("list website versions failed: session=%s", session_id)

    try:
        versions.extend(await asyncio.to_thread(list_sheet_versions, session_id))
    except Exception:
        logger.exception("list sheet versions failed: session=%s", session_id)

    try:
        versions.extend(await asyncio.to_thread(list_document_versions, session_id))
    except Exception:
        logger.exception("list document versions failed: session=%s", session_id)

    # 混合排序：优先按时间倒序；缺时间的排在后面
    versions.sort(
        key=lambda v: (v.get("created_at") is not None, v.get("created_at") or ""),
        reverse=True,
    )
    return versions


def build_website_version_artifact(session_id: str, version: int, title: str = "") -> dict[str, Any] | None:
    """把某个网站版本包装成前端可直接使用的 website artifact 结构。"""
    html = load_website_version(session_id, version)
    if not html:
        return None
    return {
        "type": "website",
        "artifact_id": f"{session_id}_v{version}",
        "session_id": session_id,
        "title": title or f"网站 v{version}",
        "project_slug": f"u{session_id}_v{version}",
        "stack": "vanilla",
        "file_count": 0,
        "preview_html": html,
    }

# ---------------------------------------------------------------------------
# 表格版本
#
# 表格快照本身已经是 ``data/sheets/u{user}_s{session}_v{n}/workbook.json``
# ——build_sheet 每次写一个新版本目录，天然带版本号。所以这里不再复制一份
# 内容，只记一个轻量索引（版本号 → 目录名 + 标题），供版本条列举。
# ---------------------------------------------------------------------------

SHEET_VERSION_INDEX_DIR = DATA_DIR / "sheet-versions"
_SHEET_INDEX_RE = re.compile(r"^u(?P<session>.+)_v(?P<version>\d+)\.json$")


def _ensure_sheet_index_dir() -> Path:
    SHEET_VERSION_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return SHEET_VERSION_INDEX_DIR


def _sheet_index_files(session_id: str) -> list[tuple[int, Path]]:
    if not SHEET_VERSION_INDEX_DIR.exists():
        return []
    found: list[tuple[int, Path]] = []
    for child in SHEET_VERSION_INDEX_DIR.iterdir():
        m = _SHEET_INDEX_RE.match(child.name)
        if m and m.group("session") == session_id:
            found.append((int(m.group("version")), child))
    return sorted(found, key=lambda item: item[0], reverse=True)


async def snapshot_sheet_version(
    session_id: str, title: str = "", reference: str = ""
) -> int | None:
    """登记一轮表格产物，返回版本号。

    内容已经由 build_sheet 落到 data/sheets 下了，这里只写索引。
    失败不影响主流程（只影响"回看历史版本"），因此内部吞掉异常只记日志。
    """
    if not session_id or not reference:
        return None

    def _write() -> int | None:
        try:
            existing = _sheet_index_files(session_id)
            version = (existing[0][0] + 1) if existing else 1
            path = _ensure_sheet_index_dir() / f"u{session_id}_v{version}.json"
            path.write_text(
                json.dumps(
                    {"title": title or "表格", "directory": reference},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return version
        except OSError as exc:
            logger.warning("sheet version snapshot failed: session=%s error=%s", session_id, exc)
            return None

    return await asyncio.to_thread(_write)


def list_sheet_versions(session_id: str) -> list[dict[str, Any]]:
    """列出该会话的表格版本（版本号倒序 = 最新在前）。"""
    result: list[dict[str, Any]] = []
    for version, path in _sheet_index_files(session_id):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        result.append({
            "kind": "sheet",
            "version": version,
            "reference": meta.get("directory", ""),
            "title": meta.get("title") or f"表格 v{version}",
            "created_at": isoformat_app_timezone(datetime.fromtimestamp(path.stat().st_mtime)),
        })
    return result


def load_sheet_version(session_id: str, version: int) -> dict[str, Any] | None:
    """按版本号读回表格快照，包装成前端可直接使用的 spreadsheet artifact。"""
    for candidate_version, path in _sheet_index_files(session_id):
        if candidate_version != version:
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        directory = meta.get("directory")
        if not directory:
            return None
        from app.core.data_path import SHEETS_DIR
        from app.services.office.service import read_snapshot as read_sheet_snapshot

        snapshot = read_sheet_snapshot(SHEETS_DIR / directory)
        if not snapshot:
            return None
        sheets = snapshot.get("sheets", {}) or {}
        order = snapshot.get("sheetOrder", []) or []
        return {
            "type": "spreadsheet",
            "artifact_id": directory,
            "session_id": session_id,
            "title": snapshot.get("name") or meta.get("title") or "表格",
            "snapshot": snapshot,
            "sheet_names": [sheets[s].get("name", s) for s in order if s in sheets],
            "sheet_count": len(order),
            "version": version,
        }
    return None


# ---------------------------------------------------------------------------
# 文档版本
#
# 与表格同构：快照本体已在 data/documents/{版本目录}/document.json，
# 这里只记轻量索引（版本号 → 目录名 + 标题）。
# ---------------------------------------------------------------------------

DOCUMENT_VERSION_INDEX_DIR = DATA_DIR / "document-versions"
_DOCUMENT_INDEX_RE = re.compile(r"^u(?P<session>.+)_v(?P<version>\d+)\.json$")


def _ensure_document_index_dir() -> Path:
    DOCUMENT_VERSION_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    return DOCUMENT_VERSION_INDEX_DIR


def _document_index_files(session_id: str) -> list[tuple[int, Path]]:
    if not DOCUMENT_VERSION_INDEX_DIR.exists():
        return []
    found: list[tuple[int, Path]] = []
    for child in DOCUMENT_VERSION_INDEX_DIR.iterdir():
        m = _DOCUMENT_INDEX_RE.match(child.name)
        if m and m.group("session") == session_id:
            found.append((int(m.group("version")), child))
    return sorted(found, key=lambda item: item[0], reverse=True)


async def snapshot_document_version(
    session_id: str, title: str = "", reference: str = ""
) -> int | None:
    if not session_id or not reference:
        return None

    def _write() -> int | None:
        try:
            existing = _document_index_files(session_id)
            version = (existing[0][0] + 1) if existing else 1
            path = _ensure_document_index_dir() / f"u{session_id}_v{version}.json"
            path.write_text(
                json.dumps(
                    {"title": title or "文档", "directory": reference},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return version
        except OSError as exc:
            logger.warning("document version snapshot failed: session=%s error=%s", session_id, exc)
            return None

    return await asyncio.to_thread(_write)


def list_document_versions(session_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for version, path in _document_index_files(session_id):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        result.append({
            "kind": "document",
            "version": version,
            "reference": meta.get("directory", ""),
            "title": meta.get("title") or f"文档 v{version}",
            "created_at": isoformat_app_timezone(datetime.fromtimestamp(path.stat().st_mtime)),
        })
    return result


def load_document_version(session_id: str, version: int) -> dict[str, Any] | None:
    """按版本号读回文档快照，包装成前端可直接使用的 document artifact。"""
    for candidate_version, path in _document_index_files(session_id):
        if candidate_version != version:
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        directory = meta.get("directory")
        if not directory:
            return None
        from app.core.data_path import DOCUMENTS_DIR
        from app.services.office.document_service import read_snapshot

        snapshot = read_snapshot(DOCUMENTS_DIR / directory)
        if not snapshot:
            return None
        body = snapshot.get("body") or {}
        return {
            "type": "document",
            "artifact_id": directory,
            "session_id": session_id,
            "title": snapshot.get("title") or meta.get("title") or "文档",
            "snapshot": snapshot,
            # 段落符 \r 与收尾的 \n 都不是正文字数
            "char_count": len(
                (body.get("dataStream") or "").replace("\r", "").replace("\n", "")
            ),
            "version": version,
        }
    return None
