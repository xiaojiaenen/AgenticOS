#!/usr/bin/env python3
"""
PPT Master - Unified Configuration Management Module

Centrally manages canvas format and SVG constraint configuration.

Usage:
    from config import Config, CANVAS_FORMATS

    # Get canvas format
    ppt169 = Config.get_canvas_format('ppt169')
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import os


# ============================================================
# Path Configuration
# ============================================================

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Core directories
SCRIPTS_DIR = PROJECT_ROOT / 'scripts'
REFERENCES_DIR = PROJECT_ROOT / 'references'
TEMPLATES_DIR = PROJECT_ROOT / 'templates'
WORKFLOWS_DIR = PROJECT_ROOT / 'workflows'

# Repository root directory
REPO_ROOT = PROJECT_ROOT.parent.parent
EXAMPLES_DIR = REPO_ROOT / 'examples'
PROJECTS_DIR = REPO_ROOT / 'projects'

# Template subdirectories
CHART_TEMPLATES_DIR = TEMPLATES_DIR / 'charts'


# ============================================================
# Environment Configuration
# ============================================================

USER_CONFIG_DIR = Path.home() / '.ppt-master'
USER_ENV_FILE = USER_CONFIG_DIR / '.env'


def get_env_candidates() -> list[Path]:
    """Return the supported .env lookup order."""
    return [
        Path.cwd() / '.env',
        REPO_ROOT / '.env',
        USER_ENV_FILE,
    ]


def resolve_env_path() -> Path:
    """
    Return the first existing .env path.

    If no candidate exists, return the CWD .env path so callers can no-op
    consistently while still showing a useful default location in messages.
    """
    candidates = get_env_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def strip_env_quotes(value: str) -> str:
    """Strip matching surrounding quotes from a .env value."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def strip_inline_env_comment(value: str) -> str:
    """Strip an unquoted inline ``#`` comment from a .env value.

    Matches standard dotenv behavior: a ``#`` outside surrounding quotes
    starts a comment and is dropped along with the rest of the line. To keep
    a literal ``#`` in the value, wrap it in single or double quotes.
    """
    stripped = value.lstrip()
    if stripped.startswith(('"', "'")):
        quote = stripped[0]
        end = stripped.find(quote, 1)
        if end != -1:
            head = value[: len(value) - len(stripped) + end + 1]
            tail = value[len(head):]
            hash_pos = tail.find('#')
            if hash_pos == -1:
                return value
            return head + tail[:hash_pos]
        return value
    hash_pos = value.find('#')
    if hash_pos == -1:
        return value
    return value[:hash_pos]


def load_prefixed_env_file(
    prefixes: tuple[str, ...],
    *,
    deprecated_keys: Optional[dict[str, str]] = None,
) -> Optional[Path]:
    """
    Load matching keys from the first supported .env file.

    Existing process environment variables always win. Keys outside the
    requested prefixes are ignored so one shared .env can hold image, search,
    and narration credentials without leaking unrelated values into the
    process.
    """
    env_path = resolve_env_path()
    if not env_path.exists():
        return None

    deprecated_keys = deprecated_keys or {}
    with env_path.open('r', encoding='utf-8') as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[7:].lstrip()
            if '=' not in line:
                raise ValueError(
                    f"Invalid line in {env_path}:{lineno}. Expected KEY=VALUE."
                )

            key, value = line.split('=', 1)
            key = key.strip()
            if not key:
                raise ValueError(
                    f"Invalid line in {env_path}:{lineno}. Missing variable name."
                )
            if not any(key.startswith(prefix) for prefix in prefixes):
                continue
            if key in deprecated_keys:
                raise ValueError(
                    f"Unsupported key in {env_path}:{lineno}: {key}\n"
                    f"{deprecated_keys[key]}"
                )
            cleaned = strip_inline_env_comment(value).strip()
            os.environ.setdefault(key, strip_env_quotes(cleaned))

    return env_path


# ============================================================
# Canvas Format Configuration
# ============================================================

CANVAS_FORMATS = {
    'ppt169': {
        'name': 'PPT 16:9',
        'dimensions': '1280×720',
        'viewbox': '0 0 1280 720',
        'width': 1280,
        'height': 720,
        'aspect_ratio': '16:9',
        'use_case': 'Modern projectors, online presentations'
    },
    'ppt43': {
        'name': 'PPT 4:3',
        'dimensions': '1024×768',
        'viewbox': '0 0 1024 768',
        'width': 1024,
        'height': 768,
        'aspect_ratio': '4:3',
        'use_case': 'Traditional projectors'
    },
    'wechat': {
        'name': 'WeChat Article Header',
        'dimensions': '900×383',
        'viewbox': '0 0 900 383',
        'width': 900,
        'height': 383,
        'aspect_ratio': '2.35:1',
        'use_case': 'WeChat article cover images'
    },
    'xiaohongshu': {
        'name': '小红书',
        'dimensions': '1242×1660',
        'viewbox': '0 0 1242 1660',
        'width': 1242,
        'height': 1660,
        'aspect_ratio': '3:4',
        'use_case': 'Knowledge sharing, product reviews'
    },
    'moments': {
        'name': 'Moments/Instagram',
        'dimensions': '1080×1080',
        'viewbox': '0 0 1080 1080',
        'width': 1080,
        'height': 1080,
        'aspect_ratio': '1:1',
        'use_case': 'Social media square images'
    },
    'story': {
        'name': 'Story/Vertical',
        'dimensions': '1080×1920',
        'viewbox': '0 0 1080 1920',
        'width': 1080,
        'height': 1920,
        'aspect_ratio': '9:16',
        'use_case': 'Short video covers, stories'
    },
    'banner': {
        'name': 'Horizontal Banner',
        'dimensions': '1920×1080',
        'viewbox': '0 0 1920 1080',
        'width': 1920,
        'height': 1080,
        'aspect_ratio': '16:9',
        'use_case': 'Web banners, large screen displays'
    },
    'a4': {
        'name': 'A4 Print',
        'dimensions': '1240×1754',
        'viewbox': '0 0 1240 1754',
        'width': 1240,
        'height': 1754,
        'aspect_ratio': '√2:1',
        'use_case': 'Print documents, PDF export'
    }
}


