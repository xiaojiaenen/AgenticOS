from __future__ import annotations

import re
import uuid
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.ppt.html_ppt_inliner import inline_html_ppt_assets
from app.services.session_storage import dump_json, load_json

_CLASS_ATTR_RE = re.compile(r"\bclass\s*=\s*(['\"])(?P<classes>.*?)\1", re.IGNORECASE | re.DOTALL)
_SECTION_TAG_RE = re.compile(r"<section\b[^>]*>", re.IGNORECASE | re.DOTALL)
_DECK_TAG_RE = re.compile(r"<(?:div|main|section|body)\b[^>]*>", re.IGNORECASE | re.DOTALL)


def _tag_has_class(tag: str, class_name: str) -> bool:
    match = _CLASS_ATTR_RE.search(tag)
    if match is None:
        return False
    return class_name in set(match.group("classes").split())


def _count_slide_sections(html: str) -> int:
    return sum(1 for match in _SECTION_TAG_RE.finditer(html) if _tag_has_class(match.group(0), "slide"))


def _has_deck_container(html: str) -> bool:
    return any(_tag_has_class(match.group(0), "deck") for match in _DECK_TAG_RE.finditer(html))


def extract_html_from_text(text: str) -> str | None:
    """Extract ```html code block from LLM output text (case-insensitive marker)."""
    import re as _re
    m = _re.search(r"```(?:html|HTML)\s*\n", text)
    if m is None:
        # Fallback: any ``` code block that starts with <!DOCTYPE or <html
        m2 = _re.search(r"```\s*\n(<!DOCTYPE\s+html|<html[\s>])", text)
        if m2 is None:
            return None
        start = m2.start()
        content_start = m2.end() - len(m2.group(1))
    else:
        start = m.start()
        content_start = m.end()
    end = text.find("\n```", content_start)
    if end < 0:
        end = text.find("```", content_start)
    if end < 0:
        # No closing ``` — LLM may not close the code block at end of message
        return text[content_start:].strip()
    return text[content_start:end].strip()


def validate_slides_html(html: str) -> bool:
    """Check that HTML contains a deck div with at least 3 slide sections."""
    slide_count = _count_slide_sections(html)
    has_deck = _has_deck_container(html)
    return slide_count >= 3 and has_deck


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


def prepare_svg_preview(svgs: list[str], theme_name: str = "minimal-white") -> str:
    """Wrap a list of SVG slide strings into a simple stand-alone HTML document.

    This replaces the heavy ``prepare_final_html()`` path — SVG colors are
    self-contained, so no CSS inlining is required.
    """
    slides_html = "\n".join(svgs)
    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="{theme_name}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
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
    return "minimal-white"


