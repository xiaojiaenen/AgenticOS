"""创作画布的图片处理服务（Pillow 纯本地，无外部依赖）。

提供非 AI 的图片处理：裁剪 / 缩放 / 压缩 / 旋转 / 格式转换 / 水印 / 缩略图。
这些操作全部在进程内完成，不调用上游大模型，因此内网也能用。

安全纪律：
- 输入字节上限（默认 20MB），防超大图打爆内存；
- Pillow decompression bomb 关闭限制由 MAX_IMAGE_PIXELS 兜底；
- 输出格式白名单，禁止意外格式；
- EXIF 方向自动校正，避免手机竖拍图旋转 90°。
"""

from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger("agenticos.image_processing")

MAX_INPUT_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000
ALLOWED_OUTPUT_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class ImageProcessingError(ValueError):
    """图片处理失败（参数非法 / 图片损坏 / 超限）。"""


def _target_format(output_format: str) -> str:
    fmt = (output_format or "").upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if fmt not in ALLOWED_OUTPUT_FORMATS:
        raise ImageProcessingError(f"不支持的输出格式：{output_format}")
    return fmt


def _load(data: bytes) -> Image.Image:
    if not data:
        raise ImageProcessingError("图片内容为空")
    if len(data) > MAX_INPUT_BYTES:
        raise ImageProcessingError(f"图片超过 {MAX_INPUT_BYTES // 1024 // 1024}MB 上限")
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(f"无法读取图片：{exc}") from exc
    # EXIF 方向校正后剥离元数据（也避免泄露 GPS 等隐私）
    img = ImageOps.exif_transpose(img)
    return img


def _serialize(img: Image.Image, fmt: str, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    save_kwargs: dict[str, Any] = {}
    if fmt == "JPEG":
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        save_kwargs = {"quality": max(1, min(95, quality)), "optimize": True}
    elif fmt == "WEBP":
        save_kwargs = {"quality": max(1, min(95, quality)), "method": 6}
    elif fmt == "GIF":
        img = img.convert("P", palette=Image.ADAPTIVE)
    img.save(buf, format=fmt, **save_kwargs)
    return buf.getvalue()


def process_image(
    data: bytes,
    *,
    operation: str,
    output_format: str = "PNG",
    quality: int = 85,
    crop: dict[str, int] | None = None,
    resize: dict[str, int] | None = None,
    degrees: int = 0,
    watermark: str = "",
    thumbnail: dict[str, int] | None = None,
) -> tuple[bytes, str, tuple[int, int]]:
    """执行一项图片处理，返回 (字节, 实际格式, 尺寸)。

    operation: crop / resize / compress / rotate / watermark / thumbnail
    """
    fmt = _target_format(output_format)
    img = _load(data)

    if operation == "crop":
        if not crop:
            raise ImageProcessingError("裁剪需要 crop 参数（x/y/width/height）")
        try:
            x, y, w, h = int(crop["x"]), int(crop["y"]), int(crop["width"]), int(crop["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ImageProcessingError("crop 参数必须是整数 x/y/width/height") from exc
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > img.width or y + h > img.height:
            raise ImageProcessingError("裁剪区域超出图片范围")
        img = img.crop((x, y, x + w, y + h))
    elif operation == "resize":
        if not resize:
            raise ImageProcessingError("缩放需要 resize 参数（width/height）")
        try:
            w, h = int(resize["width"]), int(resize["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ImageProcessingError("resize 参数必须是整数 width/height") from exc
        if w <= 0 or h <= 0 or w > 8192 or h > 8192:
            raise ImageProcessingError("缩放尺寸必须在 1~8192 之间")
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    elif operation == "thumbnail":
        if not thumbnail:
            raise ImageProcessingError("缩略图需要 thumbnail 参数（width/height）")
        try:
            w, h = int(thumbnail["width"]), int(thumbnail["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ImageProcessingError("thumbnail 参数必须是整数 width/height") from exc
        if w <= 0 or h <= 0:
            raise ImageProcessingError("缩略图尺寸必须为正整数")
        img = img.copy()
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
    elif operation == "compress":
        # 仅重新编码（换格式 / 调质量），尺寸不变
        pass
    elif operation == "rotate":
        if degrees % 90 != 0:
            raise ImageProcessingError("旋转角度必须是 90 的倍数")
        img = img.rotate(degrees % 360, expand=True)
    elif operation == "watermark":
        text = (watermark or "").strip()
        if not text:
            raise ImageProcessingError("水印需要 watermark 文本")
        img = img.convert("RGBA")
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        try:
            font = ImageFont.truetype("arial.ttf", max(14, img.width // 24))
        except OSError:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x, y = img.width - tw - 16, img.height - th - 16
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 170))
        img = Image.alpha_composite(img, layer).convert("RGB")
    else:
        raise ImageProcessingError(f"不支持的操作：{operation}")

    size = img.size
    result = _serialize(img, fmt, quality)
    return result, fmt, size
