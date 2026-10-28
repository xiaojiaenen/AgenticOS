"""Centralized data directory paths and versioned naming utilities.

All user-generated data (websites, PPT sessions, etc.) lives under
<PROJECT_ROOT>/data/.  Folder names follow the pattern:

    u<user_id>_s<session_id>_v<version>

so every artifact is traceable by user + session + version number.
"""

from __future__ import annotations

import contextvars
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root — 4 levels up from backend/app/core/data_path.py
# ---------------------------------------------------------------------------
# main.py chdirs to the repo root at startup, but tests/CLI may run from
# backend/ — then both CWD and the file-based root point at backend/,
# which has no data/design-themes. Prefer a root that actually contains
# data/design-themes so theme assets resolve correctly.
_CWD = Path.cwd()
_FILE_BASED = Path(__file__).resolve().parents[3]


def _resolve_project_root() -> Path:
    candidates = (_CWD, _FILE_BASED, _FILE_BASED.parent)
    for cand in candidates:
        if (cand / "data" / "design-themes").is_dir():
            return cand
    if (_FILE_BASED / "data").is_dir():
        return _FILE_BASED
    if (_CWD / "data").is_dir():
        return _CWD
    return _FILE_BASED


PROJECT_ROOT: Path = _resolve_project_root()

# ---------------------------------------------------------------------------
# Well-known data sub-directories
# ---------------------------------------------------------------------------
# AGENT_DATA_DIR 允许把「可写运行数据」重定向到别处，供测试隔离与自定义部署使用。
# 注意：仅重定向可写目录（网站/PPT 会话/产物/临时服务目录），
# 只读资产（design-themes 等）始终从 PROJECT_ROOT 读取，否则主题资源会找不到。
_data_dir_override = os.environ.get("AGENT_DATA_DIR", "").strip()
DATA_DIR: Path = Path(_data_dir_override).resolve() if _data_dir_override else PROJECT_ROOT / "data"

WEBSITES_DIR: Path = DATA_DIR / "websites"
WEBSITE_TEMPLATES_DIR: Path = DATA_DIR / "website-templates"
# PPT_SESSIONS_DIR 已废弃：幻灯片草稿现在落在会话工作区的 slides/ 下。
# 保留常量仅为兼容旧代码/测试的导入，新代码一律用 ``slides_dir()``。
PPT_SESSIONS_DIR: Path = DATA_DIR / "ppt-sessions"
PPT_OUTPUT_DIR: Path = DATA_DIR / "ppt-output"
VIDEO_PROJECTS_DIR: Path = DATA_DIR / "video-projects"
DESIGN_THEMES_DIR: Path = DATA_DIR / "design-themes"
NGINX_SERVE_DIR: Path = DATA_DIR / "nginx-serve"
SHEETS_DIR: Path = DATA_DIR / "sheets"
DOCUMENTS_DIR: Path = DATA_DIR / "documents"

# 会话工作区根：<DATA_DIR>/workspaces/u<uid>/s<sid>/
#
# 为什么需要它：此前 general / ppt / email 模式的文件工具把 workspace 解析成
# 进程 cwd（容器里是 /app），于是 AI 的「工作目录」直接暴露了后端源码树和
# 所有用户数据 —— 任何登录用户都能 list_files 看到别人的网站目录名。
WORKSPACES_DIR: Path = DATA_DIR / "workspaces"

# 工作区内的固定子目录
WORKSPACE_UPLOADS = "uploads"   # 用户上传的文件（AI 只读引用）
WORKSPACE_OUTPUTS = "outputs"   # AI 生成的文件
WORKSPACE_SLIDES = "slides"     # PPT 草稿（原 data/ppt-sessions）

# ---------------------------------------------------------------------------
# Context vars — set by agent_service before tool execution
# ---------------------------------------------------------------------------
_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar(
    "data_path_user_id", default=0,
)
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "data_path_session_id", default="",
)


_current_website_dir: contextvars.ContextVar[str] = contextvars.ContextVar(
    "data_path_website_dir", default="",
)

# Session-level cache: maps session_id -> website_dir absolute path.
# Survives across requests within the same server process.
_website_dir_cache: dict[str, str] = {}


def set_current_user_id(user_id: int) -> None:
    _current_user_id.set(user_id)


def set_current_session_id(session_id: str) -> None:
    _current_session_id.set(session_id)


def set_current_website_dir(dir_path: str) -> None:
    """Set the current website project directory (absolute path)."""
    _current_website_dir.set(dir_path)
    # Also cache by session_id so it survives across requests
    sid = _current_session_id.get()
    if sid and dir_path:
        _website_dir_cache[sid] = dir_path


