from __future__ import annotations

import asyncio
import re
import uuid
from typing import Any


def sanitize_svg_xml(svg: str) -> str:
    """Fix unescaped XML special characters (&, <) in SVG text/tspan content,
    and strip attribute values set to the literal string ``"undefined"``.

    LLMs often write literal ``<`` and ``&`` in human-readable text (e.g.
    "Delta E < 0.5" or "A & B"), which breaks XML parsing downstream.
    This function escapes those characters inside ``<text>`` and ``<tspan>``
    leaf content while leaving tags and attributes untouched.

    Also strips attribute-value pairs where the value is ``"undefined"``
    (e.g. ``cx="undefined"`` becomes just removed), since the LLM
    occasionally emits these for computed SVG attributes.
    """
    # Strip "undefined" attribute values first
    svg = re.sub(r'\s+\w+="undefined"', "", svg)

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
    # Safety net: load theme tokens as CSS custom properties for browser resolution.
    # If the theme is invalid/missing, fall back to "apple" to prevent
    # black-on-dark rendering (CSS var() with no definition = initial `fill: black`).
    try:
        from app.services.ppt.theme_token_resolver import load_theme_tokens
        tokens = load_theme_tokens(theme_name)
        if not tokens:
            tokens = load_theme_tokens("apple")
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
    """Detect theme name from ``data-theme`` attribute on the first SVG element.

    Validates the theme exists on disk. Falls back to ``"apple"`` when the
    detected theme name is invalid or missing.
    """
    if svgs:
        m = _DATA_THEME_RE.search(svgs[0])
        if m:
            theme_name = m.group(1)
            # Validate theme CSS file exists
            from app.services.ppt.theme_token_resolver import _THEMES_DIR
            if (_THEMES_DIR / f"{theme_name}.css").is_file():
                return theme_name
    return "apple"


def _write_svg_artifact_files(artifact_id: str, resolved_svgs: list[str], preview_html: str) -> None:
    """Write SVG source files and preview to data/ppt-output/ for debugging and manual editing."""
    from app.core.data_path import PPT_OUTPUT_DIR
    output_dir = PPT_OUTPUT_DIR / artifact_id
    output_dir.mkdir(parents=True, exist_ok=True)
    for i, svg in enumerate(resolved_svgs):
        (output_dir / f"source_slide_{i + 1}.svg").write_text(svg, encoding="utf-8")
    (output_dir / "preview.html").write_text(preview_html, encoding="utf-8")


