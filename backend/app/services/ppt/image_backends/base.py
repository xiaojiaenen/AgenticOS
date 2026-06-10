"""图片搜索后端基类"""

from __future__ import annotations

from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class ImageResult:
    """图片搜索结果"""
    url: str
    thumbnail_url: str
    source: str           # openverse/wikimedia/pexels/pixabay
    license: str          # CC0/CC BY/CC BY-SA
    license_url: str
    attribution: str      # 署名信息
    width: int
    height: int
    title: str = ""


class ImageSearchBackend(ABC):
    """图片搜索后端基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """后端名称"""
        ...

    @abstractmethod
    async def search(
        self,
        query: str,
        count: int = 5,
        orientation: str = "landscape",
        license_type: str = "cc-by",
    ) -> list[ImageResult]:
        """搜索图片

        参数:
            query: 搜索关键词
            count: 返回数量
            orientation: 方向 (landscape/portrait/square)
            license_type: 许可证类型 (cc0/cc-by/cc-by-sa)

        返回:
            图片结果列表
        """
        ...

    def _match_orientation(self, width: int, height: int, orientation: str) -> bool:
        """检查图片方向是否匹配"""
        if width <= 0 or height <= 0:
            return True  # 无法判断时认为匹配

        ratio = width / height

        if orientation == "landscape":
            return ratio > 1.1
        elif orientation == "portrait":
            return ratio < 0.9
        elif orientation == "square":
            return 0.9 <= ratio <= 1.1

        return True

    def _normalize_license(self, raw_license: str) -> str:
        """标准化许可证名称"""
        raw = raw_license.upper().replace("-", " ").replace("_", " ")

        if "CC0" in raw or "PUBLIC DOMAIN" in raw:
            return "CC0"
        elif "BY-SA" in raw:
            return "CC BY-SA"
        elif "BY" in raw:
            return "CC BY"
        elif "PUBLIC DOMAIN" in raw:
            return "Public Domain"

        return raw_license
