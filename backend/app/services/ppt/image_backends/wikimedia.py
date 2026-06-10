"""Wikimedia Commons 图片搜索后端（零配置，免费）

Wikimedia Commons 是维基媒体基金会的媒体文件库，
包含 90M+ 张自由许可的图片。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import ImageSearchBackend, ImageResult

_logger = logging.getLogger("ppt.image_search.wikimedia")

# Wikimedia API 端点
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"

# Wikimedia 要求设置 User-Agent
USER_AGENT = "AgenticOS/1.0 (https://github.com/xiaojiaenen/AgenticOS; contact@agenticos.com)"


class WikimediaBackend(ImageSearchBackend):
    """Wikimedia Commons 图片搜索"""

    @property
    def name(self) -> str:
        return "wikimedia"

    async def search(
        self,
        query: str,
        count: int = 5,
        orientation: str = "landscape",
        license_type: str = "cc-by",
    ) -> list[ImageResult]:
        """搜索 Wikimedia Commons 图片"""

        # 构建查询参数
        params: dict[str, Any] = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": "6",  # File 命名空间
            "gsrlimit": min(count * 2, 50),
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "iiurlwidth": "1280",
            "format": "json",
        }

        headers = {
            "User-Agent": USER_AGENT,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(WIKIMEDIA_API, params=params, headers=headers)
                response.raise_for_status()
                data = response.json()

            results: list[ImageResult] = []
            pages = data.get("query", {}).get("pages", {})

            for page_id, page in pages.items():
                if len(results) >= count:
                    break

                imageinfo = page.get("imageinfo", [{}])[0]
                if not imageinfo:
                    continue

                # 解析尺寸
                width = imageinfo.get("width", 0)
                height = imageinfo.get("height", 0)

                # 方向过滤
                if not self._match_orientation(width, height, orientation):
                    continue

                # 获取元数据
                metadata = imageinfo.get("extmetadata", {})

                # 许可证信息
                license_name = metadata.get("LicenseShortName", {}).get("value", "")
                license_url = metadata.get("LicenseUrl", {}).get("value", "")
                artist = metadata.get("Artist", {}).get("value", "")

                # 清理 HTML 标签
                import re
                artist = re.sub(r"<[^>]+>", "", artist).strip()

                # 许可证类型过滤
                normalized_license = self._normalize_license(license_name)
                if license_type == "cc0" and normalized_license != "CC0":
                    continue

                # 构建署名
                attribution = artist if artist else "Unknown"

                results.append(ImageResult(
                    url=imageinfo.get("url", ""),
                    thumbnail_url=imageinfo.get("thumburl", imageinfo.get("url", "")),
                    source="wikimedia",
                    license=normalized_license,
                    license_url=license_url,
                    attribution=attribution,
                    width=width,
                    height=height,
                    title=page.get("title", "").replace("File:", ""),
                ))

            return results

        except httpx.HTTPStatusError as e:
            _logger.warning("Wikimedia API error: %s %s", e.response.status_code, e.response.text[:200])
            return []
        except Exception as e:
            _logger.warning("Wikimedia search failed: %s", e)
            return []
