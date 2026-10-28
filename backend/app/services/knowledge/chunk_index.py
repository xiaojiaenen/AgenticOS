"""段级切片的落库与向量化。

调用方（编译管线、重建索引）只关心「这一页的切片要不要重做」，这里负责
切块、删旧、写新、批量向量化四件事。

事务边界：本模块 **不提交**。切块与删除必须在调用方的事务里完成，
embedding 是网络调用，放在事务外（先算向量再 add），避免长时间持有行锁。
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import KBChunkModel, KBWikiPageModel
from app.services.knowledge.chunker import chunk_embedding_text, chunk_markdown
from app.services.knowledge.embedder import get_knowledge_embedder, pack_vector

logger = logging.getLogger("knowledge.chunks")


def rebuild_page_chunks(
    db: Session,
    page: KBWikiPageModel,
    *,
    embed: bool = True,
) -> dict[str, int]:
    """重建单页切片。

    Args:
        db: 会话（不提交）
        page: 目标页面
        embed: 是否同时写段向量（向量未启用时自动跳过）

    Returns:
        {"chunks": 段数, "embedded": 成功向量化的段数}
    """
    settings = get_settings()
    chunks = chunk_markdown(
        page.content,
        max_chars=settings.knowledge_chunk_size_chars,
        overlap=settings.knowledge_chunk_overlap_chars,
        min_chars=settings.knowledge_chunk_min_chars,
        max_chunks=settings.knowledge_max_chunks_per_page,
    )

    # 先删旧段：重建是「整体替换」而不是增量补，避免残留旧切片
    # 把过期内容继续暴露在召回里
    db.execute(delete(KBChunkModel).where(KBChunkModel.page_id == page.id))
    if not chunks:
        return {"chunks": 0, "embedded": 0}

    rows = [
        KBChunkModel(
            page_id=page.id,
            knowledge_base_id=page.knowledge_base_id,
            chunk_index=chunk.index,
            heading=chunk.heading,
            content=chunk.text,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
        )
        for chunk in chunks
    ]

    embedded = 0
    if embed:
        embedder = get_knowledge_embedder()
        if embedder.is_enabled():
            try:
                texts = [
                    chunk_embedding_text(page.title, chunk.heading, chunk.text)
                    for chunk in chunks
                ]
                vectors = embedder.embed_batch(texts)
                for row, vector in zip(rows, vectors):
                    if vector is None:
                        continue
                    row.embedding = pack_vector(vector)
                    embedded += 1
            except Exception as exc:  # noqa: BLE001 —— 向量化失败不得让切片落库失败
                logger.warning("段向量化失败 page=%s（该页退化为页级向量）: %s", page.id, exc)

    db.add_all(rows)
    db.flush()
    return {"chunks": len(rows), "embedded": embedded}


def delete_page_chunks(db: Session, page_ids: Iterable[int]) -> int:
    """删除若干页的切片，返回删除的页数（不提交）。"""
    ids = [int(i) for i in page_ids]
    if not ids:
        return 0
    db.execute(delete(KBChunkModel).where(KBChunkModel.page_id.in_(ids)))
    return len(ids)


def delete_kb_chunks(db: Session, knowledge_base_id: int) -> None:
    """删除整个知识库的切片（不提交）。"""
    db.execute(delete(KBChunkModel).where(KBChunkModel.knowledge_base_id == knowledge_base_id))


def chunk_stats(db: Session, knowledge_base_id: int) -> dict[str, int]:
    """诊断用：库内切片总数与已向量化段数。"""
    from sqlalchemy import func, select

    total = db.scalar(
        select(func.count(KBChunkModel.id)).where(
            KBChunkModel.knowledge_base_id == knowledge_base_id
        )
    )
    embedded = db.scalar(
        select(func.count(KBChunkModel.id)).where(
            KBChunkModel.knowledge_base_id == knowledge_base_id,
            KBChunkModel.embedding.isnot(None),
        )
    )
    return {"chunks": int(total or 0), "embedded": int(embedded or 0)}