def _detect_theme_name(html: str) -> str:
    """Detect which html-ppt theme the Agent used from the HTML output."""
    m = re.search(r'<html[^>]*data-theme="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r"<html[^>]*data-theme='([^']+)'", html)
    if m:
        return m.group(1)
    m = re.search(r'href="[^"]*themes/([^/"]+)\.css"', html)
    if m:
        return m.group(1)
    return "minimal-white"


def _inject_chart_js_if_needed(html: str) -> str:
    """Add Chart.js when generated slide code references Chart without a loader."""
    if not re.search(r"\b(?:new\s+Chart\s*\(|Chart\s*\.)", html):
        return html
    if re.search(r"chart(?:\.umd)?(?:\.min)?\.js", html, re.IGNORECASE):
        return html

    script = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>'
    if re.search(r"</head>", html, re.IGNORECASE):
        return re.sub(r"</head>", f"{script}</head>", html, count=1, flags=re.IGNORECASE)
    return script + html


def prepare_final_html(html: str) -> str:
    """Inline all local asset references to produce a self-contained HTML document."""
    result = _inject_chart_js_if_needed(inline_html_ppt_assets(html))
    # Make slides visible without runtime.js — body.single makes all .slide
    # elements position:relative / opacity:1 (stacked vertically).
    body_m = re.search(r"<body\b([^>]*)>", result)
    if body_m is None:
        if "</head>" in result:
            result = result.replace("</head>", "</head>\n<body class=\"single\">", 1)
        else:
            result = result.replace("<html", "<html", 1) + "\n<body class=\"single\">"
        if "</body>" not in result:
            result = result.replace("</html>", "</body>\n</html>")
    elif "class=" in body_m.group(1):
        result = result[:body_m.start(1)] + body_m.group(1).replace(
            'class="', 'class="single '
        ) + result[body_m.end(1):]
    else:
        tag_end = body_m.end(1)  # position of >
        result = result[:tag_end] + ' class="single"' + result[tag_end:]
    # Override deck overflow so all slides are scrollable in the iframe
    result = result.replace(
        "</head>",
        "<style>body.single .deck{overflow:auto!important;height:auto!important}</style>\n</head>",
        1,
    )
    return result


def strip_html_block_from_text(text: str) -> str:
    """Remove the ```html code block from output text for display."""
    m = re.search(r"```(?:html|HTML)\s*\n", text)
    if m is None:
        return text
    start = m.start()
    content_start = m.end()
    end = text.find("\n```", content_start)
    if end >= 0:
        return re.sub(r"\n{3,}", "\n\n", (text[:start] + text[end + 4:])).strip()
    end = text.find("```", content_start)
    if end >= 0:
        return re.sub(r"\n{3,}", "\n\n", (text[:start] + text[end + 3:])).strip()
    # No closing ``` — remove everything from the opening marker
    return re.sub(r"\n{3,}", "\n\n", text[:start]).strip()


def _write_artifact_files(artifact_id: str, source_html: str, preview_html: str) -> None:
    """Write artifact HTML files to data/ppt-output/ for manual inspection / editing."""
    import os as _os
    # Project root is 3 levels up from this file: backend/app/services/ -> root
    project_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    output_dir = _os.path.join(project_root, "data", "ppt-output", artifact_id)
    _os.makedirs(output_dir, exist_ok=True)
    with open(_os.path.join(output_dir, "source.html"), "w", encoding="utf-8") as f:
        f.write(source_html)
    with open(_os.path.join(output_dir, "preview.html"), "w", encoding="utf-8") as f:
        f.write(preview_html)


class PptArtifactService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def create_from_text(self, session_id: str, text: str) -> dict[str, Any] | None:
        import logging
        _logger = logging.getLogger("ppt_artifact")
        html = extract_html_from_text(text)
        if html is None:
            _logger.warning(f"extract_html_from_text returned None for session={session_id}, text_len={len(text)}, has_html_tag={'```html' in text.lower()}")
            return None
        if not validate_slides_html(html):
            slide_count = _count_slide_sections(html)
            has_deck = _has_deck_container(html)
            _logger.warning(f"validate_slides_html failed: slides={slide_count}, has_deck={has_deck}, html_len={len(html)}")
            return None

        theme_name = _detect_theme_name(html)
        preview_html = prepare_final_html(html)
        artifact_id = uuid.uuid4().hex

        slide_count = _count_slide_sections(html)

        title_match = re.search(r'<(?:h1|h2)[^>]*class="[^"]*h[12][^"]*"[^>]*>(.+?)</(?:h1|h2)>', html)
        if not title_match:
            title_match = re.search(r'<(?:h1|h2)[^>]*>(.+?)</(?:h1|h2)>', html)
        title = title_match.group(1).strip() if title_match else "演示文稿"

        with self.session_factory() as db:
            db.add(
                PptArtifactModel(
                    artifact_id=artifact_id,
                    session_id=session_id,
                    title=title,
                    slide_count=slide_count,
                    deck_json=dump_json({"theme": theme_name, "slides_html": html}),
                    preview_html=preview_html,
                    metadata_json=dump_json({
                        "source": "html-ppt",
                        "theme": theme_name,
                        "raw_chars": len(text),
                    }),
                )
            )
            db.commit()

        # Write to data/ppt-output/ for easy debugging and manual editing
        _write_artifact_files(artifact_id, html, preview_html)

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
