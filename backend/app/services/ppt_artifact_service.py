from __future__ import annotations

import re
import uuid
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json

_SVG_TAG_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_SVG_CODE_BLOCK_RE = re.compile(r"```(?:svg|SVG)\s*\n(.*?)```", re.DOTALL)
_VIEWBOX_RE = re.compile(r'viewBox\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_DATA_THEME_RE = re.compile(r'data-theme\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def extract_svgs_from_text(text: str) -> list[str]:
    """Extract SVG page strings from `` ```svg `` fenced code blocks in LLM output.

    Each code block is expected to contain one ``<svg>`` element. Multiple blocks
    together form a complete slide deck.
    """
    svgs: list[str] = []
    for match in _SVG_CODE_BLOCK_RE.finditer(text):
        content = match.group(1).strip()
        if content.startswith("<svg"):
            svgs.append(content)
    return svgs


def validate_svg_slides(svgs: list[str]) -> bool:
    """Check that we have at least 3 SVG slides with consistent viewBox dimensions."""
    if len(svgs) < 3:
        return False
    view_boxes = set()
    for svg in svgs:
        m = _VIEWBOX_RE.search(svg)
        if m is None:
            return False
        # Normalize whitespace so "0 0 1280 720" matches "0 0 1280 720"
        vb = " ".join(m.group(1).split())
        view_boxes.add(vb)
    # All slides must share the same viewBox
    return len(view_boxes) == 1


def _count_svg_pages(text: str) -> int:
    """Count ```svg code blocks in LLM output."""
    return len(_SVG_CODE_BLOCK_RE.findall(text))


def prepare_svg_preview(svgs: list[str], theme_name: str = "apple") -> str:
    """Wrap a list of SVG slide strings into a simple stand-alone HTML document.

    Embeds the theme's CSS tokens so ``var(--xxx)`` references resolve even if
    token substitution was skipped (e.g. unknown theme name).
    """
    # Safety net: load theme tokens as CSS custom properties for browser resolution
    try:
        from app.services.ppt.theme_token_resolver import load_theme_tokens
        tokens = load_theme_tokens(theme_name)
    except Exception:
        tokens = {}
    token_css = ""
    if tokens:
        token_lines = "\n".join(f"    {k}: {v};" for k, v in sorted(tokens.items()))
        token_css = f"""
  /* Theme tokens for var() resolution */
  :root {{
{token_lines}
  }}"""

    slides_html = "\n".join(svgs)
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme_name}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>{token_css}
  body {{ margin:0; padding:0; background:#111; font-family:Inter,Noto Sans SC,sans-serif; }}
  body.single .deck {{ overflow:auto!important; height:auto!important; }}
  .deck {{ display:flex; flex-direction:column; align-items:center; gap:16px; padding:16px; }}
  .deck svg {{ width:100%; max-width:1280px; height:auto; display:block; border-radius:8px; box-shadow:0 4px 24px rgba(0,0,0,.4); }}
</style>
</head>
<body class="single">
<div class="deck">
{slides_html}
</div>
</body>
</html>"""


def _detect_theme_name_from_svg(svgs: list[str]) -> str:
    """Detect theme name from ``data-theme`` attribute on the first SVG element."""
    if svgs:
        m = _DATA_THEME_RE.search(svgs[0])
        if m:
            return m.group(1)
    return "apple"


def _write_svg_artifact_files(artifact_id: str, resolved_svgs: list[str], preview_html: str) -> None:
    """Write SVG source files and preview to data/ppt-output/ for debugging and manual editing."""
    import os as _os
    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    output_dir = _os.path.join(project_root, "data", "ppt-output", artifact_id)
    _os.makedirs(output_dir, exist_ok=True)
    for i, svg in enumerate(resolved_svgs):
        with open(_os.path.join(output_dir, f"source_slide_{i + 1}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
    with open(_os.path.join(output_dir, "preview.html"), "w", encoding="utf-8") as f:
        f.write(preview_html)


class PptArtifactService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def create_from_text(self, session_id: str, text: str, mode: str = "ppt") -> dict[str, Any] | None:
        """Create a PPT artifact from LLM output text containing SVG code blocks."""
        import logging
        from app.services.ppt.theme_token_resolver import load_theme_tokens, resolve_token_values

        _logger = logging.getLogger("ppt_artifact.svg")
        svgs = extract_svgs_from_text(text)
        if not svgs:
            _logger.warning(f"extract_svgs_from_text returned empty for session={session_id}, "
                           f"text_len={len(text)}, has_svg_block={'```svg' in text.lower()}")
            return None
        if not validate_svg_slides(svgs):
            _logger.warning(f"validate_svg_slides failed: count={len(svgs)}")
            return None

        theme_name = _detect_theme_name_from_svg(svgs)
        tokens = load_theme_tokens(theme_name)

        # Resolve var(--xxx) references to actual color values
        resolved_svgs = [resolve_token_values(svg, tokens) for svg in svgs]

        preview_html = prepare_svg_preview(resolved_svgs, theme_name)
        artifact_id = uuid.uuid4().hex

        slide_count = len(resolved_svgs)

        # Extract title from first SVG
        title_match = re.search(r'<text[^>]*font-size="(?:68|72|56|60)"[^>]*>([^<]+)</text>', resolved_svgs[0])
        if not title_match:
            title_match = re.search(r'<text[^>]*font-weight="(?:800|700|bold)"[^>]*>([^<]+)</text>', resolved_svgs[0])
        title = title_match.group(1).strip() if title_match else "演示文稿"

        with self.session_factory() as db:
            db.add(
                PptArtifactModel(
                    artifact_id=artifact_id,
                    session_id=session_id,
                    title=title,
                    slide_count=slide_count,
                    deck_json=dump_json({"theme": theme_name, "svgs": resolved_svgs}),
                    preview_html=preview_html,
                    metadata_json=dump_json({
                        "source": "svg-ppt",
                        "theme": theme_name,
                        "raw_chars": len(text),
                    }),
                )
            )
            db.commit()

        # Write SVG source files for debugging and manual editing
        _write_svg_artifact_files(artifact_id, resolved_svgs, preview_html)

        return {
            "artifact_id": artifact_id,
            "session_id": session_id,
            "title": title,
            "slide_count": slide_count,
            "html": preview_html,
        }

    async def get_latest_for_session(self, session_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            from sqlalchemy import select, desc
            row = db.scalar(
                select(PptArtifactModel)
                .where(PptArtifactModel.session_id == session_id)
                .order_by(desc(PptArtifactModel.created_at))
                .limit(1)
            )
            if row is None:
                return None
            return self._row_to_dict(row)

    def _row_to_dict(self, row: PptArtifactModel) -> dict[str, Any]:
        return {
            "artifact_id": row.artifact_id,
            "session_id": row.session_id,
            "title": row.title,
            "slide_count": row.slide_count,
            "html": row.preview_html,
            "deck_json": row.deck_json,
            "source_html": load_json(row.deck_json, {}).get("slides_html", ""),
            "metadata": load_json(row.metadata_json, {}),
        }

    async def get(self, artifact_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            row = db.get(PptArtifactModel, artifact_id)
            if row is None:
                return None
            return self._row_to_dict(row)

    @staticmethod
    def extract_svgs_from_artifact(artifact: dict[str, Any]) -> list[str]:
        """Extract SVG page strings from an artifact dict.

        Supports both the new SVG-based format (``deck_json.svgs``) and the
        legacy HTML-based format (``deck_json.slides_html``) via a best-effort
        extraction of inline ``<svg>`` elements.
        """
        import re as _re

        deck = load_json(artifact.get("deck_json", "{}"), {})
        if isinstance(deck, dict) and "svgs" in deck:
            svgs = deck["svgs"]
            if isinstance(svgs, list) and svgs:
                return svgs

        # Legacy fallback: extract <svg> elements from slides_html
        slides_html = deck.get("slides_html", "") if isinstance(deck, dict) else ""
        if not slides_html:
            slides_html = artifact.get("source_html", "")
        if slides_html:
            svg_matches = _re.findall(r"<svg\b[^>]*>.*?</svg>", slides_html, _re.DOTALL)
            if svg_matches:
                return svg_matches

        return []
