"""Centralized data directory paths and versioned naming utilities.

All user-generated data (websites, PPT sessions, etc.) lives under
<PROJECT_ROOT>/data/.  Folder names follow the pattern:

    u<user_id>_s<session_id>_v<version>

so every artifact is traceable by user + session + version number.
"""

from __future__ import annotations

import contextvars
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root — 4 levels up from backend/app/core/data_path.py
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Well-known data sub-directories
# ---------------------------------------------------------------------------
DATA_DIR: Path = PROJECT_ROOT / "data"
WEBSITES_DIR: Path = DATA_DIR / "websites"
WEBSITE_TEMPLATES_DIR: Path = DATA_DIR / "website-templates"
PPT_SESSIONS_DIR: Path = DATA_DIR / "ppt-sessions"
PPT_OUTPUT_DIR: Path = DATA_DIR / "ppt-output"
DESIGN_THEMES_DIR: Path = DATA_DIR / "design-themes"
NGINX_SERVE_DIR: Path = DATA_DIR / "nginx-serve"

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
