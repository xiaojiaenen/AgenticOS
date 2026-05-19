from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any


def sanitize_svg_xml(svg: str) -> str:
    """Fix unescaped XML special characters (&, <) in SVG text/tspan content.

    LLMs often write literal ``<`` and ``&`` in human-readable text (e.g.
    "Delta E < 0.5" or "A & B"), which breaks XML parsing downstream.
    This function escapes those characters inside ``<text>`` and ``<tspan>``
    leaf content while leaving tags and attributes untouched.
    """

    def _escape_content(text: str) -> str:
        parts = re.split(r"(<[^>]+>)", text)
        out: list[str] = []
        for part in parts:
            if part.startswith("<"):
                out.append(part)
            else:
                part = part.replace("&", "&amp;")
                part = part.replace("<", "&lt;")
                # Undo double-escaping of already-valid entities
                part = part.replace("&amp;amp;", "&amp;")
                part = part.replace("&amp;lt;", "&lt;")
                part = part.replace("&amp;gt;", "&gt;")
                part = part.replace("&amp;quot;", "&quot;")
                part = part.replace("&amp;apos;", "&apos;")
                out.append(part)
        return "".join(out)

    def _fix_text_elem(match: re.Match) -> str:
        full = match.group(0)
        tag_m = re.match(r"<text\b[^>]*>", full)
        if not tag_m:
            return full
        tag_open = tag_m.group(0)
        rest = full[tag_m.end() :]
        end_m = re.search(r"</text>", rest)
        if not end_m:
            return full
        content = rest[: end_m.start()]
        tag_close = end_m.group(0)
        return tag_open + _escape_content(content) + tag_close

    def _fix_tspan_elem(match: re.Match) -> str:
        full = match.group(0)
        tag_m = re.match(r"<tspan\b[^>]*>", full)
        if not tag_m:
            return full
        tag_open = tag_m.group(0)
        rest = full[tag_m.end() :]
        end_m = re.search(r"</tspan>", rest)
        if not end_m:
            return full
        content = rest[: end_m.start()]
        tag_close = end_m.group(0)
        return tag_open + _escape_content(content) + tag_close

    # Process innermost first (tspan), then text
    svg = re.sub(r"<tspan\b[^>]*>.*?</tspan>", _fix_tspan_elem, svg, flags=re.DOTALL)
    svg = re.sub(r"<text\b[^>]*>.*?</text>", _fix_text_elem, svg, flags=re.DOTALL)
    return svg

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json

def _slide_num_key(p) -> int:
    """Extract slide number from filename like 'slide_5.svg' for numeric sorting."""
    m = re.search(r'slide_(\d+)', p.name)
    return int(m.group(1)) if m else 0


_VIEWBOX_RE = re.compile(r'viewBox\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_DATA_THEME_RE = re.compile(r'data-theme\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


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
  /* Theme tokens for CSS custom property resolution */
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

    async def create_from_slides_dir(
        self, session_id: str, slides_dir: Path,
    ) -> dict[str, Any] | None:
        """Read slide SVG files from a directory, validate, and create a PPT artifact."""
        import logging
        from app.services.ppt.theme_token_resolver import load_theme_tokens, resolve_token_values

        _logger = logging.getLogger("ppt_artifact.slides_dir")

        if not slides_dir.exists():
            _logger.debug(f"slides_dir does not exist: {slides_dir}")
            return None

        svg_files = sorted(slides_dir.glob("slide_*.svg"), key=_slide_num_key)
        if len(svg_files) < 3:
            _logger.debug(f"Not enough slides: {len(svg_files)} < 3")
            return None

        svgs = []
        for f in svg_files:
            svg = f.read_text(encoding="utf-8").strip()
            if svg.startswith("<svg"):
                svgs.append(svg)
            else:
                _logger.warning(f"Slide file doesn't start with <svg>: {f}")

        # Run SVG quality check (logs only, does not block pipeline)
        try:
            from app.services.ppt.svg_quality_checker import SVGQualityChecker
            checker = SVGQualityChecker()
            for f in svg_files:
                result = checker.check_file(str(f), "ppt169")
                if result.get("errors"):
                    _logger.warning("Quality check errors in %s: %s", f.name, result["errors"])
                for w in result.get("warnings", []):
                    _logger.info("Quality check warning in %s: %s", f.name, w)
        except Exception as exc:
            _logger.warning("Quality check skipped (error initializing): %s", exc)

        if not validate_svg_slides(svgs):
            _logger.warning(f"validate_svg_slides failed: count={len(svgs)}")
            return None

        theme_name = _detect_theme_name_from_svg(svgs)
        tokens = load_theme_tokens(theme_name)
        resolved_svgs = [resolve_token_values(svg, tokens) for svg in svgs]
        resolved_svgs = [sanitize_svg_xml(svg) for svg in resolved_svgs]

        preview_html = prepare_svg_preview(resolved_svgs, theme_name)
        artifact_id = uuid.uuid4().hex
        slide_count = len(resolved_svgs)

        title_match = re.search(r'<text[^>]*font-size="(?:68|72|56|60)"[^>]*>([^<]+)</text>', resolved_svgs[0])
        if not title_match:
            title_match = re.search(r'<text[^>]*font-weight="(?:800|700|bold)"[^>]*>([^<]+)</text>', resolved_svgs[0])
        title = title_match.group(1).strip() if title_match else "演示文稿"

        def _run():
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
                            "raw_chars": sum(len(s) for s in svgs),
                        }),
                    )
                )
                db.commit()
        await asyncio.to_thread(_run)

        _write_svg_artifact_files(artifact_id, resolved_svgs, preview_html)

        return {
            "artifact_id": artifact_id,
            "session_id": session_id,
            "title": title,
            "slide_count": slide_count,
            "html": preview_html,
        }

    async def get_latest_for_session(self, session_id: str) -> dict[str, Any] | None:
        def _run():
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
        return await asyncio.to_thread(_run)

    def _row_to_dict(self, row: PptArtifactModel) -> dict[str, Any]:
        return {
            "artifact_id": row.artifact_id,
            "session_id": row.session_id,
            "title": row.title,
            "slide_count": row.slide_count,
            "html": row.preview_html,
            "deck_json": row.deck_json,
            "metadata": load_json(row.metadata_json, {}),
        }

    async def get(self, artifact_id: str) -> dict[str, Any] | None:
        def _run():
            with self.session_factory() as db:
                row = db.get(PptArtifactModel, artifact_id)
                if row is None:
                    return None
                return self._row_to_dict(row)
        return await asyncio.to_thread(_run)

    @staticmethod
    def extract_svgs_from_artifact(artifact: dict[str, Any]) -> list[str]:
        """Extract SVG page strings from an artifact's ``deck_json.svgs``."""
        deck = load_json(artifact.get("deck_json", "{}"), {})
        if isinstance(deck, dict) and "svgs" in deck:
            svgs = deck["svgs"]
            if isinstance(svgs, list) and svgs:
                return svgs
        return []
