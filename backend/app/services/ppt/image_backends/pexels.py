"""Pexels 图片搜索后端（需 API Key）

Pexels 提供高质量免费图片，需要注册获取 API Key。
API Key 通过 PEXELS_API_KEY 环境变量配置。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import ImageSearchBackend, ImageResult

_logger = logging.getLogger("ppt.image_search.pexels")

# Pexels API 端点
PEXELS_API = "https://api.pexels.com/v1/search"

# 方向映射
ORIENTATION_MAP = {
    "landscape": "landscape",
    "portrait": "portrait",
    "square": "square",
}


class PexelsBackend(ImageSearchBackend):
    """Pexels 图片搜索"""

    @property
    def name(self) -> str:
        return "pexels"

    @property
    def is_available(self) -> bool:
        """检查是否配置了 API Key"""
        return bool(os.getenv("PEXELS_API_KEY"))

    async def search(
        self,
        query: str,
        count: int = 5,
        orientation: str = "landscape",
        license_type: str = "cc-by",
    ) -> list[ImageResult]:
        """搜索 Pexels 图片"""

        api_key = os.getenv("PEXELS_API_KEY")
        if not api_key:
            _logger.debug("PEXELS_API_KEY not set, skipping Pexels search")
            return []

        # 构建查询参数
        params: dict[str, Any] = {
            "query": query,
            "per_page": min(count, 80),
            "orientation": ORIENTATION_MAP.get(orientation, "landscape"),
        }

        headers = {
            "Authorization": api_key,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(PEXELS_API, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

            results: list[ImageResult] = []
            for photo in data.get("photos", []):
                if len(results) >= count:
                    break

                # 获取图片尺寸
                width = photo.get("width", 0)
                height = photo.get("height", 0)

                # 获取不同尺寸的 URL
                src = photo.get("src", {})
                url = src.get("large2x", src.get("large", src.get("original", "")))
                thumbnail = src.get("medium", url)

                # 摄影师信息
                photographer = photo.get("photographer", "Unknown")
                photographer_url = photo.get("photographer_url", "")

                results.append(ImageResult(
                    url=url,
                    thumbnail_url=thumbnail,
                    source="pexels",
                    license="Pexels License",  # Pexels 使用自有许可证，免费商用
                    license_url="https://www.pexels.com/license/",
                    attribution=f"Photo by {photographer} on Pexels",
                    width=width,
                    height=height,
                    title=photo.get("alt", ""),
                ))

            return results

        except httpx.HTTPStatusError as e:
            _logger.warning("Pexels API error: %s %s", e.response.status_code, e.response.text[:200])
            return []
        except Exception as e:
            _logger.warning("Pexels search failed: %s", e)
            return []
