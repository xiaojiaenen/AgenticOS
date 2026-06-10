"""Openverse 图片搜索后端（零配置，免费）

Openverse 是 WordPress 基金会运营的开放内容搜索引擎，
聚合了 600M+ 张 CC 许可图片。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import ImageSearchBackend, ImageResult

_logger = logging.getLogger("ppt.image_search.openverse")

# Openverse API 端点
OPENVERSE_API = "https://api.openverse.org/v1/images/"

# 许可证映射
LICENSE_MAP = {
    "cc0": "CC0",
    "cc-by": "BY",
    "cc-by-sa": "BY-SA",
    "cc-by-nc": "BY-NC",
    "cc-by-nc-sa": "BY-NC-SA",
}


class OpenverseBackend(ImageSearchBackend):
    """Openverse 图片搜索"""

    @property
    def name(self) -> str:
        return "openverse"

    async def search(
        self,
        query: str,
        count: int = 5,
        orientation: str = "landscape",
        license_type: str = "cc-by",
    ) -> list[ImageResult]:
        """搜索 Openverse 图片"""

        # 构建查询参数
        params: dict[str, Any] = {
            "q": query,
            "page_size": min(count * 2, 50),  # 多取一些，后续过滤
            "license": LICENSE_MAP.get(license_type, "BY"),
            "mature": "false",
        }

        # 方向过滤
        if orientation == "landscape":
            params["aspect_ratio"] = "wide"
        elif orientation == "portrait":
            params["aspect_ratio"] = "tall"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(OPENVERSE_API, params=params)
                response.raise_for_status()
                data = response.json()

            results: list[ImageResult] = []
            for item in data.get("results", []):
                if len(results) >= count:
                    break

                # 解析尺寸
                width = item.get("width") or 0
                height = item.get("height") or 0

                # 方向二次过滤
                if not self._match_orientation(width, height, orientation):
                    continue

                # 构建署名信息
                creator = item.get("creator", "Unknown")
                source = item.get("source", "")
                attribution = f"by {creator}"
                if source:
                    attribution += f" / {source}"

                results.append(ImageResult(
                    url=item.get("url", ""),
                    thumbnail_url=item.get("thumbnail", item.get("url", "")),
                    source="openverse",
                    license=self._normalize_license(item.get("license", "")),
                    license_url=item.get("license_url", ""),
                    attribution=attribution,
                    width=width,
                    height=height,
                    title=item.get("title", ""),
                ))

            return results

        except httpx.HTTPStatusError as e:
            _logger.warning("Openverse API error: %s %s", e.response.status_code, e.response.text[:200])
            return []
        except Exception as e:
            _logger.warning("Openverse search failed: %s", e)
            return []
