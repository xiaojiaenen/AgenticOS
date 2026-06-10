"""图片搜索聚合器

聚合多个图片搜索后端，提供统一的搜索接口。
零配置即可使用（Openverse + Wikimedia），可选配置 Pexels/Pixabay 获取更高质量图片。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .image_backends.base import ImageResult
from .image_backends.openverse import OpenverseBackend
from .image_backends.wikimedia import WikimediaBackend
from .image_backends.pexels import PexelsBackend
from .image_backends.pixabay import PixabayBackend

_logger = logging.getLogger("ppt.image_search")


class ImageSearchService:
    """图片搜索聚合器

    使用示例：
        service = ImageSearchService()
        results = await service.search("business meeting", count=5)
    """

    def __init__(self):
        # 零配置后端（始终可用）
        self.backends = [
            OpenverseBackend(),
            WikimediaBackend(),
        ]

        # 可选后端（需要 API Key）
        self._optional_backends = {
            "pexels": PexelsBackend,
            "pixabay": PixabayBackend,
        }

        # 尝试加载可选后端
        self._load_optional_backends()

    def _load_optional_backends(self):
        """加载配置了 API Key 的可选后端"""
        for name, backend_class in self._optional_backends.items():
            try:
                backend = backend_class()
                if backend.is_available:
                    self.backends.append(backend)
                    _logger.info("Loaded optional image backend: %s", name)
            except Exception as e:
                _logger.debug("Failed to load backend %s: %s", name, e)

    async def search(
        self,
        query: str,
        count: int = 5,
        orientation: str = "landscape",
        license_type: str = "cc-by",
        strict_no_attribution: bool = False,
    ) -> list[ImageResult]:
        """搜索图片

        参数:
            query: 搜索关键词（英文效果更好）
            count: 返回数量（1-20）
            orientation: 方向 (landscape/portrait/square)
            license_type: 许可证类型 (cc0/cc-by/cc-by-sa)
            strict_no_attribution: 是否只返回免署名的图片

        返回:
            图片结果列表，按相关性排序
        """
        if not query.strip():
            return []

        count = min(max(count, 1), 20)

        # 并发搜索所有后端
        tasks = [
            self._search_backend(backend, query, count, orientation, license_type)
            for backend in self.backends
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果
        all_results: list[ImageResult] = []
        for result in results:
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, Exception):
                _logger.warning("Backend search error: %s", result)

        # 过滤免署名
        if strict_no_attribution:
            all_results = [
                r for r in all_results
                if r.license in ("CC0", "Public Domain", "Pexels License", "Pixabay License")
            ]

        # 去重（按 URL）
        seen_urls: set[str] = set()
        unique_results: list[ImageResult] = []
        for result in all_results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)

        # 按来源优先级排序（Pexels > Pixabay > Openverse > Wikimedia）
        source_priority = {"pexels": 0, "pixabay": 1, "openverse": 2, "wikimedia": 3}
        unique_results.sort(key=lambda r: source_priority.get(r.source, 99))

        return unique_results[:count]

    async def _search_backend(
        self,
        backend: Any,
        query: str,
        count: int,
        orientation: str,
        license_type: str,
    ) -> list[ImageResult]:
        """搜索单个后端"""
        try:
            return await backend.search(query, count, orientation, license_type)
        except Exception as e:
            _logger.warning("Backend %s failed: %s", backend.name, e)
            return []

    def get_available_backends(self) -> list[str]:
        """获取可用后端列表"""
        return [b.name for b in self.backends]


# 全局单例
_image_search_service: ImageSearchService | None = None


def get_image_search_service() -> ImageSearchService:
    """获取图片搜索服务单例"""
    global _image_search_service
    if _image_search_service is None:
        _image_search_service = ImageSearchService()
    return _image_search_service
