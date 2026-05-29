"""Extract core layout SVGs from svg_layouts.py into individual files.

Splits the SVG_LAYOUTS dict into individual .svg files for the
ppt-template-library skill's references/core-layouts/ directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.ppt.svg_layouts import SVG_LAYOUTS

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEST = PROJECT_ROOT / "data" / "skills" / "ppt-template-library" / "references" / "core-layouts"

# Core layouts to extract (page structure types)
CORE_LAYOUTS = [
    "cover", "toc", "section-divider",
    "stat-highlight", "kpi-grid",
    "bullets", "two-column", "three-column", "big-quote",
    "comparison", "pros-cons",
    "code", "terminal",
    "cta", "thanks",
]


def main():
    DEST.mkdir(parents=True, exist_ok=True)

    extracted = 0
    for name in CORE_LAYOUTS:
        if name not in SVG_LAYOUTS:
            print(f"  WARNING: '{name}' not found in SVG_LAYOUTS, skipping")
            continue

        svg_content = SVG_LAYOUTS[name]
        # Clean up: ensure proper XML header
        if not svg_content.strip().startswith("<?xml"):
            svg_content = svg_content.strip()

        dest_file = DEST / f"{name}.svg"
        dest_file.write_text(svg_content, encoding="utf-8")
        size = len(svg_content)
        print(f"  {name:25s} → {dest_file.name:30s} ({size:,d} chars)")
        extracted += 1

    print(f"\nExtracted {extracted}/{len(CORE_LAYOUTS)} core layouts to {DEST}")


if __name__ == "__main__":
    main()
