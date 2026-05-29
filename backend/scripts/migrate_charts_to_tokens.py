"""Migrate data/charts/*.svg hardcoded hex colors to var(--token) format.

Converts chart SVGs from hardcoded Tailwind hex values to the AgenticOS
design token system (var(--bg), var(--accent), etc.) so they can be used
alongside the existing svg_layouts.py templates.

Usage:
    python scripts/migrate_charts_to_tokens.py [--dry-run] [--source DIR] [--dest DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

# Default paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "charts"
DEFAULT_DEST = PROJECT_ROOT / "data" / "skills" / "ppt-template-library" / "references" / "charts"

# ── Color mapping: hex → token ──────────────────────────────────────────
# Each entry: (pattern_regex, replacement_token)
# Order matters — more specific patterns first.

COLOR_MAP: list[tuple[str, str]] = [
    # ── Backgrounds ──
    (r'#FFFFFF(?=[^0-9A-Fa-f]|$)', 'var(--bg)'),
    (r'#ffffff(?=[^0-9A-Fa-f]|$)', 'var(--bg)'),
    (r'#F8FAFC(?=[^0-9A-Fa-f]|$)', 'var(--bg-soft)'),
    (r'#f8fafc(?=[^0-9A-Fa-f]|$)', 'var(--bg-soft)'),
    (r'#F1F5F9(?=[^0-9A-Fa-f]|$)', 'var(--bg-soft)'),
    (r'#f1f5f9(?=[^0-9A-Fa-f]|$)', 'var(--bg-soft)'),
    (r'#F5F5F7(?=[^0-9A-Fa-f]|$)', 'var(--bg-soft)'),
    (r'#FBFBFD(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#fbfbfd(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#F9FAFB(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),

    # ── Surface / Card backgrounds ──
    (r'#F0F4F8(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#F0F9FF(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#ECFDF5(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#ECFEFF(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#FFF7ED(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#FEF2F2(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#FDF4FF(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),
    (r'#FFF1F2(?=[^0-9A-Fa-f]|$)', 'var(--surface)'),

    # ── Borders ──
    (r'#E2E8F0(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#e2e8f0(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#E0E0E0(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#e0e0e0(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#E5E7EB(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#D1D5DB(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#EEEEEE(?=[^0-9A-Fa-f]|$)', 'var(--border)'),
    (r'#eeeef0(?=[^0-9A-Fa-f]|$)', 'var(--surface-2)'),

    # ── Text: primary (darkest) ──
    (r'#0F172A(?=[^0-9A-Fa-f]|$)', 'var(--text-1)'),
    (r'#0f172a(?=[^0-9A-Fa-f]|$)', 'var(--text-1)'),
    (r'#1E293B(?=[^0-9A-Fa-f]|$)', 'var(--text-1)'),
    (r'#1e293b(?=[^0-9A-Fa-f]|$)', 'var(--text-1)'),
    (r'#111827(?=[^0-9A-Fa-f]|$)', 'var(--text-1)'),
    (r'#1F2937(?=[^0-9A-Fa-f]|$)', 'var(--text-1)'),

    # ── Text: secondary ──
    (r'#334155(?=[^0-9A-Fa-f]|$)', 'var(--text-2)'),
    (r'#475569(?=[^0-9A-Fa-f]|$)', 'var(--text-2)'),
    (r'#374151(?=[^0-9A-Fa-f]|$)', 'var(--text-2)'),
    (r'#374151(?=[^0-9A-Fa-f]|$)', 'var(--text-2)'),

    # ── Text: tertiary (lightest) ──
    (r'#64748B(?=[^0-9A-Fa-f]|$)', 'var(--text-3)'),
    (r'#64748b(?=[^0-9A-Fa-f]|$)', 'var(--text-3)'),
    (r'#6B7280(?=[^0-9A-Fa-f]|$)', 'var(--text-3)'),
    (r'#94A3B8(?=[^0-9A-Fa-f]|$)', 'var(--text-3)'),
    (r'#94a3b8(?=[^0-9A-Fa-f]|$)', 'var(--text-3)'),
    (r'#9CA3AF(?=[^0-9A-Fa-f]|$)', 'var(--text-3)'),

    # ── Accent: blue (primary brand color) ──
    (r'#3B82F6(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
    (r'#3b82f6(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
    (r'#2563EB(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#2563eb(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#1D4ED8(?=[^0-9A-Fa-f]|$)', 'var(--accent-3)'),
    (r'#1d4ed8(?=[^0-9A-Fa-f]|$)', 'var(--accent-3)'),
    (r'#0071e3(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
    (r'#0077ed(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#0066cc(?=[^0-9A-Fa-f]|$)', 'var(--accent-3)'),

    # ── Accent: sky/cyan (secondary blue) ──
    (r'#0EA5E9(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
    (r'#0ea5e9(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
    (r'#0284C7(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#0284c7(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#38BDF8(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),

    # ── Green (good/success) ──
    (r'#10B981(?=[^0-9A-Fa-f]|$)', 'var(--good)'),
    (r'#10b981(?=[^0-9A-Fa-f]|$)', 'var(--good)'),
    (r'#059669(?=[^0-9A-Fa-f]|$)', 'var(--good)'),
    (r'#16A34A(?=[^0-9A-Fa-f]|$)', 'var(--good)'),
    (r'#22C55E(?=[^0-9A-Fa-f]|$)', 'var(--good)'),
    (r'#14B8A6(?=[^0-9A-Fa-f]|$)', 'var(--good)'),
    (r'#0D9488(?=[^0-9A-Fa-f]|$)', 'var(--good)'),

    # ── Yellow/Amber (warn) ──
    (r'#F59E0B(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),
    (r'#f59e0b(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),
    (r'#D97706(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),
    (r'#EAB308(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),
    (r'#FBBF24(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),

    # ── Red (bad/danger) ──
    (r'#EF4444(?=[^0-9A-Fa-f]|$)', 'var(--bad)'),
    (r'#ef4444(?=[^0-9A-Fa-f]|$)', 'var(--bad)'),
    (r'#DC2626(?=[^0-9A-Fa-f]|$)', 'var(--bad)'),
    (r'#F87171(?=[^0-9A-Fa-f]|$)', 'var(--bad)'),

    # ── Orange ──
    (r'#F97316(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),
    (r'#f97316(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),
    (r'#EA580C(?=[^0-9A-Fa-f]|$)', 'var(--warn)'),

    # ── Purple/Indigo (map to accent) ──
    (r'#8B5CF6(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#7C3AED(?=[^0-9A-Fa-f]|$)', 'var(--accent-3)'),
    (r'#6366F1(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
    (r'#4F46E5(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),

    # ── Pink ──
    (r'#EC4899(?=[^0-9A-Fa-f]|$)', 'var(--accent-2)'),
    (r'#F472B6(?=[^0-9A-Fa-f]|$)', 'var(--accent)'),
]

# ── Gradient patterns ──
# Replace hex inside linearGradient/radialGradient stop-color attributes
GRADIENT_STOP_RE = re.compile(
    r'(stop-color\s*:\s*)(#[0-9A-Fa-f]{6})(?=;)'
)

# ── fill/stroke attribute patterns ──
ATTR_COLOR_RE = re.compile(
    r'((?:fill|stroke|flood-color|color)\s*=\s*["\']?)(#[0-9A-Fa-f]{6})(?=["\'\s;]|$)'
)

# fill="..." inside style attributes
STYLE_COLOR_RE = re.compile(
    r'((?:fill|stroke|stop-color|flood-color)\s*:\s*)(#[0-9A-Fa-f]{6})'
)


def build_color_replacements() -> list[tuple[re.Pattern, str]]:
    """Compile all color mapping patterns."""
    replacements = []
    for pattern, token in COLOR_MAP:
        replacements.append((re.compile(pattern, re.IGNORECASE), token))
    return replacements


def migrate_svg_content(svg_text: str, replacements: list[tuple[re.Pattern, str]]) -> str:
    """Replace hardcoded hex colors with var(--token) references."""
    result = svg_text
    for pattern, token in replacements:
        result = pattern.sub(token, result)
    return result


def add_data_theme_placeholder(svg_text: str) -> str:
    """Add data-theme attribute to <svg> tag if missing."""
    if 'data-theme' not in svg_text:
        svg_text = svg_text.replace(
            '<svg ',
            '<svg data-theme="theme-name" ',
            1
        )
    return svg_text


def migrate_file(
    source: Path,
    dest: Path,
    replacements: list[tuple[re.Pattern, str]],
    dry_run: bool = False,
) -> dict:
    """Migrate a single SVG file. Returns stats."""
    svg_text = source.read_text(encoding="utf-8")
    original = svg_text

    svg_text = add_data_theme_placeholder(svg_text)
    svg_text = migrate_svg_content(svg_text, replacements)

    # Count replacements
    changes = sum(1 for p, _ in replacements if p.search(original))

    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(svg_text, encoding="utf-8")

    return {
        "file": source.name,
        "hex_colors_replaced": changes,
        "size_before": len(original),
        "size_after": len(svg_text),
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate chart SVGs to var(--token)")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--copy-index", action="store_true", help="Also copy charts_index.json")
    args = parser.parse_args()

    replacements = build_color_replacements()

    svg_files = sorted(args.source.glob("*.svg"))
    if not svg_files:
        print(f"No SVG files found in {args.source}")
        return

    print(f"Migrating {len(svg_files)} SVGs: {args.source} → {args.dest}")
    if args.dry_run:
        print("[DRY RUN] No files will be written\n")

    total_replacements = 0
    for svg_file in svg_files:
        stats = migrate_file(svg_file, args.dest / svg_file.name, replacements, args.dry_run)
        total_replacements += stats["hex_colors_replaced"]
        print(f"  {stats['file']:40s} {stats['hex_colors_replaced']:3d} replacements")

    # Copy charts_index.json
    if args.copy_index:
        index_src = args.source / "charts_index.json"
        if index_src.exists():
            index_dest = args.dest / "charts_index.json"
            if not args.dry_run:
                shutil.copy2(index_src, index_dest)
            print(f"\n  Copied charts_index.json")

    print(f"\nDone: {len(svg_files)} files, {total_replacements} total replacements")


if __name__ == "__main__":
    main()
