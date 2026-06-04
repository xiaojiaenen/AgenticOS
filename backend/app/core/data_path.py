"""会话/用户维度的数据目录管理，基于 contextvars 实现请求级别的路径隔离。"""

from __future__ import annotations

import contextvars
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
PPT_OUTPUT_DIR = DATA_DIR / "ppt-output"
PPT_SESSIONS_DIR = DATA_DIR / "ppt-sessions"
WEBSITES_DIR = DATA_DIR / "websites"
WEBSITE_TEMPLATES_DIR = DATA_DIR / "website-templates"
DESIGN_THEMES_DIR = DATA_DIR / "design-themes"
NGINX_SERVE_DIR = DATA_DIR / "nginx-serve"

_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="")
_current_user_id: contextvars.ContextVar[int] = contextvars.ContextVar("user_id", default=0)
_current_website_dir: contextvars.ContextVar[str] = contextvars.ContextVar("website_dir", default="")

_website_dir_cache: dict[str, str] = {}

_VERSION_RE = re.compile(r"^u(\d+)_s(.+)_v(\d+)$")


def set_current_session_id(session_id: str) -> None:
    _current_session_id.set(session_id)


def get_current_session_id() -> str:
    return _current_session_id.get("")


def set_current_user_id(user_id: int) -> None:
    _current_user_id.set(user_id)


def get_current_user_id() -> int:
    return _current_user_id.get(0)


def set_current_website_dir(dir_path: str) -> None:
    _current_website_dir.set(dir_path)
    sid = _current_session_id.get("")
    if sid:
        _website_dir_cache[sid] = dir_path


def get_current_website_dir() -> str:
    return _current_website_dir.get("")


def restore_website_dir_for_session(session_id: str) -> None:
    cached = _website_dir_cache.get(session_id, "")
    _current_website_dir.set(cached)
    _current_session_id.set(session_id)


def format_dir_name(user_id: int, session_id: str, version: int) -> str:
    return f"u{user_id}_s{session_id}_v{version}"


def _parse_dir_name(dir_name: str) -> tuple[int, str, int]:
    m = _VERSION_RE.match(dir_name)
    if not m:
        raise ValueError(f"Invalid dir name: {dir_name}")
    return int(m.group(1)), m.group(2), int(m.group(3))


def next_version_dir(base_dir: Path, user_id: int, session_id: str) -> Path:
    max_ver = -1
    if base_dir.exists():
        for child in base_dir.iterdir():
            if child.is_dir():
                try:
                    uid, sid, ver = _parse_dir_name(child.name)
                    if uid == user_id and sid == session_id:
                        max_ver = max(max_ver, ver)
                except ValueError:
                    continue
    new_ver = max_ver + 1
    return base_dir / format_dir_name(user_id, session_id, new_ver)