# Removed DESIGN_COLORS, INDUSTRY_COLORS, FONTS, FONT_SIZES, LAYOUT_MARGINS
# (legacy HTML→PPTX pipeline — replaced by data/design-themes/*.css token system)


# ============================================================
# SVG Technical Specifications
# ============================================================

SVG_CONSTRAINTS = {
    # Forbidden elements - PPT incompatible
    'forbidden_elements': [
        # Clipping / Masking
        # Note: `clipPath` on <image> elements is conditionally allowed — the
        # converter maps qualifying clip shapes to DrawingML picture geometry.
        # See references/shared-standards.md §1.2. It is NOT listed here
        # because this flat list has no per-parent-element semantics; the
        # actual validation is in svg_quality_checker._check_forbidden_elements.
        'mask',
        # Style system
        'style',
        # Structure / Nesting
        'foreignObject',
        # Text / Fonts
        'textPath',
        # Animation / Interaction
        'animate',
        'animateMotion',
        'animateTransform',
        'animateColor',
        'set',
        'script',
        # Others
        'iframe',
    ],
    # Forbidden attributes
    # Note: marker-start / marker-end are NOT banned — they are conditionally
    # allowed (see references/shared-standards.md §1.1). The svg_to_pptx
    # converter maps qualifying <marker> defs to native DrawingML
    # <a:headEnd>/<a:tailEnd>.
    'forbidden_attributes': [
        'class',
        'id',
        'onclick', 'onload', 'onmouseover', 'onmouseout',
        'onfocus', 'onblur', 'onchange',
    ],
    # Forbidden patterns (regex matching)
    'forbidden_patterns': [
        r'@font-face',  # Web fonts
        r'rgba\s*\(',   # rgba colors (PPT incompatible)
        r'<\?xml-stylesheet\b',  # External CSS
        r'<link[^>]*rel\s*=\s*["\']stylesheet["\']',
        r'@import\s+',  # External CSS
        r'<g[^>]*\sopacity\s*=',  # Group opacity
        r'<image[^>]*\sopacity\s*=',  # Image opacity
        r'\bon\w+\s*=',  # Event attributes
        r'(?s)(?=.*<symbol)(?=.*<use\b)',  # <symbol> + <use> complex usage (order-independent)
    ],
    'recommended_fonts': [
        'system-ui',
        '-apple-system',
        'BlinkMacSystemFont',
        'Segoe UI'
    ]
}


# ============================================================
# Configuration Manager Class
# ============================================================

class Config:
    """Configuration manager."""

    @staticmethod
    def get_canvas_format(format_key: str) -> Optional[Dict]:
        """
        Get canvas format configuration.

        Args:
            format_key: Format key name (e.g. 'ppt169', 'xiaohongshu')

        Returns:
            Format configuration dict, or None if not found
        """
        return CANVAS_FORMATS.get(format_key)

    @staticmethod
    def get_all_canvas_formats() -> Dict:
        """Get all canvas formats."""
        return CANVAS_FORMATS.copy()

    @staticmethod
    def validate_svg_element(element_name: str) -> bool:
        """
        Validate whether an SVG element is allowed.

        Args:
            element_name: Element name

        Returns:
            Whether the element is allowed
        """
        return element_name.lower() not in [e.lower() for e in SVG_CONSTRAINTS['forbidden_elements']]

    @staticmethod
    def get_project_path(subdir: str = '') -> Path:
        """
        Get project path.

        Args:
            subdir: Subdirectory name

        Returns:
            Full path
        """
        if subdir:
            return PROJECT_ROOT / subdir
        return PROJECT_ROOT

# ============================================================
# Command Line Interface
# ============================================================

def print_usage() -> None:
    """Print CLI usage information."""
    print("PPT Master - Configuration Management Tool\n")
    print("Usage:")
    print("  python3 scripts/config.py list-formats     # List all canvas formats")
    print("  python3 scripts/config.py format <key>     # View a specific canvas format")


def main() -> None:
    """Command line entry point."""
    import sys

    if len(sys.argv) < 2:
        print_usage()
        return

    command = sys.argv[1]
    if command in {"-h", "--help", "help"}:
        print_usage()
        return

    if command == 'list-formats':
        print("\nCanvas Format List:\n")
        for key, info in CANVAS_FORMATS.items():
            print(
                f"  {key:15} | {info['name']:15} | {info['dimensions']:12} | {info['use_case']}")

    elif command == 'format' and len(sys.argv) > 2:
        format_key = sys.argv[2]
        info = Config.get_canvas_format(format_key)
        if info:
            print(f"\nCanvas Format: {format_key}\n")
            for key, value in info.items():
                print(f"  {key}: {value}")
        else:
            print(f"[ERROR] Format not found: {format_key}")
            print(f"   Available formats: {', '.join(CANVAS_FORMATS.keys())}")

    else:
        print(f"[ERROR] Unknown command: {command}")


if __name__ == '__main__':
    main()
