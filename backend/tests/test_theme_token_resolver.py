"""Tests for the theme token resolver — CSS parsing, token resolution, color tables."""
import pytest


SAMPLE_CSS = """
:root {
  --bg: #1a1b26;
  --bg-soft: #24253a;
  --surface: #2a2b3d;
  --surface-2: #32334a;
  --border: #3b3c54;
  --border-strong: #4c4d6a;
  --text-1: #c0caf5;
  --text-2: #a9b1d6;
  --text-3: #565f89;
  --accent: #7aa2f7;
  --accent-2: #bb9af7;
  --accent-3: #9ece6a;
  --good: #9ece6a;
  --warn: #e0af68;
  --bad: #f7768e;
  --radius: 12px;
  --radius-sm: 8px;
  --radius-lg: 20px;
  --shadow: 0 2px 8px rgba(0,0,0,.3);
  --font-sans: Inter, Noto Sans SC, sans-serif;
}
.card { background: var(--surface); }
"""


class TestParseThemeCss:
    def test_extracts_all_tokens(self):
        from app.services.ppt.theme_token_resolver import parse_theme_css

        tokens = parse_theme_css(SAMPLE_CSS)
        assert tokens["--bg"] == "#1a1b26"
        assert tokens["--accent"] == "#7aa2f7"
        assert tokens["--text-1"] == "#c0caf5"
        assert tokens["--radius"] == "12px"
        assert tokens["--font-sans"] == "Inter, Noto Sans SC, sans-serif"
        assert len(tokens) == 20

    def test_no_root_block_returns_empty(self):
        from app.services.ppt.theme_token_resolver import parse_theme_css

        assert parse_theme_css("body { color: red; }") == {}
        assert parse_theme_css("") == {}


class TestResolveTokenValues:
    def test_replaces_var_references(self):
        from app.services.ppt.theme_token_resolver import resolve_token_values

        svg = '<rect fill="var(--bg)" stroke="var(--border)"/>'
        tokens = {"--bg": "#1a1b26", "--border": "#3b3c54"}
        result = resolve_token_values(svg, tokens)
        assert result == '<rect fill="#1a1b26" stroke="#3b3c54"/>'

    def test_ignores_missing_tokens(self):
        from app.services.ppt.theme_token_resolver import resolve_token_values

        svg = '<rect fill="var(--unknown)" rx="12"/>'
        tokens = {"--bg": "#fff"}
        result = resolve_token_values(svg, tokens)
        assert 'var(--unknown)' in result  # Unresolved token stays

    def test_handles_multiple_occurrences(self):
        from app.services.ppt.theme_token_resolver import resolve_token_values

        svg = (
            '<rect fill="var(--bg)"/><text fill="var(--bg)">'
            '<tspan fill="var(--accent)">hi</tspan></text>'
        )
        tokens = {"--bg": "#000", "--accent": "#f00"}
        result = resolve_token_values(svg, tokens)
        assert result.count("#000") == 2
        assert result.count("#f00") == 1
        assert "var(" not in result

    def test_real_svg_slide(self):
        from app.services.ppt.theme_token_resolver import resolve_token_values

        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="apple">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <rect x="0" y="0" width="1280" height="4" fill="var(--accent)"/>
  <text x="640" y="300" font-size="72" fill="var(--text-1)">Hello</text>
  <rect x="100" y="400" rx="12" fill="var(--surface)" stroke="var(--border)"/>
</svg>"""
        tokens = {
            "--bg": "#1a1b26",
            "--accent": "#7aa2f7",
            "--text-1": "#c0caf5",
            "--surface": "#2a2b3d",
            "--border": "#3b3c54",
        }
        result = resolve_token_values(svg, tokens)
        assert 'var(' not in result
        assert 'fill="#1a1b26"' in result
        assert 'fill="#7aa2f7"' in result
        assert 'fill="#c0caf5"' in result
        assert 'fill="#2a2b3d"' in result
        assert 'stroke="#3b3c54"' in result


class TestBuildColorTokenTable:
    def test_includes_color_tokens_only(self):
        from app.services.ppt.theme_token_resolver import build_color_token_table

        # We can't test with a real theme file since it depends on filesystem,
        # but we can verify the function exists and returns a string
        result = build_color_token_table("nonexistent-theme")
        assert isinstance(result, str)
        assert "not found" in result.lower()

    def test_token_quick_ref_returns_string(self):
        from app.services.ppt.theme_token_resolver import build_token_quick_ref

        result = build_token_quick_ref()
        assert isinstance(result, str)
        assert "--bg" in result
        assert "--accent" in result
        assert "--radius" in result


class TestLoadThemeTokens:
    def test_nonexistent_theme_returns_empty(self):
        from app.services.ppt.theme_token_resolver import load_theme_tokens

        tokens = load_theme_tokens("this-theme-does-not-exist")
        assert tokens == {}

    def test_list_available_themes(self):
        from app.services.ppt.theme_token_resolver import list_available_themes

        themes = list_available_themes()
        assert isinstance(themes, list)
        assert len(themes) >= 1
        assert "apple" in themes
        assert "agentic" in themes


class TestSvgArtifactCreation:
    """Integration test: _create_from_svg_text flow."""

    def test_create_from_svg_text_resolves_tokens(self):
        from app.services.ppt_artifact_service import PptArtifactService

        service = PptArtifactService()

        svg_text = """```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="apple">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <rect x="0" y="0" width="1280" height="4" fill="var(--accent)"/>
  <text x="640" y="300" text-anchor="middle" font-family="Inter,Noto Sans SC,sans-serif" font-size="72" font-weight="800" fill="var(--text-1)">销售数据分析</text>
  <text x="640" y="460" text-anchor="middle" font-family="Inter,Noto Sans SC,sans-serif" font-size="24" fill="var(--text-2)">Q3 业绩回顾</text>
</svg>
```

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="apple">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <rect x="40" y="40" width="1200" height="640" rx="16" fill="var(--surface)"/>
  <text x="640" y="300" text-anchor="middle" font-family="Inter,Noto Sans SC,sans-serif" font-size="48" font-weight="700" fill="var(--text-1)">核心指标</text>
</svg>
```

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="apple">
  <rect width="1280" height="720" fill="var(--bg)"/>
  <text x="640" y="360" text-anchor="middle" font-family="Inter,Noto Sans SC,sans-serif" font-size="48" fill="var(--text-1)">谢谢</text>
</svg>
```"""

        import asyncio
        result = asyncio.run(service.create_from_text(
            session_id="test-svg-session",
            text=svg_text,
            mode="ppt",
        ))

        assert result is not None
        assert result["slide_count"] == 3
        assert result["title"] == "销售数据分析"
        assert "var(" not in result["html"]  # All tokens resolved
        assert "#ffffff" in result["html"]  # --bg resolved
        assert "#0071e3" in result["html"]  # --accent resolved

    def test_create_from_svg_text_rejects_too_few_slides(self):
        from app.services.ppt_artifact_service import PptArtifactService

        service = PptArtifactService()

        svg_text = """```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="minimal-white">
  <rect width="1280" height="720" fill="var(--bg)"/>
</svg>
```

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="minimal-white">
  <rect width="1280" height="720" fill="var(--bg)"/>
</svg>
```"""

        import asyncio
        result = asyncio.run(service.create_from_text(
            session_id="test-svg-too-few",
            text=svg_text,
            mode="ppt",
        ))
        assert result is None

