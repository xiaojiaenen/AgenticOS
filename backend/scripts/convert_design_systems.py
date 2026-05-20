#!/usr/bin/env python3
"""
Convert open-design design systems → AgenticOS PPT theme CSS files.

Reads each design system from data/design-systems/, extracts color
palettes, maps to the 17 PPT theme tokens, and writes CSS files to
data/design-themes/.

Two paths:
  A. Systems with tokens.css → direct token-name mapping + var() resolution
  B. Systems without tokens.css → subsection-aware extraction from DESIGN.md §2
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── 28 PPT theme tokens ─────────────────────────────────────────────
PPT_TOKENS = [
    # Color tokens (17)
    "--bg", "--bg-soft", "--surface", "--surface-2",
    "--border", "--border-strong",
    "--text-1", "--text-2", "--text-3",
    "--accent", "--accent-2", "--accent-3",
    "--good", "--warn", "--bad",
    "--grad", "--grad-soft",
    # Typography tokens (4)
    "--font-sans", "--font-display", "--font-mono", "--font-serif",
    # Layout tokens (5)
    "--radius", "--radius-sm", "--radius-lg",
    "--shadow", "--shadow-lg",
]

# Mapping: design-system token name → PPT token name
DS_TO_PPT: dict[str, str] = {
    # Colors
    "--bg":            "--bg",
    "--surface":       "--bg-soft",
    "--surface-warm":  "--surface",
    "--fg":            "--text-1",
    "--fg-2":          "--text-2",
    "--muted":         "--text-3",
    "--meta":          "--text-3",
    "--border":        "--border",
    "--border-soft":   "--border-strong",
    "--accent":        "--accent",
    "--accent-hover":  "--accent-2",
    "--accent-active": "--accent-3",
    "--success":       "--good",
    "--warn":          "--warn",
    "--danger":        "--bad",
    # Typography
    "--font-sans":     "--font-sans",
    "--font-display":  "--font-display",
    "--font-mono":     "--font-mono",
    "--font-serif":    "--font-serif",
    # Layout
    "--radius":        "--radius",
    "--radius-sm":     "--radius-sm",
    "--radius-lg":     "--radius-lg",
    "--shadow":        "--shadow",
    "--shadow-lg":     "--shadow-lg",
}

FALLBACKS: dict[str, str] = {
    "--bg": "#ffffff",
    "--bg-soft": "#f0f0f3",
    "--surface": "#fafafa",
    "--surface-2": "#e8e8ec",
    "--border": "#d9d9de",
    "--border-strong": "#a0a0a8",
    "--text-1": "#1a1a1e",
    "--text-2": "#6b6b75",
    "--text-3": "#a0a0a8",
    "--accent": "#3b82f6",
    "--accent-2": "#60a5fa",
    "--accent-3": "#2563eb",
    "--good": "#16a34a",
    "--warn": "#eab308",
    "--bad": "#dc2626",
    "--grad": "linear-gradient(135deg, #3b82f6, #60a5fa)",
    "--grad-soft": "linear-gradient(135deg, rgba(59,130,246,0.08), rgba(96,165,250,0.04))",
    # Typography
    "--font-sans": "Inter, Noto Sans SC, sans-serif",
    "--font-display": "Inter, Noto Sans SC, sans-serif",
    "--font-mono": "JetBrains Mono, monospace",
    "--font-serif": "Playfair Display, Noto Serif SC, serif",
    # Layout
    "--radius": "12px",
    "--radius-sm": "8px",
    "--radius-lg": "20px",
    "--shadow": "0 2px 8px rgba(0,0,0,0.08)",
    "--shadow-lg": "0 8px 24px rgba(0,0,0,0.12)",
}

HEX6_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
ROOT_BLOCK_RE = re.compile(r":root\s*\{", re.DOTALL)
TOKEN_LINE_RE = re.compile(r"^\s*(--[\w-]+)\s*:\s*([^;]+);", re.MULTILINE)

PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
DESIGN_SYSTEMS_DIR = PROJ_ROOT / "data" / "design-systems"
OUTPUT_DIR = PROJ_ROOT / "data" / "design-themes"


# ── Color utilities ─────────────────────────────────────────────────

def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    elif len(h) == 8:
        h = h[:6]
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def perceived_lightness(hex_color: str) -> float:
    r, g, b = hex_to_rgb(hex_color)
    return 0.299 * r + 0.587 * g + 0.114 * b


def saturation(hex_color: str) -> float:
    r, g, b = [c / 255.0 for c in hex_to_rgb(hex_color)]
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == 0:
        return 0.0
    return (mx - mn) / mx


def is_hex6(v: str) -> bool:
    return bool(HEX6_RE.match(v.strip()))


def darken(hex_color: str, factor: float = 0.1) -> str:
    r, g, b = hex_to_rgb(hex_color)
    return rgb_to_hex(
        max(0, int(r * (1 - factor))),
        max(0, int(g * (1 - factor))),
        max(0, int(b * (1 - factor))),
    )


def lighten(hex_color: str, factor: float = 0.1) -> str:
    r, g, b = hex_to_rgb(hex_color)
    return rgb_to_hex(
        min(255, int(r + (255 - r) * factor)),
        min(255, int(g + (255 - g) * factor)),
        min(255, int(b + (255 - b) * factor)),
    )


# ── CSS parsing (strips comments first) ─────────────────────────────

def strip_css_comments(css: str) -> str:
    return CSS_COMMENT_RE.sub(" ", css)


def parse_css_tokens(css_text: str) -> dict[str, str]:
    """Extract ``--name: value`` pairs from the real ``:root { }`` block."""
    clean = strip_css_comments(css_text)
    m = ROOT_BLOCK_RE.search(clean)
    if not m:
        return {}
    # brace-count from the opening brace
    start = m.end()
    depth = 1
    end = start
    for i in range(start, len(clean)):
        if clean[i] == "{":
            depth += 1
        elif clean[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = clean[start:end]
    tokens: dict[str, str] = {}
    for match in TOKEN_LINE_RE.finditer(block):
        tokens[match.group(1)] = match.group(2).strip()
    return tokens


def resolve_var_references(tokens: dict[str, str]) -> dict[str, str]:
    """Resolve ``var(--other)`` values one level deep."""
    resolved = dict(tokens)
    for name, value in tokens.items():
        m = re.match(r"var\((--[\w-]+)\)", value)
        if m:
            ref = m.group(1)
            if ref in tokens and "var(" not in tokens[ref]:
                resolved[name] = tokens[ref]
    return resolved


# ── Path A: tokens.css → PPT tokens ─────────────────────────────────

def convert_from_tokens_css(tokens_css_path: Path) -> dict[str, str]:
    raw = parse_css_tokens(tokens_css_path.read_text(encoding="utf-8"))
    tokens = resolve_var_references(raw)
    result: dict[str, str] = {}

    for ds_name, ppt_name in DS_TO_PPT.items():
        val = tokens.get(ds_name, "")
        if val and is_hex6(val):
            result[ppt_name] = val.lower()

    # surface-2: darken bg-soft or surface
    if "--surface-2" not in result:
        src = result.get("--surface", result.get("--bg-soft"))
        if src:
            result["--surface-2"] = darken(src, 0.05)

    _synthesize_gradients(result)
    return result


# ── Path B: DESIGN.md §2 subsection-aware parsing ───────────────────

_SUBSECTION_RE = re.compile(r"###\s+(.+)")


def parse_section2_subsections(design_md_text: str) -> dict[str, list[tuple[str, str]]]:
    """Parse §2 into {subsection_name: [(color_name, #hex), ...]}."""
    # Try "## 2. Color..." first, then "## Color..." (some systems skip numbering)
    m = re.search(r"## 2\.\s*(?:Color|Colour).*?(?=## 3\.\s)", design_md_text, re.DOTALL)
    if not m:
        m = re.search(r"##\s*(?:Color|Colour)\s*(?:Palette|System).*?(?=##\s+(?:Typography|Brand|Components|Spacing|Layout|Motion|Type|Component))", design_md_text, re.DOTALL)
    if not m:
        return {}
    section = m.group(0)

    # Split by ### headings
    parts = _SUBSECTION_RE.split(section)
    if len(parts) > 1:
        # Has ### subsections — but colors might be in preamble too
        subs: dict[str, list[tuple[str, str]]] = {}
        # Parse preamble (parts[0]) for flat-list colors
        preamble_colors = _extract_hex_lines(parts[0])
        if preamble_colors:
            subs["_flat"] = preamble_colors
        for i in range(1, len(parts), 2):
            heading = parts[i].strip().lower()
            content = parts[i + 1] if i + 1 < len(parts) else ""
            colors = _extract_hex_lines(content)
            if colors:
                subs[heading] = colors
        return subs

    # Flat format: "- **TokenName:** `#hex` — description"
    colors = _extract_hex_lines(section)
    if colors:
        return {"_flat": colors}
    return {}


def _extract_hex_lines(text: str) -> list[tuple[str, str]]:
    """Extract (name, #hex) from list lines or table rows."""
    result: list[tuple[str, str]] = []
    for line in text.split("\n"):
        # "- **Name** (`#hex`): description" or "- **Name:** `#hex` — desc"
        m = re.match(r"\s*[-*]\s*\*\*(.+?)\*\*:?\s*\(?`?(#[0-9a-fA-F]{6})`?\)?", line)
        if m:
            result.append((m.group(1).strip().rstrip(":"), m.group(2)))
            continue
        # Table row: "| **Name** | `#hex` | ..." or "| Name | `#hex` | ..."
        m = re.match(r"\s*\|\s*\*{0,2}(.+?)\*{0,2}\s*\|\s*`?(#[0-9a-fA-F]{6})`?\s*\|", line)
        if m:
            name = m.group(1).strip()
            # Skip header rows
            if name.lower() not in ("token", "color", "hex", "name", "role", "colour"):
                result.append((name, m.group(2)))
    return result


def _classify_flat(colors: list[tuple[str, str]]) -> dict[str, str]:
    """Map flat-format tokens to PPT tokens. Falls back to heuristic if names don't match."""
    result: dict[str, str] = {}
    # Direct mappings from flat token names → PPT tokens
    flat_map = {
        "primary": "--accent",
        "secondary": "--accent-2",
        "success": "--good",
        "warning": "--warn",
        "danger": "--bad",
        "surface": "--bg",
        "text": "--text-1",
        "neutral": "--bg-soft",
    }
    for name, hex_val in colors:
        key = name.lower().rstrip(":")
        ppt = flat_map.get(key)
        if ppt:
            result[ppt] = hex_val.lower()

    if not result:
        # Flat names didn't match — fall back to heuristic classification
        return _classify_heuristic(colors)

    # Derive accent variants
    if "--accent" in result:
        if "--accent-2" not in result:
            result["--accent-2"] = lighten(result["--accent"], 0.15)
        if "--accent-3" not in result:
            result["--accent-3"] = darken(result["--accent"], 0.15)

    # Fill gaps
    _fill_neutral_gaps(result)
    _synthesize_gradients(result)
    return result


def _is_dark_theme(result: dict[str, str]) -> bool:
    """Detect whether the theme is dark by checking background lightness."""
    bg = result.get("--bg", "")
    if bg and is_hex6(bg):
        return perceived_lightness(bg) < 128
    return False


def _fill_neutral_gaps(result: dict[str, str]) -> None:
    """Derive missing neutral tokens from what we have.

    Only fills tokens that are genuinely absent. Never overwrites
    existing values. Uses dark/light-aware synthesis.
    """
    dark = _is_dark_theme(result)

    if "--bg-soft" not in result and "--bg" in result:
        bg = result["--bg"]
        if dark:
            result["--bg-soft"] = darken(bg, 0.05)
        else:
            result["--bg-soft"] = darken(bg, 0.03)
    if "--surface" not in result and "--bg" in result:
        if dark:
            result["--surface"] = lighten(result["--bg"], 0.06)
        else:
            result["--surface"] = result["--bg"]
    if "--surface-2" not in result:
        src = result.get("--surface", result.get("--bg-soft", result.get("--bg", FALLBACKS["--bg"])))
        if dark:
            result["--surface-2"] = lighten(src, 0.12)
        else:
            result["--surface-2"] = darken(src, 0.04)
    if "--border" not in result:
        if dark:
            result["--border"] = "rgba(255,255,255,.10)"
        else:
            result["--border"] = darken(result.get("--bg", FALLBACKS["--bg"]), 0.10)
    if "--border-strong" not in result:
        if dark:
            result["--border-strong"] = "rgba(255,255,255,.22)"
        else:
            result["--border-strong"] = darken(result.get("--bg", FALLBACKS["--bg"]), 0.30)
    if "--text-2" not in result and "--text-1" in result:
        if dark:
            result["--text-2"] = darken(result["--text-1"], 0.15)
        else:
            result["--text-2"] = lighten(result["--text-1"], 0.40)
    if "--text-3" not in result:
        text1 = result.get("--text-1", FALLBACKS["--text-1"])
        if dark:
            result["--text-3"] = darken(text1, 0.40)
        else:
            result["--text-3"] = lighten(text1, 0.65)


def _classify_heuristic(colors: list[tuple[str, str]]) -> dict[str, str]:
    """Assign colors to PPT roles based on saturation and lightness."""
    result: dict[str, str] = {}
    neutrals = []
    chromatics = []
    for name, hex_val in colors:
        hex_val = hex_val.lower()
        L = perceived_lightness(hex_val)
        s = saturation(hex_val)
        if s < 0.15:
            neutrals.append((name, hex_val, L))
        else:
            chromatics.append((name, hex_val, L, s))

    neutrals.sort(key=lambda x: -x[2])  # lightest first
    chromatics.sort(key=lambda x: -x[3])  # most saturated first

    if neutrals:
        # lightest → bg
        result["--bg"] = neutrals[0][1]
        if len(neutrals) > 1:
            result["--bg-soft"] = neutrals[1][1]
        if len(neutrals) > 2:
            result["--surface"] = neutrals[2][1] if neutrals[2][2] > 180 else neutrals[0][1]
        # darkest → text
        if len(neutrals) > 1:
            result["--text-1"] = neutrals[-1][1]
        if len(neutrals) > 2:
            result["--text-2"] = neutrals[-2][1]
        # mid → border
        mid_idx = len(neutrals) // 2
        if len(neutrals) > 2:
            result["--border"] = neutrals[mid_idx][1]

    if chromatics:
        result["--accent"] = chromatics[0][1]
        result["--accent-2"] = lighten(chromatics[0][1], 0.15)
        result["--accent-3"] = darken(chromatics[0][1], 0.15)

    # Find semantic colors by name
    for name, hex_val in colors:
        nl = name.lower()
        if any(kw in nl for kw in ["success", "green", "good", "positive", "correct"]):
            result["--good"] = hex_val.lower()
        elif any(kw in nl for kw in ["warn", "yellow", "amber", "caution"]):
            result["--warn"] = hex_val.lower()
        elif any(kw in nl for kw in ["error", "danger", "red", "destructive", "wrong", "bad"]):
            result["--bad"] = hex_val.lower()

    _fill_neutral_gaps(result)
    _synthesize_gradients(result)
    return result


def classify_colors_for_ppt(
    subs: dict[str, list[tuple[str, str]]],
) -> dict[str, str]:
    """Assign colors from DESIGN.md subsections to PPT token roles."""
    result: dict[str, str] = {}

    if "_flat" in subs:
        return _classify_flat(subs["_flat"])

    # Collect all colors with their source subsection
    all_colors: list[tuple[str, str, str]] = []
    for sub_name, colors in subs.items():
        for name, hex_val in colors:
            all_colors.append((name, hex_val, sub_name))

    # Classify each color as neutral or chromatic, then by lightness
    neutrals: list[tuple[str, str, str, float, float]] = []
    chromatics: list[tuple[str, str, str, float, float]] = []
    for name, hex_val, sub in all_colors:
        hex_val = hex_val.lower()
        L = perceived_lightness(hex_val)
        s = saturation(hex_val)
        if s < 0.15:  # near-gray
            neutrals.append((name, hex_val, sub, L, s))
        else:
            chromatics.append((name, hex_val, sub, L, s))

    # Sort neutrals by lightness (light first)
    neutrals.sort(key=lambda x: -x[3])  # descending lightness
    # Sort chromatics by saturation (most saturated first for accent)
    chromatics.sort(key=lambda x: -x[4])

    # ── Assign neutrals to bg / surface / text / border ─────────
    # Lightest → bg, bg-soft, surface
    # Mid → surface-2, border
    # Darker → border-strong, text-3
    # Darkest → text-1, text-2

    # Use subsection hints to steer assignment
    def _sub_match(sub: str, keywords: list[str]) -> bool:
        return any(kw in sub for kw in keywords)

    # bg candidates: light neutrals from "surface", "background", "primary" subsections
    bg_candidates = [
        n for n in neutrals
        if _sub_match(n[2], ["surface", "background", "primary", "base"])
        and n[3] > 200
    ]
    if not bg_candidates:
        bg_candidates = [n for n in neutrals if n[3] > 240]
    if bg_candidates:
        result["--bg"] = bg_candidates[0][1]
        neutrals.remove(bg_candidates[0])

    # bg-soft: next lightest, or from "surface" subsection
    soft_candidates = [
        n for n in neutrals
        if _sub_match(n[2], ["surface", "background", "secondary", "soft"])
        and n[3] > 180
    ]
    if not soft_candidates:
        soft_candidates = [n for n in neutrals if n[3] > 220]
    if soft_candidates:
        result["--bg-soft"] = soft_candidates[0][1]
        neutrals.remove(soft_candidates[0])

    # surface: another light neutral
    if neutrals and neutrals[0][3] > 220:
        result["--surface"] = neutrals[0][1]
        neutrals.pop(0)

    # surface-2: slightly darker surface
    if neutrals and neutrals[0][3] > 180:
        result["--surface-2"] = neutrals[0][1]
        neutrals.pop(0)

    # border: mid-light neutral from "border" subsection
    border_candidates = [
        n for n in neutrals
        if _sub_match(n[2], ["border", "divider", "stroke"])
        and 160 < n[3] < 240
    ]
    if not border_candidates:
        border_candidates = [n for n in neutrals if 160 < n[3] < 240]
    if border_candidates:
        result["--border"] = border_candidates[0][1]
        neutrals.remove(border_candidates[0])

    # border-strong: darker border
    bsc = [n for n in neutrals if _sub_match(n[2], ["border"]) and n[3] < 180]
    if not bsc:
        bsc = [n for n in neutrals if 100 < n[3] < 180]
    if bsc:
        result["--border-strong"] = bsc[0][1]
        neutrals.remove(bsc[0])

    # text: darkest neutrals, or from "text", "ink", "neutral" subsections
    text_candidates = [
        n for n in neutrals
        if _sub_match(n[2], ["text", "ink", "foreground", "neutral", "primary"])
        and n[3] < 80
    ]
    if not text_candidates:
        text_candidates = [n for n in neutrals if n[3] < 60]
    if len(text_candidates) >= 1:
        result["--text-1"] = text_candidates[0][1]
        neutrals.remove(text_candidates[0])
    if len(text_candidates) >= 2:
        result["--text-2"] = text_candidates[1][1]
        neutrals.remove(text_candidates[1])
    elif neutrals and neutrals[-1][3] < 120:
        result["--text-2"] = neutrals[-1][1]
        neutrals.pop()

    # text-3: mid-dark neutral
    t3 = [n for n in neutrals if _sub_match(n[2], ["text", "muted", "meta", "placeholder", "disabled"]) and n[3] < 180]
    if not t3:
        t3 = [n for n in neutrals if 100 < n[3] < 180]
    if t3:
        result["--text-3"] = t3[0][1]
        neutrals.remove(t3[0])

    # ── Assign chromatics to accent / semantic ──────────────────
    # accent: most saturated chromatic from "primary", "accent", "brand"
    accent_candidates = [
        c for c in chromatics
        if _sub_match(c[2], ["primary", "accent", "brand", "action", "cta", "link"])
    ]
    if not accent_candidates:
        accent_candidates = chromatics[:3] if chromatics else []
    if accent_candidates:
        result["--accent"] = accent_candidates[0][1]
        if accent_candidates[0] in chromatics:
            chromatics.remove(accent_candidates[0])

    # accent-2: lighter variant (hover, secondary accent)
    a2_candidates = [
        c for c in chromatics
        if _sub_match(c[2], ["hover", "secondary", "accent", "light"])
        and c[3] > 0.3
    ]
    if not a2_candidates and chromatics:
        # pick a different chromatic
        a2_candidates = chromatics[:1]
    if a2_candidates:
        result["--accent-2"] = a2_candidates[0][1]
        if a2_candidates[0] in chromatics:
            chromatics.remove(a2_candidates[0])

    # accent-3: darker variant (pressed, active)
    a3_candidates = [
        c for c in chromatics
        if _sub_match(c[2], ["pressed", "active", "deep", "dark"])
    ]
    if not a3_candidates and "--accent" in result:
        result["--accent-3"] = darken(result["--accent"], 0.15)
    elif a3_candidates:
        result["--accent-3"] = a3_candidates[0][1]
        if a3_candidates[0] in chromatics:
            chromatics.remove(a3_candidates[0])

    # good: green-tinged chromatic
    good_candidates = [
        c for c in chromatics
        if _sub_match(c[2], ["success", "green", "positive", "good", "correct", "confirmed", "merge"])
    ]
    if good_candidates:
        result["--good"] = good_candidates[0][1]
        if good_candidates[0] in chromatics:
            chromatics.remove(good_candidates[0])

    # warn: yellow/amber
    warn_candidates = [
        c for c in chromatics
        if _sub_match(c[2], ["warn", "yellow", "amber", "caution", "attention", "lemon"])
    ]
    if warn_candidates:
        result["--warn"] = warn_candidates[0][1]
        if warn_candidates[0] in chromatics:
            chromatics.remove(warn_candidates[0])

    # bad: red
    bad_candidates = [
        c for c in chromatics
        if _sub_match(c[2], ["error", "danger", "red", "destructive", "wrong", "critical", "negative", "cardinal"])
    ]
    if bad_candidates:
        result["--bad"] = bad_candidates[0][1]
        if bad_candidates[0] in chromatics:
            chromatics.remove(bad_candidates[0])

    # Synthesize accent variants if not found
    if "--accent" in result:
        if "--accent-2" not in result:
            result["--accent-2"] = lighten(result["--accent"], 0.15)
        if "--accent-3" not in result:
            result["--accent-3"] = darken(result["--accent"], 0.15)

    _synthesize_gradients(result)
    return result


def convert_from_design_md(design_md_path: Path) -> dict[str, str]:
    text = design_md_path.read_text(encoding="utf-8")
    subs = parse_section2_subsections(text)
    if not subs:
        return {}
    result = classify_colors_for_ppt(subs)
    # Also extract typography and layout tokens
    result.update(_extract_typography_tokens(text))
    result.update(_extract_layout_tokens(text))
    return result


# ── Typography extraction from DESIGN.md §3 ──────────────────────────

def _extract_typography_tokens(design_md_text: str) -> dict[str, str]:
    """Extract font stacks from DESIGN.md §3 (Typography Rules)."""
    result: dict[str, str] = {}
    # Find section 3 (or unnumbered Typography section)
    m = re.search(
        r"## 3\.\s*(?:Typography|Type|Font).*?(?=## [45]\.\s)",
        design_md_text, re.DOTALL,
    )
    if not m:
        m = re.search(
            r"##\s*(?:Typography|Type|Font).*?(?=##\s+(?:Component|Layout|Spacing|Depth|Motion|Color|Brand|Icon))",
            design_md_text, re.DOTALL,
        )
    if not m:
        return result
    section = m.group(0)

    # Extract font-family values from code spans or inline mentions
    # Pattern: `font-family: "Inter", sans-serif` or mentions like "Heading: Inter Bold"
    font_blocks = re.findall(
        r'(?:font-family|font|family)[:\s]+[\`"]?([A-Za-z][A-Za-z0-9\s,\-]+?)(?:[\`"]|$|;|\))',
        section, re.IGNORECASE,
    )
    # Pattern: **Heading**: "Inter", 700 or similar
    heading_font = re.findall(
        r'Heading.*?(?:font|family|type|face)?[:\s]+[\`"]*([A-Za-z][A-Za-z0-9\s\-]+)[\`"]*',
        section, re.IGNORECASE,
    )
    # Pattern: **Body**: followed by font name
    body_font = re.findall(
        r'Body.*?(?:font|family|type|face)?[:\s]+[\`"]*([A-Za-z][A-Za-z0-9\s\-]+)[\`"]*',
        section, re.IGNORECASE,
    )

    all_mentions = font_blocks + heading_font + body_font

    # Classify fonts into sans/serif/mono/display
    sans_candidates: list[str] = []
    serif_candidates: list[str] = []
    mono_candidates: list[str] = []

    for f in all_mentions:
        f = f.strip().rstrip(",").rstrip(";")
        if not f or len(f) < 3:
            continue
        fl = f.lower()
        if any(kw in fl for kw in ["mono", "code", "console", "terminal", "jetbrains", "fira code", "source code", "cascadia"]):
            mono_candidates.append(f)
        elif any(kw in fl for kw in ["serif", "playfair", "times", "georgia", "garamond", "merriweather", "noto serif", "lora", "spectral", "eb garamond"]):
            serif_candidates.append(f)
        elif any(kw in fl for kw in ["sans", "inter", "system-ui", "roboto", "helvetica", "arial", "noto sans", "sf pro", "segoe"]):
            sans_candidates.append(f)

    if sans_candidates:
        result["--font-sans"] = sans_candidates[0]
    if serif_candidates:
        result["--font-serif"] = serif_candidates[0]
        result["--font-display"] = serif_candidates[0]  # display defaults to serif if available
    if mono_candidates:
        result["--font-mono"] = mono_candidates[0]

    return result


# ── Layout token extraction from DESIGN.md §5/§6 ─────────────────────

def _extract_layout_tokens(design_md_text: str) -> dict[str, str]:
    """Extract radius and shadow values from DESIGN.md §5 (Layout) and §6 (Depth)."""
    result: dict[str, str] = {}
    # Try to find layout/spacing section
    layout_m = re.search(
        r"## [56]\.\s*(?:Layout|Spacing|Depth|Elevation|Shadow).*?(?=## [67]\.\s|##\s+\w)",
        design_md_text, re.DOTALL,
    )
    if not layout_m:
        layout_m = re.search(
            r"##\s*(?:Layout|Spacing|Depth|Elevation|Shadow|Component).*?(?=##\s+(?:Animation|Motion|Responsive|Do|Icon|Accessibility))",
            design_md_text, re.DOTALL,
        )
    if not layout_m:
        return result
    section = layout_m.group(0)

    # Extract border-radius values
    radius_vals = re.findall(r'(?:border-radius|radius|rounded|rounding)[:\s]+(\d+)px', section, re.IGNORECASE)
    if radius_vals:
        radii = sorted(set(int(v) for v in radius_vals))
        if len(radii) >= 3:
            result["--radius-sm"] = f"{radii[0]}px"
            result["--radius"] = f"{radii[len(radii)//2]}px"
            result["--radius-lg"] = f"{radii[-1]}px"
        elif len(radii) == 2:
            result["--radius-sm"] = f"{radii[0]}px"
            result["--radius"] = f"{radii[1]}px"
            result["--radius-lg"] = f"{int(radii[1] * 1.6)}px"
        elif radii:
            r = radii[0]
            result["--radius-sm"] = f"{max(4, int(r * 0.6))}px"
            result["--radius"] = f"{r}px"
            result["--radius-lg"] = f"{int(r * 1.6)}px"

    # Extract shadow values
    shadow_matches = re.findall(
        r'(?:shadow|elevation).*?(\d+)\s*(?:px)?.*?(\d+)\s*(?:px)?.*?(?:rgba?\([^)]+\)|#[0-9a-fA-F]+)',
        section, re.IGNORECASE,
    )
    if shadow_matches:
        # Simple extraction — use reasonable defaults based on found values
        for dy, blur in shadow_matches:
            dy_val = int(dy)
            blur_val = int(blur)
            if dy_val <= 4 and blur_val <= 12:
                result["--shadow"] = f"0 {dy}px {blur}px rgba(0,0,0,0.08)"
            else:
                result["--shadow-lg"] = f"0 {dy}px {blur}px rgba(0,0,0,0.12)"

    return result


# ── Path C: html-ppt theme CSS → PPT tokens ──────────────────────────

_HTML_PPT_THEMES_DIR = Path.home() / "code" / "open-design" / "design-templates" / "html-ppt" / "assets" / "themes"

# html-ppt token → PPT token mapping
_HTML_PPT_TO_PPT: dict[str, str] = {
    "--bg": "--bg",
    "--bg-card": "--surface",
    "--bg-alt": "--bg-soft",
    "--fg": "--text-1",
    "--fg-secondary": "--text-2",
    "--fg-muted": "--text-3",
    "--border": "--border",
    "--accent": "--accent",
    "--accent-hover": "--accent-2",
    "--accent-active": "--accent-3",
    "--success": "--good",
    "--warning": "--warn",
    "--danger": "--bad",
    "--font-sans": "--font-sans",
    "--font-display": "--font-display",
    "--font-mono": "--font-mono",
    "--font-serif": "--font-serif",
    "--radius": "--radius",
    "--radius-sm": "--radius-sm",
    "--radius-lg": "--radius-lg",
    "--shadow": "--shadow",
    "--shadow-lg": "--shadow-lg",
}


def convert_from_html_ppt_theme(theme_css_path: Path) -> dict[str, str]:
    """Convert an html-ppt theme CSS file to PPT theme tokens.

    Two-pass extraction:
    1. Map known aliases (--fg → --text-1, --success → --good, etc.)
    2. Direct pass-through: if a PPT token exists in the CSS with the same name, use it
    """
    if not theme_css_path.is_file():
        return {}
    raw = parse_css_tokens(theme_css_path.read_text(encoding="utf-8"))
    if not raw:
        return {}
    tokens = resolve_var_references(raw)
    result: dict[str, str] = {}

    # Pass 1: mapped aliases
    for html_token, ppt_token in _HTML_PPT_TO_PPT.items():
        val = tokens.get(html_token, "")
        if not val:
            continue
        val = val.strip().rstrip(";")
        if ppt_token.startswith("--font") or ppt_token.startswith("--radius") or ppt_token.startswith("--shadow"):
            result[ppt_token] = val
        elif ppt_token in ("--grad", "--grad-soft"):
            continue
        elif ppt_token in ("--surface", "--surface-2", "--border", "--border-strong"):
            result[ppt_token] = val
        elif is_hex6(val.split()[0]) or val.startswith("rgba(") or val.startswith("hsla("):
            result[ppt_token] = val.lower()

    # Pass 2: direct pass-through for any PPT token not yet filled
    # (html-ppt themes often use the same --text-1 / --bg-soft names directly)
    for token_name in PPT_TOKENS:
        if token_name in result:
            continue
        val = tokens.get(token_name, "")
        if not val:
            continue
        val = val.strip().rstrip(";")
        if token_name.startswith("--font") or token_name.startswith("--radius") or token_name.startswith("--shadow"):
            result[token_name] = val
        elif token_name in ("--grad", "--grad-soft"):
            continue
        elif token_name in ("--surface", "--surface-2", "--border", "--border-strong"):
            # Allow rgba() / hsla() values — common in dark/glass themes
            result[token_name] = val
        elif is_hex6(val.split()[0]) or val.startswith("rgba(") or val.startswith("hsla("):
            result[token_name] = val.lower()

    # Fill gaps — but only for tokens still missing
    _fill_neutral_gaps(result)
    _synthesize_gradients(result)
    return result


def sync_html_ppt_themes() -> list[str]:
    """Discover available html-ppt theme names from the open-design repo."""
    if not _HTML_PPT_THEMES_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _HTML_PPT_THEMES_DIR.glob("*.css")
        if p.stem not in ("base", "fonts", "animations")
    )


def _synthesize_gradients(result: dict[str, str]) -> None:
    if "--grad" not in result:
        a1 = result.get("--accent", FALLBACKS["--accent"])
        a2 = result.get("--accent-2", a1)
        result["--grad"] = f"linear-gradient(135deg, {a1}, {a2})"
    if "--grad-soft" not in result:
        a1 = result.get("--accent", FALLBACKS["--accent"])
        a2 = result.get("--accent-2", a1)
        r1, g1, b1 = hex_to_rgb(a1)
        r2, g2, b2 = hex_to_rgb(a2)
        result["--grad-soft"] = (
            f"linear-gradient(135deg, rgba({r1},{g1},{b1},0.08), rgba({r2},{g2},{b2},0.04))"
        )


# ── Output ──────────────────────────────────────────────────────────

def fill_fallbacks(result: dict[str, str]) -> dict[str, str]:
    out = dict(result)
    for token in PPT_TOKENS:
        if token not in out or not out[token]:
            out[token] = FALLBACKS[token]
    return out


def write_theme_css(theme_name: str, tokens: dict[str, str]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{theme_name}.css"
    lines = [
        f"/* PPT theme: {theme_name} — auto-generated from open-design */",
        "",
        ":root {",
    ]
    for token in PPT_TOKENS:
        val = tokens.get(token, FALLBACKS[token])
        lines.append(f"  {token}: {val};")
    lines.append("}")
    lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ── Main ────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Convert design systems to PPT theme CSS")
    parser.add_argument("--html-ppt", action="store_true", help="Also convert html-ppt themes from open-design")
    args = parser.parse_args()

    if not DESIGN_SYSTEMS_DIR.is_dir():
        print(f"Design systems directory not found: {DESIGN_SYSTEMS_DIR}")
        sys.exit(1)

    ds_dirs = sorted(
        d for d in DESIGN_SYSTEMS_DIR.iterdir()
        if d.is_dir() and d.name != "_schema"
    )

    token_count = 0
    heuristic_count = 0
    html_ppt_count = 0
    skipped = 0
    num_tokens = len(PPT_TOKENS)

    for ds_dir in ds_dirs:
        name = ds_dir.name
        design_md = ds_dir / "DESIGN.md"
        tokens_css = ds_dir / "tokens.css"

        if not design_md.is_file():
            print(f"  SKIP {name}: no DESIGN.md")
            skipped += 1
            continue

        tokens: dict[str, str] = {}

        if tokens_css.is_file():
            tokens = convert_from_tokens_css(tokens_css)
            source = "tokens.css"
            token_count += 1
        else:
            tokens = convert_from_design_md(design_md)
            source = "DESIGN.md"
            heuristic_count += 1

        tokens = fill_fallbacks(tokens)
        write_theme_css(name, tokens)
        custom_count = sum(
            1 for t in PPT_TOKENS
            if t in tokens and tokens[t] != FALLBACKS.get(t, "")
        )
        print(f"  {name:20s} ← {source:10s}  ({custom_count}/{num_tokens} custom)")

    # Path C: html-ppt themes
    if args.html_ppt:
        html_themes = sync_html_ppt_themes()
        print(f"\nFound {len(html_themes)} html-ppt themes. Converting...\n")
        for theme_name in html_themes:
            theme_path = _HTML_PPT_THEMES_DIR / f"{theme_name}.css"
            tokens = convert_from_html_ppt_theme(theme_path)
            if tokens:
                tokens = fill_fallbacks(tokens)
                write_theme_css(theme_name, tokens)
                custom_count = sum(
                    1 for t in PPT_TOKENS
                    if t in tokens and tokens[t] != FALLBACKS.get(t, "")
                )
                print(f"  {theme_name:20s} ← html-ppt   ({custom_count}/{num_tokens} custom)")
                html_ppt_count += 1

    print(f"\nDone: {token_count} from tokens.css, {heuristic_count} from DESIGN.md, {html_ppt_count} from html-ppt, {skipped} skipped")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
