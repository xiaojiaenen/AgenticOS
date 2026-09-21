import asyncio

from markitdown import MarkItDown
from wuwei.tools import ToolRegistry


def _convert_sync(path: str) -> str:
    """同步执行 markitdown 转换（在线程池中运行）"""
    md_converter = MarkItDown()
    result = md_converter.convert(path)
    if result is None or not result.text_content.strip():
        return "转换失败，该文件无法转为文本"
    return result.text_content


def register_file_to_md_tool(registry: ToolRegistry) -> None:
    @registry.tool(display_name="文件转Markdown")
    async def file_to_md(path: str) -> str:
        """将文件转换为 Markdown 文本供阅读，支持 .docx/.pdf/.txt/.md/.csv/.xlsx/.html 等常见格式。

        参数:
          path: 文件的绝对路径

        返回文件的 Markdown 文本内容。不要对 .pptx 文件使用此工具——应使用 convert_pptx_to_svg。
        """
        try:
            # 在线程池中执行同步转换，防止阻塞事件循环
            return await asyncio.to_thread(_convert_sync, path)
        except Exception as e:
            return f"文件转换失败：{e}"
