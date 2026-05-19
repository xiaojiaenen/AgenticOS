"""SVG to PNG conversion for Office compatibility mode."""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger("svg_to_pptx.media")

# SVG to PNG library detection
# Prefer CairoSVG (better quality), fall back to svglib
PNG_RENDERER: str | None = None

try:
    import cairosvg
    PNG_RENDERER = 'cairosvg'
except (ImportError, OSError):
    try:
        from svglib.svglib import svg2rlg
        from reportlab.graphics import renderPM
        PNG_RENDERER = 'svglib'
    except (ImportError, OSError):
        pass


def get_png_renderer_info() -> tuple[str | None, str, str | None]:
    """Get PNG renderer status information.

    Returns:
        (renderer_name, status_text, install_hint) tuple.
    """
    if PNG_RENDERER == 'cairosvg':
        return ('cairosvg', '(full gradient/filter support)', None)
    elif PNG_RENDERER == 'svglib':
        return ('svglib', '(some gradients may be lost)',
                'Install cairosvg for better results: pip install cairosvg')
    else:
        return (None, '(not installed)',
                'Install via: pip install cairosvg or pip install svglib reportlab')


def convert_svg_to_png(
    svg_path: Path,
    png_path: Path,
    width: int | None = None,
    height: int | None = None,
    scale: float = 1.0,
) -> bool:
    """Convert SVG to PNG using the available renderer.

    Args:
        svg_path: SVG file path.
        png_path: Output PNG file path.
        width: Output width in pixels (before scale).
        height: Output height in pixels (before scale).
        scale: Scale multiplier for high-DPI output (e.g. 2.0 for 2x).

    Returns:
        Whether the conversion was successful.
    """
    if PNG_RENDERER is None:
        return False

    scaled_width = int(width * scale) if width else None
    scaled_height = int(height * scale) if height else None

    try:
        if PNG_RENDERER == 'cairosvg':
            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(png_path),
                output_width=scaled_width,
                output_height=scaled_height,
                scale=scale,
            )
            return True

        elif PNG_RENDERER == 'svglib':
            drawing = svg2rlg(str(svg_path))
            if drawing is None:
                logger.warning("Unable to parse SVG: %s", svg_path.name)
                return False
            renderPM.drawToFile(
                drawing,
                str(png_path),
                fmt="PNG",
                configPIL={'quality': 95},
            )
            # svglib doesn't support direct scale; post-scale with PIL
            if scale != 1.0 and scaled_width and scaled_height:
                try:
                    from PIL import Image
                    img = Image.open(str(png_path))
                    img = img.resize((scaled_width, scaled_height), Image.LANCZOS)
                    img.save(str(png_path), 'PNG')
                except ImportError:
                    pass
            return True

    except Exception as e:
        logger.warning("SVG to PNG conversion failed (%s): %s", svg_path.name, e)
        return False

    return False


def _cache_key(svg_path: Path, width: int | None, height: int | None, scale: float = 1.0) -> str:
    h = hashlib.sha256()
    with open(svg_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return f"{h.hexdigest()}_{width or 0}x{height or 0}_s{scale}_{PNG_RENDERER or 'none'}"


def convert_svg_to_png_cached(
    svg_path: Path,
    png_path: Path,
    width: int | None = None,
    height: int | None = None,
    cache_dir: Path | None = None,
    scale: float = 1.0,
) -> bool:
    """Cache-aware SVG→PNG conversion.

    Returns True on success (cache hit or fresh render). Cache key bakes in
    SVG content hash + size + renderer name; switching renderers invalidates
    naturally. Failures are never cached.
    """
    if cache_dir is None:
        return convert_svg_to_png(svg_path, png_path, width, height, scale)

    if PNG_RENDERER is None:
        return False

    try:
        key = _cache_key(svg_path, width, height, scale)
    except OSError as e:
        logger.warning("Failed to hash SVG (%s): %s", svg_path.name, e)
        return convert_svg_to_png(svg_path, png_path, width, height)

    cached = cache_dir / f"{key}.png"
    if cached.is_file():
        try:
            shutil.copy(cached, png_path)
            return True
        except OSError as e:
            logger.warning("Cache copy failed, re-rendering (%s): %s", svg_path.name, e)

    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(suffix='.png', dir=str(cache_dir))
    tmp_path = Path(tmp_name)
    import os
    os.close(tmp_fd)

    ok = convert_svg_to_png(svg_path, tmp_path, width, height, scale)
    if not ok:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        return False

    try:
        os.replace(tmp_path, cached)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    try:
        shutil.copy(cached, png_path)
        return True
    except OSError as e:
        logger.warning("Cache copy failed (%s): %s", svg_path.name, e)
        return False
