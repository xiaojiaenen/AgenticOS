"""Pixabay 图片搜索后端（需 API Key）

Pixabay 提供高质量免费图片，需要注册获取 API Key。
API Key 通过 PIXABAY_API_KEY 环境变量配置。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from .base import ImageSearchBackend, ImageResult

_logger = logging.getLogger("ppt.image_search.pixabay")

# Pixabay API 端点
PIXABAY_API = "https://pixabay.com/api/"

# 方向映射
ORIENTATION_MAP = {
    "landscape": "horizontal",
    "portrait": "vertical",
    "square": "horizontal",  # Pixabay 没有方形过滤
}


class PixabayBackend(ImageSearchBackend):
    """Pixabay 图片搜索"""

    @property
    def name(self) -> str:
        return "pixabay"

    @property
    def is_available(self) -> bool:
        """检查是否配置了 API Key"""
        return bool(os.getenv("PIXABAY_API_KEY"))

    async def search(
        self,
        query: str,
        count: int = 5,
        orientation: str = "landscape",
        license_type: str = "cc-by",
    ) -> list[ImageResult]:
        """搜索 Pixabay 图片"""

        api_key = os.getenv("PIXABAY_API_KEY")
        if not api_key:
            _logger.debug("PIXABAY_API_KEY not set, skipping Pixabay search")
            return []

        # 构建查询参数
        params: dict[str, Any] = {
            "key": api_key,
            "q": query,
            "per_page": min(count, 200),
            "orientation": ORIENTATION_MAP.get(orientation, "horizontal"),
            "image_type": "photo",
            "safesearch": "true",
        }

        # 许可证过滤
        if license_type == "cc0":
            params["editors_choice"] = "true"  # 编辑精选通常更自由

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(PIXABAY_API, params=params)
                response.raise_for_status()
                data = response.json()

            results: list[ImageResult] = []
            for hit in data.get("hits", []):
                if len(results) >= count:
                    break

                # 获取图片尺寸
                width = hit.get("imageWidth", 0)
                height = hit.get("imageHeight", 0)

                # 获取图片 URL
                url = hit.get("largeImageURL", hit.get("webformatURL", ""))
                thumbnail = hit.get("previewURL", url)

                # 用户信息
                user = hit.get("user", "Unknown")

                results.append(ImageResult(
                    url=url,
                    thumbnail_url=thumbnail,
                    source="pixabay",
                    license="Pixabay License",  # Pixabay 使用自有许可证，免费商用
                    license_url="https://pixabay.com/service/license-summary/",
                    attribution=f"Image by {user} from Pixabay",
                    width=width,
                    height=height,
                    title=hit.get("tags", ""),
                ))

            return results

        except httpx.HTTPStatusError as e:
            _logger.warning("Pixabay API error: %s %s", e.response.status_code, e.response.text[:200])
            return []
        except Exception as e:
            _logger.warning("Pixabay search failed: %s", e)
            return []
