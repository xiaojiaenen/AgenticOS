"""PPT 主题 token 解析器 — 从 design-themes 目录加载主题并生成快速参考。"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.data_path import DESIGN_THEMES_DIR


def _load_themes() -> dict[str, dict]:
    """Load all theme JSON files from the design-themes directory."""
    themes: dict[str, dict] = {}
    if not DESIGN_THEMES_DIR.exists():
        return themes
    for f in DESIGN_THEMES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name", f.stem)
            themes[name] = data
        except (json.JSONDecodeError, OSError):
            continue
    return themes


def list_available_themes() -> list[str]:
    """Return sorted list of available theme names."""
    return sorted(_load_themes().keys())


def build_token_quick_ref() -> str:
    """Build a quick reference string of theme tokens for LLM context."""
    themes = _load_themes()
    if not themes:
        return "No PPT themes available."

    lines = ["Available PPT themes:"]
    for name, data in sorted(themes.items()):
        desc = data.get("description", "")
        colors = data.get("colors", {})
        color_str = ", ".join(f"{k}={v}" for k, v in list(colors.items())[:4])
        lines.append(f"- {name}: {desc} ({color_str})" if color_str else f"- {name}: {desc}")
    return "\n".join(lines)