class PptArtifactService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory
        self._last_quality_errors: list[str] = []
        self._last_quality_warnings: list[str] = []

    async def create_from_slides_dir(
        self, session_id: str, slides_dir: Path,
    ) -> dict[str, Any] | None:
        """Read slide SVG files from a directory, validate, and create a PPT artifact."""
        import logging
        from app.services.ppt.theme_token_resolver import load_theme_tokens, resolve_token_values

        _logger = logging.getLogger("ppt_artifact.slides_dir")

        if not slides_dir.exists():
            _logger.debug(f"slides_dir does not exist: {slides_dir}")
            self._last_quality_errors = [f"幻灯片目录不存在: {slides_dir}"]
            self._last_quality_warnings = []
            return None

        svg_files = sorted(slides_dir.glob("slide_*.svg"), key=_slide_num_key)
        if len(svg_files) < 3:
            _logger.debug(f"Not enough slides: {len(svg_files)} < 3")
            self._last_quality_errors = [f"幻灯片不足 3 页（当前 {len(svg_files)} 页）"]
            self._last_quality_warnings = []
            return None

        svgs = []
        for f in svg_files:
            svg = f.read_text(encoding="utf-8").strip()
            if svg.startswith("<svg"):
                svgs.append(svg)
            else:
                _logger.warning(f"Slide file doesn't start with <svg>: {f}")

        # Run SVG quality check with blocking for critical errors
        _CRITICAL_KEYWORDS = [
            "forbidden element", "viewBox mismatch", "Invalid XML",
            "rgba()", "Missing viewBox",
        ]
        try:
            from app.services.ppt.svg_quality_checker import (
                SVGQualityChecker,
                check_spec_lock_consistency,
                check_layout_discipline,
            )
            checker = SVGQualityChecker()
            critical_errors: list[str] = []
            all_warnings: list[str] = []
            for f in svg_files:
                result = checker.check_file(str(f), "ppt169")
                for err in result.get("errors", []):
                    if any(kw.lower() in err.lower() for kw in _CRITICAL_KEYWORDS):
                        critical_errors.append(f"{f.name}: {err}")
                    else:
                        all_warnings.append(f"{f.name}: {err}")
                for w in result.get("warnings", []):
                    all_warnings.append(f"{f.name}: {w}")

            # New checks: spec_lock consistency + layout discipline
            for i, svg_content in enumerate(svgs):
                slide_name = f"slide_{i+1}.svg"
                spec_warnings = check_spec_lock_consistency(svg_content)
                layout_warnings = check_layout_discipline(svg_content)
                for w in spec_warnings + layout_warnings:
                    all_warnings.append(f"{slide_name}: {w}")

            # Anti-AI-Slop check — findings are warnings, never block preview
            try:
                from app.services.ppt.anti_slop_checker import check_anti_slop
                for i, svg_content in enumerate(svgs):
                    slide_name = f"slide_{i+1}.svg"
                    slop_findings = check_anti_slop(svg_content)
                    for f in slop_findings:
                        msg = f"{slide_name}: [{f.severity}] {f.code} — {f.message}"
                        # anti-slop 是设计风格检查，不阻断预览
                        all_warnings.append(msg)
            except Exception as exc:
                _logger.debug("Anti-slop check skipped: %s", exc)

            # Block on critical errors — triggers fallback chain
            if critical_errors:
                _logger.error(
                    "SVG quality gate BLOCKED %d critical errors: %s",
                    len(critical_errors), critical_errors,
                )
                self._last_quality_errors = critical_errors
                self._last_quality_warnings = all_warnings[:10]
                return None

            # Log non-critical warnings (do not block)
            for w in all_warnings:
                _logger.info("Quality check: %s", w)
        except Exception as exc:
            _logger.warning("Quality check skipped (error initializing): %s", exc)

        if not validate_svg_slides(svgs):
            _logger.warning(f"validate_svg_slides failed: count={len(svgs)}")
            # 诊断具体原因
            reasons = []
            if len(svgs) < 3:
                reasons.append(f"SVG 页数不足: {len(svgs)} < 3")
            for i, svg in enumerate(svgs):
                if not _VIEWBOX_RE.search(svg):
                    reasons.append(f"slide_{i+1}.svg 缺少 viewBox 属性")
            if not reasons:
                reasons.append("所有幻灯片的 viewBox 不一致")
            self._last_quality_errors = reasons
            self._last_quality_warnings = []
            return None

        theme_name = _detect_theme_name_from_svg(svgs)
        tokens = load_theme_tokens(theme_name)

        # 保留原始 SVG（带 var(--token) 引用），用于主题切换
        raw_svgs = svgs.copy()

        resolved_svgs = [resolve_token_values(svg, tokens) for svg in svgs]

        # Post-processing: rect-to-path conversion for PPTX compatibility
        try:
            from app.services.ppt.svg_finalize.svg_rect_to_path import process_svg as rect_to_path
            processed = []
            for svg in resolved_svgs:
                svg, _count = rect_to_path(svg)
                processed.append(svg)
            resolved_svgs = processed
        except Exception as exc:
            _logger.debug("rect-to-path post-processing skipped: %s", exc)

        resolved_svgs = [sanitize_svg_xml(svg) for svg in resolved_svgs]
        raw_svgs = [sanitize_svg_xml(svg) for svg in raw_svgs]

        preview_html = prepare_svg_preview(raw_svgs, theme_name)
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
                        deck_json=dump_json({
                            "theme": theme_name,
                            "svgs": resolved_svgs,
                            "raw_svgs": raw_svgs,  # 保留原始 SVG 用于主题切换
                        }),
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
            "theme": theme_name,
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

    async def retheme(self, artifact_id: str, new_theme: str) -> dict[str, Any] | None:
        """Switch theme for an existing artifact and regenerate preview HTML.

        Uses raw_svgs (with var(--token) references) if available, falls back to resolved svgs.
        Returns updated artifact dict or None if not found.
        """
        import logging
        from app.services.ppt.theme_token_resolver import (
            load_theme_tokens,
            resolve_token_values,
            list_available_themes,
        )

        _logger = logging.getLogger("ppt_artifact.retheme")

        # Validate theme exists
        available = list_available_themes()
        if new_theme not in available:
            _logger.warning("Theme '%s' not available. Available: %s", new_theme, available)
            return None

        def _run():
            with self.session_factory() as db:
                row = db.get(PptArtifactModel, artifact_id)
                if row is None:
                    return None

                deck = load_json(row.deck_json, {})

                # 优先使用原始 SVG（带 var(--token)），否则用已解析的
                raw_svgs = deck.get("raw_svgs", deck.get("svgs", []))
                if not raw_svgs:
                    _logger.warning("No SVGs found in artifact %s", artifact_id)
                    return None

                # 用新主题解析 token
                tokens = load_theme_tokens(new_theme)
                resolved_svgs = [resolve_token_values(svg, tokens) for svg in raw_svgs]

                # Post-processing
                try:
                    from app.services.ppt.svg_finalize.svg_rect_to_path import process_svg as rect_to_path
                    processed = []
                    for svg in resolved_svgs:
                        svg, _count = rect_to_path(svg)
                        processed.append(svg)
                    resolved_svgs = processed
                except Exception:
                    pass

                resolved_svgs = [sanitize_svg_xml(svg) for svg in resolved_svgs]

                # 生成新的预览 HTML
                preview_html = prepare_svg_preview(raw_svgs, new_theme)

                # 更新数据库
                deck["theme"] = new_theme
                deck["svgs"] = resolved_svgs
                # raw_svgs 保持不变

                row.deck_json = dump_json(deck)
                row.preview_html = preview_html

                metadata = load_json(row.metadata_json, {})
                metadata["theme"] = new_theme
                row.metadata_json = dump_json(metadata)

                db.commit()

                return {
                    "artifact_id": row.artifact_id,
                    "session_id": row.session_id,
                    "title": row.title,
                    "slide_count": row.slide_count,
                    "html": row.preview_html,
                    "theme": new_theme,
                }

        return await asyncio.to_thread(_run)
