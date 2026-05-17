"""Tests for the SVG-to-PPTX export pipeline."""
import json
import tempfile
from pathlib import Path

import pytest

# Simple SVG slides for testing
SIMPLE_SVGS = [
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#1a1b26"/>
  <rect x="0" y="0" width="1280" height="4" fill="#7aa2f7"/>
  <text x="640" y="300" text-anchor="middle" font-family="Inter,sans-serif" font-size="72" font-weight="800" fill="#c0caf5">Slide 1</text>
</svg>""",
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#ffffff"/>
  <text x="640" y="300" text-anchor="middle" font-family="Inter,sans-serif" font-size="54" font-weight="700" fill="#111216">Slide 2</text>
  <rect x="540" y="380" width="200" height="48" rx="12" fill="#3b6cff"/>
  <text x="640" y="410" text-anchor="middle" font-family="Inter,sans-serif" font-size="16" fill="#ffffff">Button</text>
</svg>""",
    """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#f7f7f8"/>
  <circle cx="640" cy="340" r="120" fill="#3b6cff"/>
  <text x="640" y="520" text-anchor="middle" font-family="Inter,sans-serif" font-size="32" fill="#111216">Thank You</text>
</svg>""",
]


class TestSvgToPptxConversion:
    """Test the SVG → DrawingML conversion pipeline."""

    def test_convert_svg_to_slide_shapes(self):
        from app.services.ppt.svg_to_pptx import convert_svg_to_slide_shapes

        svg_path = Path(tempfile.mktemp(suffix=".svg"))
        svg_path.write_text(SIMPLE_SVGS[0], encoding="utf-8")
        try:
            slide_xml, media_files, rel_entries, anim_targets = (
                convert_svg_to_slide_shapes(svg_path, slide_num=1, verbose=False)
            )
            assert len(slide_xml) > 0
            assert "<p:sld" in slide_xml
            assert isinstance(media_files, dict)
            assert isinstance(anim_targets, list)
            # Should have converted at least rect, text elements
            assert len(anim_targets) >= 3
        finally:
            svg_path.unlink(missing_ok=True)

    def test_create_pptx_with_native_svg(self):
        from app.services.ppt.svg_to_pptx import create_pptx_with_native_svg

        svg_paths = []
        for i, svg in enumerate(SIMPLE_SVGS):
            p = Path(tempfile.mktemp(suffix=f"_{i}.svg"))
            p.write_text(svg, encoding="utf-8")
            svg_paths.append(p)

        output_path = Path(tempfile.mktemp(suffix=".pptx"))
        try:
            success = create_pptx_with_native_svg(
                svg_files=svg_paths,
                output_path=output_path,
                canvas_format="ppt169",
                verbose=False,
                use_native_shapes=True,
                transition=None,
                use_compat_mode=False,
                enable_notes=False,
            )
            assert success
            assert output_path.exists()
            assert output_path.stat().st_size > 10000  # Should be a substantial file

            # Verify PPTX is a valid ZIP
            import zipfile
            with zipfile.ZipFile(output_path, "r") as zf:
                names = zf.namelist()
                assert "[Content_Types].xml" in names
                assert "ppt/slides/slide1.xml" in names
                assert "ppt/slides/slide2.xml" in names
                assert "ppt/slides/slide3.xml" in names
                assert "ppt/presentation.xml" in names
        finally:
            for p in svg_paths:
                p.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)

    def test_export_native_pptx_has_real_shapes(self):
        """Verify that native PPTX contains real DrawingML shapes, not images."""
        from app.services.ppt.svg_to_pptx import create_pptx_with_native_svg

        svg_paths = []
        for i, svg in enumerate(SIMPLE_SVGS):
            p = Path(tempfile.mktemp(suffix=f"_{i}.svg"))
            p.write_text(svg, encoding="utf-8")
            svg_paths.append(p)

        output_path = Path(tempfile.mktemp(suffix=".pptx"))
        try:
            create_pptx_with_native_svg(
                svg_files=svg_paths,
                output_path=output_path,
                canvas_format="ppt169",
                verbose=False,
                use_native_shapes=True,
                transition=None,
                use_compat_mode=False,
                enable_notes=False,
            )

            import zipfile
            with zipfile.ZipFile(output_path, "r") as zf:
                # Read first slide
                slide_xml = zf.read("ppt/slides/slide1.xml").decode("utf-8")
                # Should contain DrawingML shape elements (rect → <a:rect>)
                assert "<p:sp>" in slide_xml  # Shape element
                assert "<a:prstGeom" in slide_xml  # Preset geometry
                assert "<a:rPr" in slide_xml or "<a:endParaRPr" in slide_xml  # Text run properties
        finally:
            for p in svg_paths:
                p.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


