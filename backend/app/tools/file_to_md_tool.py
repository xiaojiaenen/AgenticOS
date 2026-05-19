from markitdown import MarkItDown
from wuwei.tools import ToolRegistry


def register_file_to_md_tool(registry: ToolRegistry) -> None:
    @registry.tool(display_name="文件转Markdown")
    async def file_to_md(path: str) -> str:
        """将文件转换为 Markdown 文本供阅读，支持 .docx/.pdf/.txt/.md/.csv/.xlsx/.html 等常见格式。

        参数:
          path: 文件的绝对路径

        返回文件的 Markdown 文本内容。不要对 .pptx 文件使用此工具——应使用 convert_pptx_to_svg。
        """
        try:
            md_converter = MarkItDown()
            result = md_converter.convert(path)
        except Exception as e:
            return f"文件转换失败：{e}"

        if result is None or not result.text_content.strip():
            return "转换失败，该文件无法转为文本"

        return result.text_content
