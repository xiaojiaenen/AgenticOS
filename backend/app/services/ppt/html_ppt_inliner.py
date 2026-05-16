"""Inliner for html-ppt assets.

Reads an LLM-generated HTML document that references html-ppt CSS/JS files
via <link> and <script src> tags, inlines the file contents, and returns a
single self-contained HTML string suitable for sandboxed-iframe rendering.
"""

from __future__ import annotations

import re
from pathlib import Path

_HTML_PPT_ROOT = Path(__file__).resolve().parent / "html-ppt"


def _resolve_asset_path(href: str) -> Path | None:
    """Resolve an asset path relative to the html-ppt root directory.

    Handles paths like ``assets/base.css``, ``../assets/themes/foo.css``, etc.
    Returns the resolved Path if the file exists, or None.
    """
    # Normalize: remove leading ../ sequences and common prefixes
    cleaned = href.lstrip("./")
    while cleaned.startswith("../"):
        cleaned = cleaned[3:]

    # Try common base directories
    candidates = [
        _HTML_PPT_ROOT / cleaned,
        _HTML_PPT_ROOT / "assets" / cleaned.replace("assets/", ""),
        _HTML_PPT_ROOT / "templates" / cleaned.replace("templates/", ""),
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Direct file check
    direct = _HTML_PPT_ROOT / cleaned.split("/")[-1]
    if direct.exists():
        return direct

    return None


def inline_html_ppt_assets(html: str) -> str:
    """Inline all local CSS and JS references into a self-contained HTML document.

    Local ``<link rel="stylesheet">`` tags are replaced with ``<style>`` blocks.
    Local ``<script src="...">`` tags are replaced with inline ``<script>`` blocks.
    Remote URLs (http/https) are left unchanged.
    """
    result = html

    # 1. Inline stylesheets: <link rel="stylesheet" href="path">
    def _replace_link(match: re.Match[str]) -> str:
        href = match.group("href")
        if href.startswith(("http://", "https://", "data:")):
            return match.group(0)

        resolved = _resolve_asset_path(href)
        if resolved is None:
            return match.group(0)

        content = resolved.read_text(encoding="utf-8")
        return f"<style>\n{content}\n</style>"

    result = re.sub(
        r'<link\s+[^>]*rel=["\']stylesheet["\'][^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*/?>',
        _replace_link,
        result,
        flags=re.IGNORECASE,
    )

    # Also handle <link href="..." rel="stylesheet"> (swapped attribute order)
    result = re.sub(
        r'<link\s+[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*rel=["\']stylesheet["\'][^>]*/?>',
        _replace_link,
        result,
        flags=re.IGNORECASE,
    )

    # 2. Inline scripts: <script src="path"></script>
    def _replace_script(match: re.Match[str]) -> str:
        src = match.group("src")
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)

        resolved = _resolve_asset_path(src)
        if resolved is None:
            return match.group(0)

        content = resolved.read_text(encoding="utf-8")
        return f"<script>\n{content}\n</script>"

    result = re.sub(
        r'<script\s+[^>]*src=["\'](?P<src>[^"\']+)["\'][^>]*>\s*</script>',
        _replace_script,
        result,
        flags=re.IGNORECASE,
    )

    return result
