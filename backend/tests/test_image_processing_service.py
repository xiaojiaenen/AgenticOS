"""创作画布图片处理服务单测（Pillow 纯本地，无网络）。"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.services.image_processing_service import (
    ImageProcessingError,
    process_image,
)


def _png(width: int = 200, height: int = 100, color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def test_crop():
    out, fmt, size = process_image(_png(), operation="crop",
                                   crop={"x": 10, "y": 10, "width": 100, "height": 50})
    assert fmt == "PNG"
    assert size == (100, 50)
    assert Image.open(io.BytesIO(out)).size == (100, 50)


def test_crop_out_of_bounds_rejected():
    with pytest.raises(ImageProcessingError, match="超出"):
        process_image(_png(), operation="crop",
                      crop={"x": 150, "y": 0, "width": 100, "height": 50})


def test_resize():
    out, fmt, size = process_image(_png(), operation="resize",
                                   resize={"width": 80, "height": 40}, output_format="WEBP")
    assert fmt == "WEBP"
    assert size == (80, 40)
    assert Image.open(io.BytesIO(out)).size == (80, 40)


def test_compress_to_jpeg():
    out, fmt, size = process_image(_png(), operation="compress",
                                   output_format="JPEG", quality=70)
    assert fmt == "JPEG"
    assert size == (200, 100)
    assert Image.open(io.BytesIO(out)).format == "JPEG"


def test_rotate_90():
    out, fmt, size = process_image(_png(), operation="rotate", degrees=90)
    assert size == (100, 200)


def test_rotate_must_be_multiple_of_90():
    with pytest.raises(ImageProcessingError, match="90"):
        process_image(_png(), operation="rotate", degrees=45)


def test_thumbnail_keeps_aspect():
    out, fmt, size = process_image(_png(200, 100), operation="thumbnail",
                                   thumbnail={"width": 100, "height": 100})
    assert size[0] <= 100 and size[1] <= 100
    assert size[0] / size[1] == pytest.approx(2.0, abs=0.05)


def test_watermark():
    out, fmt, size = process_image(_png(), operation="watermark", watermark="AgenticOS")
    assert Image.open(io.BytesIO(out)).size == size


def test_bad_format_rejected():
    with pytest.raises(ImageProcessingError, match="不支持的输出格式"):
        process_image(_png(), operation="compress", output_format="exe")


def test_empty_input_rejected():
    with pytest.raises(ImageProcessingError, match="为空"):
        process_image(b"", operation="compress")


def test_corrupt_input_rejected():
    with pytest.raises(ImageProcessingError, match="无法读取"):
        process_image(b"not an image", operation="compress")


def test_unknown_operation_rejected():
    with pytest.raises(ImageProcessingError, match="不支持的操作"):
        process_image(_png(), operation="teleport")