def restore_website_dir_for_session(session_id: str) -> None:
    """Restore the website dir contextvar from the session cache.

    Call this at the start of each request to re-populate the contextvar.
    """
    cached = _website_dir_cache.get(session_id, "")
    if cached:
        _current_website_dir.set(cached)


def get_current_user_id() -> int:
    return _current_user_id.get()


def get_current_session_id() -> str:
    return _current_session_id.get()


def get_current_website_dir() -> str:
    """Return the current website project directory, or empty string if not set."""
    return _current_website_dir.get()


# ---------------------------------------------------------------------------
# 会话工作区（general / ppt / email 的文件根）
# ---------------------------------------------------------------------------


def workspace_dir(user_id: int, session_id: str, *, create: bool = False) -> Path:
    """返回某个会话的工作区目录：``workspaces/u<uid>/s<sid>``。

    这是 AI 在 general / ppt / email 模式下唯一可读写的区域。**不含任何源码、
    不含其它用户/会话的数据**，与 ``WEBSITES_DIR``（部署源，跨进程共享）刻意分开。

    ``session_id`` 里可能带 ``/`` 或 ``..``（历史会话 id 由前端生成），
    这里做一次净化，避免拼出越界路径。
    """
    safe_session = _sanitize_path_segment(session_id)
    safe_user = max(int(user_id or 0), 0)
    path = WORKSPACES_DIR / f"u{safe_user}" / f"s{safe_session}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def uploads_dir(user_id: int, session_id: str, *, create: bool = False) -> Path:
    """会话的上传目录。"""
    path = workspace_dir(user_id, session_id, create=create) / WORKSPACE_UPLOADS
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def outputs_dir(user_id: int, session_id: str, *, create: bool = False) -> Path:
    """会话的产出目录（AI 生成的文件）。"""
    path = workspace_dir(user_id, session_id, create=create) / WORKSPACE_OUTPUTS
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def slides_dir(user_id: int, session_id: str, *, create: bool = False) -> Path:
    """会话的 PPT 幻灯片目录（替代原 ``ppt-sessions/u.._s.._v1``）。

    统一到工作区后，9 处各自为政的「按 session 扫目录」逻辑都可以删掉 ——
    它们用了三种不同的匹配方式（``split("_v")`` / ``_s{sid}_`` in name /
    ``endswith``），本身就是 bug 来源。
    """
    path = workspace_dir(user_id, session_id, create=create) / WORKSPACE_SLIDES
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def current_workspace_dir(*, create: bool = False) -> Path | None:
    """当前请求上下文的工作区；user/session 未设置时返回 None。"""
    session_id = _current_session_id.get()
    user_id = _current_user_id.get()
    if not session_id:
        return None
    return workspace_dir(user_id, session_id, create=create)


def current_slides_dir(*, create: bool = False) -> Path | None:
    """当前请求上下文的幻灯片目录。"""
    session_id = _current_session_id.get()
    user_id = _current_user_id.get()
    if not session_id:
        return None
    return slides_dir(user_id, session_id, create=create)


def _sanitize_path_segment(value: str) -> str:
    """把可能带路径分隔符的 id 压成单段，防越界。"""
    text = str(value or "").strip()
    if not text:
        return "_"
    # 只保留安全字符；其余替换成下划线。session id 通常形如
    # ``1793184945644-mf4al7``，含 ``-``，必须保留。
    text = re.sub(r"[^A-Za-z0-9._-]", "_", text)
    text = text.replace("..", "_")
    return text.strip("._") or "_"


# ---------------------------------------------------------------------------
# Versioned directory naming
# ---------------------------------------------------------------------------
_VERSION_RE = re.compile(
    r"^u(\d+)_s(.+)_v(\d+)$"
)


def _parse_dir_name(name: str) -> tuple[int, str, int] | None:
    """Parse a directory name into (user_id, session_id, version) or None."""
    m = _VERSION_RE.match(name)
    if m:
        return int(m.group(1)), m.group(2), int(m.group(3))
    return None


def format_dir_name(user_id: int, session_id: str, version: int) -> str:
    return f"u{user_id}_s{session_id}_v{version}"


def next_version_dir(base_dir: Path, user_id: int, session_id: str) -> Path:
    """Return the next available versioned directory path.

    Scans *base_dir* for existing entries matching the naming pattern,
    then returns a path with version = max_existing + 1 (or 1 if none exist).
    The directory is **not** created — callers should mkdir themselves.
    """
    max_ver = 0
    if base_dir.exists():
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            parsed = _parse_dir_name(child.name)
            if parsed and parsed[0] == user_id and parsed[1] == session_id:
                max_ver = max(max_ver, parsed[2])
    return base_dir / format_dir_name(user_id, session_id, max_ver + 1)
