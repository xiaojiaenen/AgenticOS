"""
Knowledge Base Service Module

提供知识库系统的核心功能：
- 文档解析（PDF、Word、Markdown、HTML）
- Wiki 编译（LLM 驱动的知识提取和页面生成）
- 检索服务（BM25 + 向量 + 知识图谱）
- 编译管线编排
"""

from .document_parser import DocumentParser, ParsedDocument
from .wiki_compiler import WikiCompiler, AnalysisResult, WikiPageDraft
from .retrieval import KnowledgeRetrieval, SearchResult
from .ingest_pipeline import IngestPipeline

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "WikiCompiler",
    "AnalysisResult",
    "WikiPageDraft",
    "KnowledgeRetrieval",
    "SearchResult",
    "IngestPipeline",
]
