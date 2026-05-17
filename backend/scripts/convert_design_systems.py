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

# ── 17 PPT theme tokens ─────────────────────────────────────────────
PPT_TOKENS = [
    "--bg", "--bg-soft", "--surface", "--surface-2",
    "--border", "--border-strong",
    "--text-1", "--text-2", "--text-3",
    "--accent", "--accent-2", "--accent-3",
    "--good", "--warn", "--bad",
    "--grad", "--grad-soft",
]

# Mapping: design-system token name → PPT token name
DS_TO_PPT: dict[str, str] = {
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


def _fill_neutral_gaps(result: dict[str, str]) -> None:
    """Derive missing neutral tokens from what we have."""
    if "--bg-soft" not in result and "--bg" in result:
        result["--bg-soft"] = darken(result["--bg"], 0.03) if perceived_lightness(result["--bg"]) > 200 else lighten(result["--bg"], 0.1)
    if "--surface" not in result:
        result["--surface"] = darken(result.get("--bg", FALLBACKS["--bg"]), 0.02)
    if "--surface-2" not in result:
        src = result.get("--bg-soft", result.get("--bg", FALLBACKS["--bg"]))
        result["--surface-2"] = darken(src, 0.06)
    if "--border" not in result:
        result["--border"] = lighten(result.get("--text-1", FALLBACKS["--text-1"]), 0.75)
    if "--border-strong" not in result:
        result["--border-strong"] = lighten(result.get("--text-1", FALLBACKS["--text-1"]), 0.55)
    if "--text-2" not in result and "--text-1" in result:
        result["--text-2"] = lighten(result["--text-1"], 0.4)
    if "--text-3" not in result:
        result["--text-3"] = lighten(result.get("--text-1", FALLBACKS["--text-1"]), 0.65)


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
    return classify_colors_for_ppt(subs)


# ── Gradient synthesis ──────────────────────────────────────────────

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
    if not DESIGN_SYSTEMS_DIR.is_dir():
        print(f"Design systems directory not found: {DESIGN_SYSTEMS_DIR}")
        sys.exit(1)

    ds_dirs = sorted(
        d for d in DESIGN_SYSTEMS_DIR.iterdir()
        if d.is_dir() and d.name != "_schema"
    )

    token_count = 0
    heuristic_count = 0
    skipped = 0

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
        print(f"  {name:20s} ← {source:10s}  ({custom_count}/17 custom)")

    print(f"\nDone: {token_count} from tokens.css, {heuristic_count} from DESIGN.md, {skipped} skipped")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