class TestPptArtifactServiceSvg:
    """Test the artifact service SVG extraction."""

    def test_extract_svgs_from_new_format(self):
        from app.services.ppt_artifact_service import PptArtifactService

        svgs = SIMPLE_SVGS
        artifact = {
            "artifact_id": "test123",
            "deck_json": json.dumps({"theme": "tokyo-night", "svgs": svgs}),
            "preview_html": "",
            "source_html": "",
            "metadata": {},
        }
        extracted = PptArtifactService.extract_svgs_from_artifact(artifact)
        assert len(extracted) == 3
        assert extracted == svgs

    def test_extract_svgs_from_legacy_html_fallback(self):
        from app.services.ppt_artifact_service import PptArtifactService

        html_with_svgs = """<div class="deck">
<section class="slide"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#fff"/></svg></section>
<section class="slide"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"><rect width="1280" height="720" fill="#000"/></svg></section>
</div>"""
        artifact = {
            "artifact_id": "test_legacy",
            "deck_json": json.dumps({"theme": "minimal-white", "slides_html": html_with_svgs}),
            "preview_html": "",
            "source_html": "",
            "metadata": {},
        }
        extracted = PptArtifactService.extract_svgs_from_artifact(artifact)
        assert len(extracted) == 2

    def test_extract_svgs_empty_artifact(self):
        from app.services.ppt_artifact_service import PptArtifactService

        artifact = {"artifact_id": "empty", "deck_json": "{}", "preview_html": ""}
        extracted = PptArtifactService.extract_svgs_from_artifact(artifact)
        assert extracted == []


