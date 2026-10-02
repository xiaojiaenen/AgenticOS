"""摘要检索（Summary Auto-Gen）测试：摘要/标题命中也能召回页面。"""

from __future__ import annotations

import pytest

from app.db.models import KnowledgeBaseModel, KBWikiPageModel
from app.db.session import create_db_session
from app.services.knowledge.retrieval import KnowledgeRetrieval


@pytest.fixture
def kb_with_pages():
    """构造一个知识库：正文不含关键词，但标题/摘要含——用于验证扩展召回。

    作用域为 session 级复用：同一 slug 重复插入会触发唯一约束。
    """
    with create_db_session() as db:
        existing = db.query(KnowledgeBaseModel).filter(
            KnowledgeBaseModel.slug == "summary-recall-test"
        ).first()
        if existing is not None:
            db.rollback()
            return int(existing.id)
        kb = KnowledgeBaseModel(
            owner_id=1,
            name="摘要检索测试库",
            slug="summary-recall-test",
            description="验证标题/摘要参与召回",
            scope="org",
            visibility="public",
            is_active=True,
        )
        db.add(kb)
        db.flush()

        # 页面 A：正文没有关键词，摘要里有
        db.add(KBWikiPageModel(
            knowledge_base_id=kb.id,
            title="页面甲",
            slug="page-a",
            page_type="concept",
            content="本文介绍一些无关内容。",
            summary="差旅报销的电子发票合规要求",
            is_active=True,
        ))
        # 页面 B：正文里有关键词（基准）
        db.add(KBWikiPageModel(
            knowledge_base_id=kb.id,
            title="页面乙",
            slug="page-b",
            page_type="concept",
            content="差旅报销需要提供电子发票。",
            summary=None,
            is_active=True,
        ))
        # 页面 C：正文/摘要都不含，应不被召回
        db.add(KBWikiPageModel(
            knowledge_base_id=kb.id,
            title="页面丙",
            slug="page-c",
            page_type="concept",
            content="完全不相干的文本。",
            summary="也不相干",
            is_active=True,
        ))
        db.commit()
        return kb.id


class TestSummaryRecall:
    def test_summary_hit_is_recalled(self, kb_with_pages):
        """正文不含关键词、仅摘要命中的页面应被召回。"""
        with create_db_session() as db:
            results = KnowledgeRetrieval(db).search(
                query="电子发票",
                knowledge_base_ids=[kb_with_pages],
                max_results=10,
                is_admin=True,
            )
        titles = [r.title for r in results]
        assert "页面甲" in titles, "仅摘要命中的页面未被召回"

    def test_unrelated_page_not_recalled(self, kb_with_pages):
        with create_db_session() as db:
            results = KnowledgeRetrieval(db).search(
                query="电子发票",
                knowledge_base_ids=[kb_with_pages],
                max_results=10,
                is_admin=True,
            )
        titles = [r.title for r in results]
        assert "页面丙" not in titles

    def test_empty_summary_is_safe(self, kb_with_pages):
        """摘要为 NULL 的历史页面不应导致检索报错。"""
        with create_db_session() as db:
            results = KnowledgeRetrieval(db).search(
                query="差旅报销",
                knowledge_base_ids=[kb_with_pages],
                max_results=10,
                is_admin=True,
            )
        assert results, "正文命中仍应返回结果"