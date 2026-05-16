from __future__ import annotations

import re
import uuid
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.ppt.html_ppt_inliner import inline_html_ppt_assets
from app.services.session_storage import dump_json, load_json


def extract_html_from_text(text: str) -> str | None:
    """Extract ```html code block from LLM output text."""
    # Find ```html marker
    start = text.find("```html")
    if start < 0:
        return None
    content_start = start + 6
    # Skip whitespace after marker
    while content_start < len(text) and text[content_start] in (" ", "\t", "\r", "\n"):
        content_start += 1
    # Find closing ```
    end = text.find("\n```", content_start)
    if end < 0:
        end = text.find("```", content_start)
    if end < 0:
        return None
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
    return inline_html_ppt_assets(html)


def strip_html_block_from_text(text: str) -> str:
    """Remove the ```html code block from output text for display."""
    start = text.find("```html")
    if start < 0:
        return text
    end = text.find("\n```", start + 6)
    if end >= 0:
        text = text[:start] + text[end + 4:]
    else:
        end = text.find("```", start + 6)
        if end >= 0:
            text = text[:start] + text[end + 3:]
        else:
            text = text[:start]
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class PptArtifactService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def create_from_text(self, session_id: str, text: str) -> dict[str, Any] | None:
        html = extract_html_from_text(text)
        if html is None or not validate_slides_html(html):
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