class TestSvgExtractionFromText:
    """Test SVG extraction from LLM output text."""

    def test_extract_svgs_from_text_multiple_blocks(self):
        from app.services.ppt_artifact_service import extract_svgs_from_text

        text = """Here is your presentation:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#1a1b26"/>
  <text x="640" y="300" text-anchor="middle" font-size="48" fill="#fff">Slide 1</text>
</svg>
```

Some commentary...

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#ffffff"/>
  <text x="640" y="300" text-anchor="middle" font-size="48" fill="#111">Slide 2</text>
</svg>
```

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#f7f7f8"/>
  <text x="640" y="300" text-anchor="middle" font-size="48" fill="#111">Slide 3</text>
</svg>
```

End."""
        svgs = extract_svgs_from_text(text)
        assert len(svgs) == 3
        assert all(svg.startswith("<svg") for svg in svgs)
        assert 'Slide 1' in svgs[0]
        assert 'Slide 3' in svgs[2]

    def test_extract_svgs_from_text_no_svg_blocks(self):
        from app.services.ppt_artifact_service import extract_svgs_from_text

        assert extract_svgs_from_text("No SVG here, just some text.") == []
        assert extract_svgs_from_text("") == []
        # Should NOT match html code blocks
        assert extract_svgs_from_text("```html\n<div>test</div>\n```") == []

    def test_extract_svgs_from_text_uppercase_marker(self):
        from app.services.ppt_artifact_service import extract_svgs_from_text

        text = """```SVG
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <rect width="1280" height="720" fill="#000"/>
</svg>
```"""
        svgs = extract_svgs_from_text(text)
        assert len(svgs) == 1
        assert '<rect' in svgs[0]

    def test_validate_svg_slides_valid(self):
        from app.services.ppt_artifact_service import validate_svg_slides
        assert validate_svg_slides(SIMPLE_SVGS)

    def test_validate_svg_slides_too_few(self):
        from app.services.ppt_artifact_service import validate_svg_slides
        assert not validate_svg_slides(SIMPLE_SVGS[:2])
        assert not validate_svg_slides([])

    def test_validate_svg_slides_inconsistent_viewbox(self):
        from app.services.ppt_artifact_service import validate_svg_slides

        svgs = [
            SIMPLE_SVGS[0],
            SIMPLE_SVGS[1],
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="#000"/></svg>',
        ]
        assert not validate_svg_slides(svgs)

    def test_count_svg_pages(self):
        from app.services.ppt_artifact_service import _count_svg_pages

        text = "```svg\n<svg></svg>\n```\n```svg\n<svg></svg>\n```"
        assert _count_svg_pages(text) == 2
        assert _count_svg_pages("no svg here") == 0

    def test_detect_theme_name_from_svg(self):
        from app.services.ppt_artifact_service import _detect_theme_name_from_svg

        svgs = ['<svg xmlns="http://www.w3.org/2000/svg" data-theme="tokyo-night" viewBox="0 0 1280 720">...</svg>']
        assert _detect_theme_name_from_svg(svgs) == "tokyo-night"
        assert _detect_theme_name_from_svg([]) == "apple"
        assert _detect_theme_name_from_svg(['<svg viewBox="0 0 1280 720"></svg>']) == "apple"

    def test_prepare_svg_preview(self):
        from app.services.ppt_artifact_service import prepare_svg_preview

        html = prepare_svg_preview(SIMPLE_SVGS, "tokyo-night")
        assert '<html lang="zh-CN"' in html
        assert 'data-theme="tokyo-night"' in html
        assert 'class="deck"' in html
        assert SIMPLE_SVGS[0] in html
        assert SIMPLE_SVGS[1] in html
        assert SIMPLE_SVGS[2] in html


class TestSvgConversionEdgeCases:
    """Test edge cases in the SVG → PPTX conversion."""

    def test_gradient_fill(self):
        from app.services.ppt.svg_to_pptx import convert_svg_to_slide_shapes

        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs>
    <linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ff0000"/>
      <stop offset="100%" stop-color="#0000ff"/>
    </linearGradient>
  </defs>
  <rect width="1280" height="720" fill="url(#g1)"/>
</svg>"""
        svg_path = Path(tempfile.mktemp(suffix=".svg"))
        svg_path.write_text(svg, encoding="utf-8")
        try:
            slide_xml, _, _, _ = convert_svg_to_slide_shapes(svg_path, slide_num=1, verbose=False)
            assert "<a:gradFill>" in slide_xml
        finally:
            svg_path.unlink(missing_ok=True)

    def test_slide_with_shadow(self):
        from app.services.ppt.svg_to_pptx import convert_svg_to_slide_shapes

        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
  <defs>
    <filter id="shadow">
      <feDropShadow dx="4" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.3"/>
    </filter>
  </defs>
  <rect x="100" y="100" width="400" height="300" rx="16" fill="#fff" filter="url(#shadow)"/>
</svg>"""
        svg_path = Path(tempfile.mktemp(suffix=".svg"))
        svg_path.write_text(svg, encoding="utf-8")
        try:
            slide_xml, _, _, _ = convert_svg_to_slide_shapes(svg_path, slide_num=1, verbose=False)
            assert "<a:effectLst>" in slide_xml
            assert "<a:outerShdw" in slide_xml
        finally:
            svg_path.unlink(missing_ok=True)
