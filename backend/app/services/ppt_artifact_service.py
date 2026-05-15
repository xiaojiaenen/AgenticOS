from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from app.db.models import PptArtifactModel
from app.db.session import create_db_session
from app.services.session_storage import dump_json, load_json

_PPT_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
{tokens_css}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 24px 0;
  background: var(--bg, #f5f6f8);
  font-family: var(--font-body, Inter, ui-sans-serif, system-ui, -apple-system, sans-serif);
  color: var(--fg, #1a1a2e);
}}

.slides-container {{
  display: flex;
  flex-direction: column;
  gap: 32px;
  width: 100%;
  max-width: 1280px;
}}

/* ---- Slide base ---- */
.slide {{
  width: 1280px;
  height: 720px;
  margin: 0 auto;
  position: relative;
  overflow: hidden;
  background: var(--bg, #fff);
  border-radius: var(--radius-card, 12px);
  box-shadow: var(--shadow-card, 0 4px 24px rgba(0,0,0,.08));
  padding: 64px 80px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  page-break-after: always;
}}

.slide[data-slide-type="cover"],
.slide[data-slide-type="section"],
.slide[data-slide-type="quote"],
.slide[data-slide-type="closing"] {{
  background: var(--bg, #0f172a);
  color: #fff;
  text-align: center;
  align-items: center;
}}

/* ---- Typography ---- */
.slide h1 {{ font-size: 44px; font-weight: 800; line-height: 1.25; letter-spacing: -0.02em; }}
.slide h2 {{ font-size: 34px; font-weight: 700; line-height: 1.3; letter-spacing: -0.01em; }}
.slide h3 {{ font-size: 24px; font-weight: 600; line-height: 1.4; }}
.slide .eyebrow {{
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent, #3b82f6);
  margin-bottom: 12px;
  font-weight: 600;
}}
.slide .subtitle {{
  font-size: 16px;
  color: var(--muted, #64748b);
  margin-top: 8px;
}}
.slide p {{ font-size: 16px; line-height: 1.7; color: var(--muted, #64748b); }}

.slide[data-slide-type="cover"] h1,
.slide[data-slide-type="closing"] h2 {{
  font-size: 52px;
  color: #fff;
}}

/* ---- Stats grid ---- */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  margin-top: 40px;
  width: 100%;
}}
.stat-card {{
  background: var(--surface, #f8fafc);
  border-radius: var(--radius-card, 12px);
  padding: 32px 24px;
  text-align: center;
  border: 1px solid var(--border, #e2e8f0);
}}
.stat-card strong {{
  display: block;
  font-size: 40px;
  font-weight: 800;
  color: var(--accent, #3b82f6);
  line-height: 1.2;
}}
.stat-card span {{ display: block; font-size: 16px; font-weight: 600; margin-top: 8px; }}
.stat-card small {{
  display: block;
  font-size: 13px;
  color: var(--muted, #94a3b8);
  margin-top: 4px;
}}

/* ---- Point list ---- */
.point-list {{
  list-style: none;
  counter-reset: point;
  margin-top: 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}}
.point-list li {{
  counter-increment: point;
  font-size: 18px;
  line-height: 1.6;
  padding: 16px 20px;
  background: var(--surface, #f8fafc);
  border-radius: var(--radius-card, 10px);
  border-left: 4px solid var(--accent, #3b82f6);
}}
.point-list li::before {{
  content: counter(point, decimal-leading-zero);
  font-size: 13px;
  font-weight: 700;
  color: var(--accent, #3b82f6);
  margin-right: 12px;
}}

/* ---- Chart area ---- */
.chart-area {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  margin-top: 36px;
  align-items: start;
}}
.chart-visual {{
  background: var(--surface, #f8fafc);
  border-radius: var(--radius-card, 12px);
  border: 1px solid var(--border, #e2e8f0);
  min-height: 280px;
}}
.insight-card {{
  background: var(--surface, #f8fafc);
  border-radius: var(--radius-card, 12px);
  border: 1px solid var(--border, #e2e8f0);
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}}
.insight-card strong {{
  font-size: 48px;
  font-weight: 800;
  color: var(--accent, #3b82f6);
}}
.insight-card p {{ font-size: 15px; line-height: 1.7; }}

/* ---- Comparison grid ---- */
.compare-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 36px;
}}
.compare-left, .compare-right {{
  padding: 32px;
  border-radius: var(--radius-card, 12px);
  border: 1px solid var(--border, #e2e8f0);
}}
.compare-left {{ background: var(--surface, #fef2f2); }}
.compare-right {{ background: var(--surface, #f0fdf4); }}
.compare-left h3, .compare-right h3 {{ margin-bottom: 16px; }}
.compare-left ul, .compare-right ul {{
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.compare-left li, .compare-right li {{
  font-size: 15px;
  line-height: 1.6;
  padding: 8px 0;
  border-bottom: 1px solid var(--border, rgba(0,0,0,.06));
}}

/* ---- Timeline ---- */
.timeline-track {{
  display: flex;
  justify-content: space-between;
  margin-top: 48px;
  position: relative;
  gap: 8px;
}}
.timeline-track::before {{
  content: "";
  position: absolute;
  top: 28px;
  left: 5%;
  right: 5%;
  height: 2px;
  background: var(--accent, #3b82f6);
  opacity: 0.3;
}}
.timeline-node {{
  flex: 1;
  text-align: center;
  position: relative;
  z-index: 1;
}}
.timeline-node strong {{
  display: block;
  font-size: 28px;
  font-weight: 800;
  color: var(--accent, #3b82f6);
  margin-bottom: 8px;
}}
.timeline-node span {{
  display: block;
  font-size: 15px;
  font-weight: 600;
}}
.timeline-node small {{
  display: block;
  font-size: 12px;
  color: var(--muted, #94a3b8);
  margin-top: 4px;
}}

/* ---- Quote ---- */
.slide blockquote {{
  font-size: 40px;
  font-weight: 700;
  line-height: 1.4;
  border: none;
  padding: 0;
  margin: 0 0 24px 0;
  color: #fff;
}}
.slide cite {{
  font-size: 16px;
  font-style: normal;
  color: var(--muted, rgba(255,255,255,.6));
}}

/* ---- Image text ---- */
.slide[data-slide-type="imageText"] {{
  flex-direction: row;
  gap: 48px;
  padding: 64px 64px;
}}
.image-placeholder {{
  flex: 1;
  min-width: 320px;
  background: var(--surface, #f1f5f9);
  border-radius: var(--radius-card, 12px);
  border: 1px dashed var(--border, #cbd5e1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted, #94a3b8);
  font-size: 14px;
  height: 100%;
  min-height: 480px;
}}
.text-area {{
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 16px;
}}
.text-area ul {{
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}}
.text-area li {{
  font-size: 15px;
  line-height: 1.6;
  padding-left: 20px;
  position: relative;
}}
.text-area li::before {{
  content: "✓";
  position: absolute;
  left: 0;
  color: var(--accent, #22c55e);
  font-weight: 700;
}}

/* ---- Slide number ---- */
.slide-number {{
  position: absolute;
  bottom: 24px;
  right: 32px;
  font-size: 12px;
  color: var(--muted, #94a3b8);
  font-weight: 500;
}}

/* ---- Page layout ---- */
@media print {{
  body {{ background: #fff; padding: 0; }}
  .slide {{ box-shadow: none; border-radius: 0; page-break-after: always; }}
}}

@media (max-width: 1320px) {{
  .slide {{ width: 100vw; height: auto; min-height: 56.25vw; padding: 5vw 6vw; border-radius: 0; }}
  .slide h1 {{ font-size: clamp(24px, 4vw, 44px); }}
  .slide h2 {{ font-size: clamp(20px, 3vw, 34px); }}
}}
</style>
</head>
<body>
<div class="slides-container" id="ppt-slides-container">
{slides_html}
</div>
<script>
// Add slide numbers
document.querySelectorAll('.slide').forEach(function(slide, i) {{
  var num = document.createElement('div');
  num.className = 'slide-number';
  num.textContent = (i + 1) + ' / ' + document.querySelectorAll('.slide').length;
  slide.appendChild(num);
}});
</script>
</body>
</html>"""


def _read_tokens_css(design_system_name: str) -> str:
    """Read tokens.css for a design system. Returns empty string if not found."""
    css_path = (
        Path(__file__).resolve().parents[3] / "data" / "design-systems" / design_system_name / "tokens.css"
    )
    try:
        return css_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


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
    """Check that HTML contains at least 3 slide sections."""
    count = html.count('<section class="slide"')
    return count >= 3


def _detect_design_system(text: str, html: str) -> str:
    """Try to detect which design system the Agent used from the output text."""
    from app.services.design_system import get_design_system_registry

    registry = get_design_system_registry()
    combined = (text + " " + html).lower()
    for ds in registry.list_all():
        if ds.name.lower() in combined or ds.label.lower() in combined:
            return ds.name
    # Fallback: use first available
    if registry.count > 0:
        return registry.list_all()[0].name
    return "default"


def build_full_html_document(slides_html: str, design_system_name: str) -> str:
    """Inject tokens.css and wrap slides in complete HTML document."""
    tokens_css = _read_tokens_css(design_system_name)
    return _PPT_TEMPLATE.format(tokens_css=tokens_css, slides_html=slides_html)


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
        slides_html = extract_html_from_text(text)
        if slides_html is None or not validate_slides_html(slides_html):
            return None

        design_system_name = _detect_design_system(text, slides_html)
        preview_html = build_full_html_document(slides_html, design_system_name)
        artifact_id = uuid.uuid4().hex

        # Count slides for metadata
        slide_count = slides_html.count('<section class="slide"')

        # Derive title from first h1 or h2 in slides
        title_match = re.search(r'<(?:h1|h2)[^>]*>(.+?)</(?:h1|h2)>', slides_html)
        title = title_match.group(1).strip() if title_match else "演示文稿"

        with self.session_factory() as db:
            db.add(
                PptArtifactModel(
                    artifact_id=artifact_id,
                    session_id=session_id,
                    title=title,
                    slide_count=slide_count,
                    deck_json=dump_json({"design_system": design_system_name, "slides_html": slides_html}),
                    preview_html=preview_html,
                    metadata_json=dump_json({
                        "source": "html",
                        "design_system": design_system_name,
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
            "design_system": design_system_name,
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
