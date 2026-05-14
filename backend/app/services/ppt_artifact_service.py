from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json
from app.services.ppt.base_template import PPT_PAGE_CLASS, _h
from app.services.ppt.registry import ALLOWED_TYPES, get_or_default, list_names

# Trigger template registration via side-effect import
import app.services.ppt.templates  # noqa: F401

# ---- CSS cache ----

_tailwind_css: str | None = None


def _get_tailwind_css() -> str:
    global _tailwind_css
    if _tailwind_css is None:
        css_path = Path(__file__).resolve().parent / "ppt" / ".." / "ppt_tailwind_compiled.css"
        # normalize: go from ppt/ back to parent
        css_path = (Path(__file__).resolve().parent.parent) / "ppt_tailwind_compiled.css"
        try:
            _tailwind_css = css_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            _tailwind_css = ""
    return _tailwind_css


# ---- data helpers ----

def _as_string(value: Any, fallback: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else fallback


def _as_string_array(value: Any, limit: int = 7) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_string(item) for item in value if _as_string(item)][:limit]


def _normalize_slide(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        value = {}
    raw_type = _as_string(value.get("type"), "cover" if index == 0 else "bullets")
    slide_type = raw_type if raw_type in ALLOWED_TYPES else "bullets"
    chart = value.get("chart") if isinstance(value.get("chart"), dict) else None
    normalized: dict[str, Any] = {
        "type": slide_type,
        "eyebrow": _as_string(value.get("eyebrow")),
        "title": _as_string(value.get("title"), f"第 {index + 1} 页"),
        "subtitle": _as_string(value.get("subtitle")),
        "body": _as_string(value.get("body")),
        "items": _as_string_array(value.get("items")),
        "leftTitle": _as_string(value.get("leftTitle")),
        "rightTitle": _as_string(value.get("rightTitle")),
        "leftItems": _as_string_array(value.get("leftItems")),
        "rightItems": _as_string_array(value.get("rightItems")),
        "imageUrl": _as_string(value.get("imageUrl")),
        "quote": _as_string(value.get("quote")),
        "author": _as_string(value.get("author")),
        "stats": [],
        "timeline": [],
    }
    if chart and isinstance(chart.get("labels"), list) and isinstance(chart.get("values"), list):
        values: list[float] = []
        for item in chart.get("values", [])[:6]:
            try:
                values.append(float(item))
            except (TypeError, ValueError):
                continue
        normalized["chart"] = {
            "type": chart.get("type") if chart.get("type") in {"bar", "line", "donut"} else "bar",
            "labels": _as_string_array(chart.get("labels"), limit=6),
            "values": values,
            "unit": _as_string(chart.get("unit")),
        }
    if isinstance(value.get("stats"), list):
        normalized["stats"] = [
            {
                "label": _as_string(item.get("label")) if isinstance(item, dict) else "",
                "value": _as_string(item.get("value")) if isinstance(item, dict) else "",
                "caption": _as_string(item.get("caption")) if isinstance(item, dict) else "",
            }
            for item in value["stats"][:4]
        ]
        normalized["stats"] = [item for item in normalized["stats"] if item["label"] or item["value"]]
    if isinstance(value.get("timeline"), list):
        normalized["timeline"] = [
            {
                "label": _as_string(item.get("label")) if isinstance(item, dict) else "",
                "title": _as_string(item.get("title")) if isinstance(item, dict) else "",
                "body": _as_string(item.get("body")) if isinstance(item, dict) else "",
            }
            for item in value["timeline"][:5]
        ]
        normalized["timeline"] = [item for item in normalized["timeline"] if item["label"] or item["title"]]
    return normalized


# ---- parse / extract ----


def parse_ppt_deck(code: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(code)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("slides"), list):
        return None
    slides = [_normalize_slide(slide, index) for index, slide in enumerate(payload["slides"][:16])]
    if not slides:
        return None
    theme = payload.get("theme", "executive")
    # Validate against registered templates; fall back to "executive"
    registered = list_names()
    if theme not in registered:
        theme = "executive"
    return {
        "title": _as_string(payload.get("title"), slides[0]["title"] or "AgenticOS 演示文稿"),
        "subtitle": _as_string(payload.get("subtitle")),
        "author": _as_string(payload.get("author")),
        "theme": theme,
        "slides": slides,
    }


def extract_ppt_deck_from_text(text: str) -> tuple[str, dict[str, Any]] | None:
    # Find ```pptdeck or ```json block using simple string search, not fragile regex
    for marker in ("```pptdeck", "```json"):
        start = text.find(marker)
        if start < 0:
            continue
        # Skip past the marker and any trailing whitespace/newlines
        content_start = start + len(marker)
        while content_start < len(text) and text[content_start] in (" ", "\t", "\r", "\n"):
            content_start += 1
        # Find closing ```
        end = text.find("\n```", content_start)
        if end < 0:
            end = text.find("```", content_start)
        if end < 0:
            continue
        code = text[content_start:end].strip()
        deck = parse_ppt_deck(code)
        if deck is not None:
            return (code, deck)
    return None


def strip_ppt_deck_from_text(text: str) -> str:
    for marker in ("```pptdeck", "```json"):
        start = text.find(marker)
        if start < 0:
            continue
        # Find closing ``` (prefer \n``` for cleaner cut, but fall back to raw ```)
        end = text.find("\n```", start + len(marker))
        if end >= 0:
            text = text[:start] + text[end + 4:]  # skip \n + ```
        else:
            end = text.find("```", start + len(marker))
            if end >= 0:
                text = text[:start] + text[end + 3:]  # skip ```
            else:
                text = text[:start]  # partial block, drop everything from start
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---- HTML rendering ----


def render_ppt_html(deck: dict[str, Any]) -> str:
    template = get_or_default(deck.get("theme", "executive"))
    total = len(deck["slides"])
    slides_html = "".join(
        template.render_slide(slide, deck, index) for index, slide in enumerate(deck["slides"])
    )
    tailwind_css = _get_tailwind_css()
    return (
        f"<style>{tailwind_css}"
        f".ppt-preview-card>.{PPT_PAGE_CLASS}{{transform:scale(.72);transform-origin:top left}}"
        f"body{{margin:0;padding:32px 0;background:#f5f6f8;}}"
        f"</style>"
        f"<div class=\"ppt-preview-container\" style=\"font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif\">{slides_html}</div>"
    )


# ---- service ----


class PptArtifactService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    async def create_from_text(self, session_id: str, text: str) -> dict[str, Any] | None:
        extracted = extract_ppt_deck_from_text(text)
        if extracted is None:
            return None
        code, deck = extracted
        artifact_id = uuid.uuid4().hex
        preview_html = render_ppt_html(deck)
        with self.session_factory() as db:
            db.add(
                PptArtifactModel(
                    artifact_id=artifact_id,
                    session_id=session_id,
                    title=deck["title"],
                    slide_count=len(deck["slides"]),
                    deck_json=dump_json(deck),
                    preview_html=preview_html,
                    metadata_json=dump_json({"source": "pptdeck", "raw_chars": len(code)}),
                )
            )
            db.commit()
        return {
            "artifact_id": artifact_id,
            "session_id": session_id,
            "title": deck["title"],
            "slide_count": len(deck["slides"]),
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
