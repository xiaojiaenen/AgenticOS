"""
资源管理存储
完整对标 html-video 原版 AssetStore
Content-addressed 资源存储，按项目隔离
"""

import hashlib
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Optional

from .types import Asset, AssetType, AssetMetadata
from .errors import HtmlVideoError, ErrorCode


# 扩展名到 MIME 类型和 AssetType 的映射
MIME_MAP: dict[str, tuple[str, AssetType]] = {
    # 图片
    ".jpg": ("image/jpeg", AssetType.IMAGE),
    ".jpeg": ("image/jpeg", AssetType.IMAGE),
    ".png": ("image/png", AssetType.IMAGE),
    ".gif": ("image/gif", AssetType.IMAGE),
    ".webp": ("image/webp", AssetType.IMAGE),
    ".svg": ("image/svg+xml", AssetType.IMAGE),
    ".avif": ("image/avif", AssetType.IMAGE),
    # 音频
    ".mp3": ("audio/mpeg", AssetType.AUDIO),
    ".wav": ("audio/wav", AssetType.AUDIO),
    ".ogg": ("audio/ogg", AssetType.AUDIO),
    ".aac": ("audio/aac", AssetType.AUDIO),
    ".flac": ("audio/flac", AssetType.AUDIO),
    ".m4a": ("audio/mp4", AssetType.AUDIO),
    # 视频
    ".mp4": ("video/mp4", AssetType.VIDEO),
    ".webm": ("video/webm", AssetType.VIDEO),
    ".mov": ("video/quicktime", AssetType.VIDEO),
    ".avi": ("video/x-msvideo", AssetType.VIDEO),
    # 数据
    ".json": ("application/json", AssetType.DATA),
    ".csv": ("text/csv", AssetType.DATA),
    ".xml": ("application/xml", AssetType.DATA),
    # 文本
    ".txt": ("text/plain", AssetType.TEXT),
    ".md": ("text/markdown", AssetType.TEXT),
    ".html": ("text/html", AssetType.TEXT),
    ".css": ("text/css", AssetType.TEXT),
    ".js": ("application/javascript", AssetType.TEXT),
}


class AssetStore:
    """Content-addressed 资源存储，按项目隔离"""

    def __init__(self, project_root: str):
        self._project_root = Path(project_root)
        self._projects_dir = self._project_root / ".html-video" / "projects"

    async def add_file_asset(
        self,
        project_id: str,
        source_path: str,
        user_tags: Optional[list[str]] = None,
        user_caption: Optional[str] = None,
    ) -> Asset:
        """
        1. 计算文件 SHA1 作为 ID
        2. 猜测 MIME 类型（按扩展名映射）
        3. 复制到 assets/{id}{ext}（已存在则跳过）
        4. 返回 Asset
        """
        source = Path(source_path)
        if not source.exists():
            raise HtmlVideoError(
                code=ErrorCode.ASSET_NOT_FOUND,
                message=f"Source file not found: {source_path}",
                context={"source_path": source_path},
            )

        # 计算 SHA1
        sha1 = hashlib.sha1()
        with open(source, "rb") as f:
            while chunk := f.read(8192):
                sha1.update(chunk)
        asset_id = sha1.hexdigest()

        # 猜测 MIME 类型
        ext = source.suffix.lower()
        mime_info = guess_mime(source_path)
        mime_type = mime_info.get("mime_type", "application/octet-stream")
        asset_type = mime_info.get("type", AssetType.IMAGE)

        # 目标路径
        assets_dir = self._projects_dir / project_id / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest_path = assets_dir / f"{asset_id}{ext}"

        # 如果不存在则复制
        if not dest_path.exists():
            shutil.copy2(source, dest_path)

        # 获取文件大小
        size_bytes = dest_path.stat().st_size

        return Asset(
            id=asset_id,
            type=asset_type,
            path=str(dest_path),
            metadata=AssetMetadata(
                filename=source.name,
                mime_type=mime_type,
                size_bytes=size_bytes,
                user_caption=user_caption,
            ),
            user_tags=user_tags or [],
        )

    async def add_inline_asset(
        self,
        project_id: str,
        content: str,
        type: str,
        user_tags: Optional[list[str]] = None,
        user_caption: Optional[str] = None,
    ) -> Asset:
        """内联文本/数据资源，SHA1(content) 作为 ID"""
        # 计算 SHA1
        asset_id = hashlib.sha1(content.encode("utf-8")).hexdigest()

        # 确定资源类型
        asset_type = AssetType(type) if type in [e.value for e in AssetType] else AssetType.TEXT

        return Asset(
            id=asset_id,
            type=asset_type,
            content=content,
            metadata=AssetMetadata(
                user_caption=user_caption,
                size_bytes=len(content.encode("utf-8")),
            ),
            user_tags=user_tags or [],
        )

    async def add_buffer_asset(
        self,
        project_id: str,
        data: bytes,
        ext: str,
        user_tags: Optional[list[str]] = None,
        user_caption: Optional[str] = None,
    ) -> Asset:
        """原始字节资源（如 MiniMax 生成的 MP3）"""
        # 计算 SHA1
        asset_id = hashlib.sha1(data).hexdigest()

        # 猜测 MIME 类型
        mime_info = guess_mime(f"file{ext}")
        mime_type = mime_info.get("mime_type", "application/octet-stream")
        asset_type = mime_info.get("type", AssetType.DATA)

        # 保存文件
        assets_dir = self._projects_dir / project_id / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest_path = assets_dir / f"{asset_id}{ext}"

        if not dest_path.exists():
            with open(dest_path, "wb") as f:
                f.write(data)

        return Asset(
            id=asset_id,
            type=asset_type,
            path=str(dest_path),
            metadata=AssetMetadata(
                mime_type=mime_type,
                size_bytes=len(data),
                user_caption=user_caption,
            ),
            user_tags=user_tags or [],
        )

    def get_asset_path(self, project_id: str, asset_id: str) -> Optional[str]:
        """获取资源文件路径"""
        assets_dir = self._projects_dir / project_id / "assets"
        if not assets_dir.exists():
            return None

        # 查找匹配的文件
        for asset_file in assets_dir.iterdir():
            if asset_file.stem == asset_id:
                return str(asset_file)
        return None


def guess_mime(file_path: str) -> dict:
    """按扩展名猜测 MIME 类型和 AssetType"""
    ext = Path(file_path).suffix.lower()

    if ext in MIME_MAP:
        mime_type, asset_type = MIME_MAP[ext]
        return {"mime_type": mime_type, "type": asset_type}

    # 使用 mimetypes 模块猜测
    mime_type, _ = mimetypes.guess_type(file_path)
    return {
        "mime_type": mime_type or "application/octet-stream",
        "type": AssetType.DATA,
    }
