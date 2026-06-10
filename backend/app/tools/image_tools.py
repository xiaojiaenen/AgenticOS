"""图片搜索工具

提供图片搜索和图片信息获取功能，供 PPT 生成时使用。
"""

from __future__ import annotations

import logging

from wuwei.tools import ToolRegistry

from app.services.ppt.image_search import get_image_search_service

_logger = logging.getLogger("tools.image")


def register_image_tools(registry: ToolRegistry) -> None:
    """注册图片相关工具"""

    @registry.tool(display_name="搜索网络图片")
    async def search_images(
        query: str,
        count: int = 3,
        license: str = "cc-by",
        orientation: str = "landscape",
    ) -> str:
        """搜索免费商用图片，返回 URL 和许可证信息。

        参数:
            query: 搜索关键词（英文效果更好，如 "business meeting", "technology abstract"）
            count: 返回数量（1-10，建议 3-5）
            license: 许可证类型
                - cc0: 完全免费，无需署名（推荐）
                - cc-by: 需署名
                - cc-by-sa: 需相同方式共享
            orientation: 图片方向
                - landscape: 横版（适合 16:9 PPT）
                - portrait: 竖版
                - square: 方形

        返回: 图片 URL 列表，包含许可证和尺寸信息

        使用场景:
            - 封面背景图：orientation=landscape, count=3
            - 内容配图：orientation=landscape, count=5
            - 人物介绍：orientation=portrait, count=3
        """
        service = get_image_search_service()

        results = await service.search(
            query=query,
            count=count,
            orientation=orientation,
            license_type=license,
        )

        if not results:
            return f"未找到符合条件的图片。建议：\n- 尝试更简单的关键词（英文效果更好）\n- 放宽许可证限制（使用 cc-by）\n- 或使用用户提供的图片 URL"

        output_lines = [f"找到 {len(results)} 张图片：\n"]

        for i, img in enumerate(results, 1):
            output_lines.append(f"**{i}. {img.title or '无标题'}**")
            output_lines.append(f"   URL: {img.url}")
            output_lines.append(f"   尺寸: {img.width}x{img.height}")
            output_lines.append(f"   许可证: {img.license}")
            output_lines.append(f"   来源: {img.source}")
            output_lines.append(f"   署名: {img.attribution}")
            output_lines.append("")

        # 添加使用提示
        output_lines.append("---")
        output_lines.append("在 SVG 中使用图片：")
        output_lines.append('```xml')
        output_lines.append('<image href="{URL}" x="0" y="0" width="640" height="360"')
        output_lines.append('       preserveAspectRatio="xMidYMid slice"/>')
        output_lines.append('```')

        if any(img.license not in ("CC0", "Public Domain") for img in results):
            output_lines.append("\n⚠️ 部分图片需要署名，请在 PPT 最后一页注明图片来源。")

        return "\n".join(output_lines)

    @registry.tool(display_name="获取图片信息")
    async def get_image_info(url: str) -> str:
        """获取图片的元数据信息（尺寸、格式、是否可用）。

        参数:
            url: 图片 URL

        返回: 图片信息（尺寸、格式、文件大小等）
        """
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # HEAD 请求检查可用性
                head_response = await client.head(url, follow_redirects=True)

                if head_response.status_code != 200:
                    return f"图片不可用，HTTP 状态码: {head_response.status_code}"

                content_type = head_response.headers.get("content-type", "")
                content_length = head_response.headers.get("content-length")

                # 检查是否是图片
                if not content_type.startswith("image/"):
                    return f"URL 不是图片，Content-Type: {content_type}"

                # 下载前 1KB 检测尺寸
                range_response = await client.get(
                    url,
                    headers={"Range": "bytes=0-1023"},
                    follow_redirects=True,
                )

                info_lines = [
                    f"图片信息：",
                    f"- 格式: {content_type}",
                    f"- 大小: {int(content_length) / 1024:.1f} KB" if content_length else "- 大小: 未知",
                    f"- URL: {url}",
                ]

                # 尝试从 content-type 推断格式
                format_map = {
                    "image/jpeg": "JPEG",
                    "image/png": "PNG",
                    "image/gif": "GIF",
                    "image/webp": "WebP",
                    "image/svg+xml": "SVG",
                }
                fmt = format_map.get(content_type, content_type)
                info_lines.insert(1, f"- 格式: {fmt}")

                return "\n".join(info_lines)

        except httpx.TimeoutException:
            return "获取图片信息超时，请检查 URL 是否可访问"
        except Exception as e:
            return f"获取图片信息失败: {str(e)}"
