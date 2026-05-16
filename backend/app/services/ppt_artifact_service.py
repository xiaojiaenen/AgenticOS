from __future__ import annotations

import re
import uuid
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.ppt.html_ppt_inliner import inline_html_ppt_assets
from app.services.session_storage import dump_json, load_json


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
    slide_count = html.count('<section class="slide"')
    has_deck = 'class="deck"' in html or "class='deck'" in html
    return slide_count >= 3 and has_deck


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


def prepare_final_html(html: str) -> str:
    """Inline all local asset references to produce a self-contained HTML document."""
    result = inline_html_ppt_assets(html)
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
            slide_count = html.count('<section class="slide"')
            has_deck = 'class="deck"' in html or "class='deck'" in html
            _logger.warning(f"validate_slides_html failed: slides={slide_count}, has_deck={has_deck}, html_len={len(html)}")
            return None

        theme_name = _detect_theme_name(html)
        preview_html = prepare_final_html(html)
        artifact_id = uuid.uuid4().hex

        slide_count = html.count('<section class="slide"')

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

    async def get(self, artifact_id: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            row = db.get(PptArtifactModel, artifact_id)
            if row is None:
                return None
            return {
                "artifact_id": row.artifact_id,
                "session_id": row.session_id,
                "title": row.title,
                "slide_count": row.slide_count,
                "html": row.preview_html,
                "metadata": load_json(row.metadata_json, {}),
            }
