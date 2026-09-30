"""
编译管线编排

协调文档解析、Wiki 编译、冲突检测、存储的完整流程。
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import (
    KBDocumentModel,
    KBWikiPageModel,
    KBWikiLinkModel,
    KBReviewItemModel,
    KnowledgeBaseModel,
)
from app.db.session import SessionLocal

from .document_parser import DocumentParser
from .wiki_compiler import WikiCompiler, WikiPageDraft

logger = logging.getLogger(__name__)


class IngestPipeline:
    """文档编译管线"""

    def __init__(self, llm_gateway=None):
        """
        Args:
            llm_gateway: wuwei LLMGateway 实例（用于 Wiki 编译）
        """
        self.parser = DocumentParser()
        self.llm_gateway = llm_gateway

    def process_document(
        self,
        document_id: int,
        knowledge_base_id: int,
    ) -> dict:
        """
        处理单个文档的完整编译流程

        Args:
            document_id: 文档 ID
            knowledge_base_id: 知识库 ID

        Returns:
            dict: 处理结果 {"success": bool, "pages_created": int, "errors": []}
        """
        result = {
            "success": False,
            "pages_created": 0,
            "pages_updated": 0,
            "conflicts_found": 0,
            "errors": [],
        }

        db = SessionLocal()
        try:
            # 1. 加载文档和知识库
            document = self._load_document(db, document_id)
            if not document:
                result["errors"].append(f"Document not found: {document_id}")
                return result

            knowledge_base = self._load_knowledge_base(db, knowledge_base_id)
            if not knowledge_base:
                result["errors"].append(f"Knowledge base not found: {knowledge_base_id}")
                return result

            # 2. 更新文档状态为 compiling
            self._update_document_status(db, document_id, "compiling")

            # 3. 解析文档
            logger.info(f"Parsing document: {document.file_path}")
            parsed = self.parser.parse_sync(document.file_path, document.file_type)

            # 4. 增量检查
            if document.content_hash == parsed.content_hash:
                logger.info(f"Document unchanged, skipping: {document_id}")
                self._update_document_status(db, document_id, "compiled")
                result["success"] = True
                return result

            # 5. Wiki 编译（始终走编译器；analyze_sync 在无 LLM 时降级为启发式）
            compiler = WikiCompiler(self.llm_gateway, knowledge_base.purpose)

            # 5.1 分析
            logger.info("Analyzing document...")
            analysis = compiler.analyze_sync(parsed)

            # 5.2 生成页面
            logger.info("Generating wiki pages...")
            page_drafts = compiler.generate_pages_sync(analysis, parsed, document_id)

            # 5.3 冲突检测
            logger.info("Detecting conflicts...")
            existing_pages = self._load_existing_pages(db, knowledge_base_id)
            conflicts = compiler.detect_conflicts_sync(page_drafts, existing_pages)
            result["conflicts_found"] = len(conflicts)

            # 5.4 创建审核任务（如果有冲突）
            for conflict in conflicts:
                self._create_review_item(
                    db,
                    knowledge_base_id,
                    conflict,
                    document_id,
                )

            # 5.5 保存页面
            logger.info("Saving wiki pages...")
            saved_by_title: dict[str, KBWikiPageModel] = {}
            for draft in page_drafts:
                if draft.action == "skip":
                    continue
                page = self._save_wiki_page(db, knowledge_base_id, draft, document_id)
                if page is not None:
                    saved_by_title[page.title] = page
                    if draft.action == "merge":
                        result["pages_updated"] += 1
                    else:
                        result["pages_created"] += 1

            # 5.6 写入 wikilinks（KBWikiLinkModel）
            self._persist_wikilinks(db, saved_by_title, page_drafts, knowledge_base_id)

            # 6. 更新文档状态
            document.content_hash = parsed.content_hash
            document.status = "compiled"
            document.compiled_at = datetime.utcnow()
            db.commit()

            result["success"] = True
            logger.info(f"Document processed successfully: {document_id}")

        except Exception as e:
            logger.error(f"Pipeline failed for document {document_id}: {e}")
            result["errors"].append(str(e))
            self._update_document_status(db, document_id, "failed")
            db.commit()
        finally:
            db.close()

        return result

    def _load_document(self, db: Session, document_id: int) -> Optional[KBDocumentModel]:
        """加载文档"""
        return db.get(KBDocumentModel, document_id)

    def _load_knowledge_base(self, db: Session, kb_id: int) -> Optional[KnowledgeBaseModel]:
        """加载知识库"""
        return db.get(KnowledgeBaseModel, kb_id)

    def _update_document_status(self, db: Session, document_id: int, status: str):
        """更新文档状态"""
        stmt = update(KBDocumentModel).where(
            KBDocumentModel.id == document_id
        ).values(status=status)
        db.execute(stmt)
        db.commit()

    def _load_existing_pages(self, db: Session, kb_id: int) -> list[dict]:
        """加载已有页面"""
        stmt = select(KBWikiPageModel).where(
            KBWikiPageModel.knowledge_base_id == kb_id,
            KBWikiPageModel.is_active.is_(True),
        )
        result = db.execute(stmt)
        pages = result.scalars().all()
        return [
            {
                "id": p.id,
                "title": p.title,
                "content": p.content,
            }
            for p in pages
        ]

    def _save_wiki_page(
        self,
        db: Session,
        kb_id: int,
        draft: WikiPageDraft,
        document_id: int,
    ) -> Optional[KBWikiPageModel]:
        """保存 Wiki 页面"""
        slug = self._slugify(draft.title)

        # 检查是否已存在
        stmt = select(KBWikiPageModel).where(
            KBWikiPageModel.knowledge_base_id == kb_id,
            KBWikiPageModel.slug == slug,
        )
        result = db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and draft.action == "merge":
            # 更新已有页面
            existing.content = draft.content
            existing.frontmatter_json = json.dumps(draft.frontmatter, ensure_ascii=False)
            # 追加来源
            try:
                sources = json.loads(existing.sources_json) if existing.sources_json else []
            except json.JSONDecodeError:
                sources = []
            source_ref = f"kb_document:{document_id}"
            if source_ref not in sources:
                sources.append(source_ref)
            existing.sources_json = json.dumps(sources)
            db.flush()
            return existing
        else:
            # 创建新页面（slug 冲突时合并到已有）
            if existing:
                existing.content = draft.content
                existing.frontmatter_json = json.dumps(draft.frontmatter, ensure_ascii=False)
                try:
                    sources = json.loads(existing.sources_json) if existing.sources_json else []
                except json.JSONDecodeError:
                    sources = []
                source_ref = f"kb_document:{document_id}"
                if source_ref not in sources:
                    sources.append(source_ref)
                existing.sources_json = json.dumps(sources)
                db.flush()
                return existing

            page = KBWikiPageModel(
                knowledge_base_id=kb_id,
                title=draft.title,
                slug=slug,
                page_type=draft.page_type,
                content=draft.content,
                frontmatter_json=json.dumps(draft.frontmatter, ensure_ascii=False),
                sources_json=json.dumps(draft.sources),
                authority_level="L1",  # 默认自动编译
            )
            db.add(page)
            db.flush()
            return page

    def _persist_wikilinks(
        self,
        db: Session,
        saved_by_title: dict[str, KBWikiPageModel],
        page_drafts: list[WikiPageDraft],
        kb_id: int,
    ) -> None:
        """将草稿 wikilinks 写入 KBWikiLinkModel（含同 KB 内已有页面）。"""
        # 标题 → 页面（本批 + 同 KB 已有活跃页）
        title_to_page: dict[str, KBWikiPageModel] = dict(saved_by_title)
        existing = db.execute(
            select(KBWikiPageModel).where(
                KBWikiPageModel.knowledge_base_id == kb_id,
                KBWikiPageModel.is_active.is_(True),
            )
        ).scalars().all()
        for p in existing:
            title_to_page.setdefault(p.title, p)

        created_pairs: set[tuple[int, int]] = set()

        for draft in page_drafts:
            if draft.action == "skip":
                continue
            source = title_to_page.get(draft.title)
            if source is None:
                continue

            targets = list(draft.wikilinks)
            # 也从正文中提取 [[Title]] 形式
            targets.extend(re_wikilinks(draft.content))

            for link_title in targets:
                if not link_title or link_title == draft.title:
                    continue
                target = title_to_page.get(link_title)
                if target is None:
                    continue
                pair = (source.id, target.id)
                if source.id == target.id or pair in created_pairs:
                    continue
                created_pairs.add(pair)
                # 避免重复边
                exists = db.execute(
                    select(KBWikiLinkModel).where(
                        KBWikiLinkModel.source_page_id == source.id,
                        KBWikiLinkModel.target_page_id == target.id,
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                db.add(KBWikiLinkModel(
                    source_page_id=source.id,
                    target_page_id=target.id,
                    link_type="reference",
                    context=draft.title,
                ))

        if created_pairs:
            db.flush()
            logger.info(f"Persisted {len(created_pairs)} wikilinks for kb={kb_id}")

    def _create_review_item(
        self,
        db: Session,
        kb_id: int,
        conflict,
        document_id: int,
    ):
        """创建审核任务"""
        review = KBReviewItemModel(
            knowledge_base_id=kb_id,
            review_type="conflict_resolution",
            title=f"内容冲突: {conflict.existing_page_title}",
            description=f"新内容与已有页面 '{conflict.existing_page_title}' 存在矛盾: {conflict.nature}",
            options_json=json.dumps([
                {"action": "adopt_new", "label": "采纳新内容"},
                {"action": "keep_existing", "label": "保留已有内容"},
                {"action": "merge", "label": "合并两者"},
                {"action": "skip", "label": "跳过"},
            ]),
            related_document_ids_json=json.dumps([document_id]),
            related_page_ids_json=json.dumps([conflict.existing_page_id]) if conflict.existing_page_id else "[]",
        )
        db.add(review)
        db.flush()

    def _slugify(self, text: str) -> str:
        """生成 URL 友好的 slug"""
        import re
        text = re.sub(r"[^\w\s一-鿿-]", "", text)
        text = re.sub(r"\s+", "-", text.strip())
        return text.lower()[:100]


def re_wikilinks(content: str) -> list[str]:
    """从 Markdown 中提取 [[Title]] 链接标题。"""
    import re
    return re.findall(r"\[\[([^\]]+)\]\]", content or "")


def process_document_ingest(
    document_id: int,
    knowledge_base_id: int,
    llm_gateway=None,
) -> dict:
    """
    文档编译便捷函数
    """
    pipeline = IngestPipeline(llm_gateway)
    return pipeline.process_document(document_id, knowledge_base_id)
