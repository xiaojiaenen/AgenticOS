"""
文档解析器

使用 markitdown 统一解析多种文档格式（PDF、Word、Markdown、HTML、Excel、PPTX 等）。
markitdown 是微软维护的库，已作为项目依赖存在（file_to_md_tool 在用）。
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Section:
    """章节结构"""
    level: int  # 标题级别 (1-6)
    title: str
    content: str
    start_offset: int
    end_offset: int


@dataclass
class ParsedDocument:
    """解析后的文档结构"""
    text: str  # 纯文本内容（Markdown 格式）
    sections: list[Section] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    content_hash: str = ""  # SHA256 哈希

    def __post_init__(self):
        if not self.content_hash and self.text:
            self.content_hash = hashlib.sha256(self.text.encode()).hexdigest()


class DocumentParser:
    """多格式文档解析器，基于 markitdown"""

    SUPPORTED_EXTENSIONS = {
        "pdf", "docx", "doc", "md", "markdown", "html", "htm",
        "txt", "csv", "xlsx", "xls", "pptx", "json", "xml",
    }

    def parse_sync(self, file_path: str, file_type: Optional[str] = None) -> ParsedDocument:
        """
        同步解析文档，返回结构化的 ParsedDocument

        Args:
            file_path: 文件路径
            file_type: 文件类型（可选，自动从扩展名推断）

        Returns:
            ParsedDocument: 解析后的文档结构
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # 推断文件类型
        if file_type is None:
            file_type = path.suffix.lstrip(".").lower()

        if file_type not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {file_type}")

        logger.info(f"Parsing document with markitdown: {file_path} (type: {file_type})")

        try:
            from markitdown import MarkItDown

            converter = MarkItDown()
            result = converter.convert(str(path))

            if result is None or not result.text_content.strip():
                raise ValueError("markitdown returned empty content")

            text = result.text_content

            # 提取元数据
            metadata = {
                "file_path": str(path),
                "file_type": file_type,
                "file_size": path.stat().st_size,
                "file_name": path.name,
            }

            # 提取章节结构
            sections = self._extract_sections(text)

            # 提取标题
            title = self._extract_title(text)
            if title:
                metadata["title"] = title

            return ParsedDocument(
                text=text,
                sections=sections,
                metadata=metadata,
            )

        except ImportError:
            raise ImportError(
                "markitdown is required for document parsing. "
                "Install with: pip install markitdown[all]"
            )
        except Exception as e:
            logger.error(f"Failed to parse document {file_path}: {e}")
            raise

    def _extract_sections(self, text: str) -> list[Section]:
        """从 Markdown 文本中提取章节结构"""
        sections = []
        lines = text.split("\n")
        current_section = None
        current_content = []
        offset = 0

        for line in lines:
            # 检测 Markdown 标题
            match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if match:
                # 保存上一个章节
                if current_section:
                    current_section.content = "\n".join(current_content)
                    current_section.end_offset = offset
                    sections.append(current_section)
                    current_content = []

                level = len(match.group(1))
                title = match.group(2).strip()
                current_section = Section(
                    level=level,
                    title=title,
                    content="",
                    start_offset=offset,
                    end_offset=offset,
                )
            elif current_section:
                current_content.append(line)

            offset += len(line) + 1

        # 保存最后一个章节
        if current_section:
            current_section.content = "\n".join(current_content)
            current_section.end_offset = offset
            sections.append(current_section)

        return sections

    def _extract_title(self, text: str) -> str:
        """从 Markdown 文本中提取标题"""
        # 尝试提取第一个 # 标题
        match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if match:
            return match.group(1).strip()

        # 取第一行非空文本
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                return line[:100]  # 限制长度

        return ""
