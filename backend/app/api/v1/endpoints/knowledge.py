"""
知识库 API 端点

提供知识库管理、文档上传、Wiki 页面浏览、检索等功能。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, delete, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, get_db
from app.db.models import (
    UserModel,
    KnowledgeBaseModel,
    KBDocumentModel,
    KBWikiPageModel,
    KBWikiLinkModel,
    KBIngestTaskModel,
    KBReviewItemModel,
)
from app.core.data_path import DATA_DIR

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: Optional[str] = Field(None, max_length=200)
    description: str = ""
    purpose: str = ""
    scope: str = Field("org", pattern="^(org|team|personal)$")
    visibility: str = Field("public", pattern="^(public|restricted|private)$")


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    purpose: Optional[str] = None
    visibility: Optional[str] = Field(None, pattern="^(public|restricted|private)$")
    is_active: Optional[bool] = None


class KnowledgeBaseResponse(BaseModel):
    id: int
    name: str
    slug: str
    description: str
    purpose: str
    scope: str
    visibility: str
    is_active: bool
    owner_id: int
    document_count: int = 0
    page_count: int = 0
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    file_type: str
    file_size: int
    status: str
    compiled_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime


class WikiPageResponse(BaseModel):
    id: int
    knowledge_base_id: int
    title: str
    slug: str
    page_type: str
    content: str
    sources: list[str]
    authority_level: str
    created_at: datetime
    updated_at: datetime


class SearchRequest(BaseModel):
    query: str
    knowledge_base_ids: Optional[list[int]] = None
    page_type: Optional[str] = None
    max_results: int = Field(10, ge=1, le=50)


class SearchResultItem(BaseModel):
    page_id: int
    title: str
    content: str
    page_type: str
    score: float
    sources: list[str]
    authority_level: str


# ---------------------------------------------------------------------------
# Knowledge Base CRUD
# ---------------------------------------------------------------------------


@router.get("/bases", response_model=list[KnowledgeBaseResponse])
def list_knowledge_bases(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出当前用户可见的知识库（visibility/scope 过滤，过滤后内存分页）。"""
    from app.services.knowledge.retrieval import can_view_knowledge_base

    is_admin = current_user.role == "admin"
    all_kbs = [
        kb for kb in db.execute(
            select(KnowledgeBaseModel).where(KnowledgeBaseModel.is_active.is_(True))
        ).scalars().all()
        if can_view_knowledge_base(kb, user_id=current_user.id, is_admin=is_admin)
    ][offset:offset + limit]

    if all_kbs:
        kb_ids = [kb.id for kb in all_kbs]
        # Batch count documents
        doc_counts = dict(db.execute(
            select(KBDocumentModel.knowledge_base_id, func.count(KBDocumentModel.id))
            .where(KBDocumentModel.knowledge_base_id.in_(kb_ids))
            .group_by(KBDocumentModel.knowledge_base_id)
        ).all())
        # Batch count pages
        page_counts = dict(db.execute(
            select(KBWikiPageModel.knowledge_base_id, func.count(KBWikiPageModel.id))
            .where(KBWikiPageModel.knowledge_base_id.in_(kb_ids), KBWikiPageModel.is_active.is_(True))
            .group_by(KBWikiPageModel.knowledge_base_id)
        ).all())
    else:
        doc_counts = {}
        page_counts = {}

    response = []
    for kb in all_kbs:
        response.append(KnowledgeBaseResponse(
            id=kb.id,
            name=kb.name,
            slug=kb.slug,
            description=kb.description,
            purpose=kb.purpose,
            scope=kb.scope,
            visibility=kb.visibility,
            is_active=kb.is_active,
            owner_id=kb.owner_id,
            document_count=doc_counts.get(kb.id, 0),
            page_count=page_counts.get(kb.id, 0),
            created_at=kb.created_at,
            updated_at=kb.updated_at,
        ))

    return response


@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    request: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    """创建知识库"""
    # 生成 slug
    slug = request.slug or request.name.lower().replace(" ", "-")
    slug = "".join(c for c in slug if c.isalnum() or c == "-")[:200]

    # 检查 slug 唯一性
    existing = db.execute(
        select(KnowledgeBaseModel).where(KnowledgeBaseModel.slug == slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slug already exists: {slug}",
        )

    kb = KnowledgeBaseModel(
        name=request.name,
        slug=slug,
        description=request.description,
        purpose=request.purpose,
        scope=request.scope,
        visibility=request.visibility,
        owner_id=current_user.id,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        slug=kb.slug,
        description=kb.description,
        purpose=kb.purpose,
        scope=kb.scope,
        visibility=kb.visibility,
        is_active=kb.is_active,
        owner_id=kb.owner_id,
        document_count=0,
        page_count=0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取知识库详情（private=owner/admin）。"""
    from app.services.knowledge.retrieval import can_view_knowledge_base

    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    is_admin = current_user.role == "admin"
    if not can_view_knowledge_base(kb, user_id=current_user.id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    doc_count = db.execute(
        select(func.count()).select_from(KBDocumentModel).where(
            KBDocumentModel.knowledge_base_id == kb.id
        )
    )
    page_count = db.execute(
        select(func.count()).select_from(KBWikiPageModel).where(
            KBWikiPageModel.knowledge_base_id == kb.id,
            KBWikiPageModel.is_active.is_(True),
        )
    )

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        slug=kb.slug,
        description=kb.description,
        purpose=kb.purpose,
        scope=kb.scope,
        visibility=kb.visibility,
        is_active=kb.is_active,
        owner_id=kb.owner_id,
        document_count=doc_count.scalar() or 0,
        page_count=page_count.scalar() or 0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.patch("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(
    kb_id: int,
    request: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    """更新知识库"""
    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    if request.name is not None:
        kb.name = request.name
    if request.description is not None:
        kb.description = request.description
    if request.purpose is not None:
        kb.purpose = request.purpose
    if request.visibility is not None:
        kb.visibility = request.visibility
    if request.is_active is not None:
        kb.is_active = request.is_active

    db.commit()
    db.refresh(kb)

    doc_count = db.execute(
        select(func.count()).select_from(KBDocumentModel).where(
            KBDocumentModel.knowledge_base_id == kb.id
        )
    )
    page_count = db.execute(
        select(func.count()).select_from(KBWikiPageModel).where(
            KBWikiPageModel.knowledge_base_id == kb.id,
            KBWikiPageModel.is_active.is_(True),
        )
    )

    return KnowledgeBaseResponse(
        id=kb.id,
        name=kb.name,
        slug=kb.slug,
        description=kb.description,
        purpose=kb.purpose,
        scope=kb.scope,
        visibility=kb.visibility,
        is_active=kb.is_active,
        owner_id=kb.owner_id,
        document_count=doc_count.scalar() or 0,
        page_count=page_count.scalar() or 0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.delete("/bases/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    """删除知识库"""
    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    # 删除相关数据
    db.execute(delete(KBWikiLinkModel).where(
        KBWikiLinkModel.source_page_id.in_(
            select(KBWikiPageModel.id).where(KBWikiPageModel.knowledge_base_id == kb_id)
        )
    ))
    db.execute(delete(KBWikiPageModel).where(KBWikiPageModel.knowledge_base_id == kb_id))
    db.execute(delete(KBDocumentModel).where(KBDocumentModel.knowledge_base_id == kb_id))
    db.execute(delete(KBIngestTaskModel).where(KBIngestTaskModel.knowledge_base_id == kb_id))
    db.execute(delete(KBReviewItemModel).where(KBReviewItemModel.knowledge_base_id == kb_id))
    db.delete(kb)
    db.commit()


# ---------------------------------------------------------------------------
# Document Management
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/documents", response_model=list[DocumentResponse])
def list_documents(
    kb_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出知识库中的文档"""
    from app.services.knowledge.retrieval import can_view_knowledge_base

    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    is_admin = current_user.role == "admin"
    if not can_view_knowledge_base(kb, user_id=current_user.id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    stmt = select(KBDocumentModel).where(
        KBDocumentModel.knowledge_base_id == kb_id
    ).order_by(KBDocumentModel.created_at.desc()).offset(offset).limit(limit)

    result = db.execute(stmt)
    documents = result.scalars().all()

    return [
        DocumentResponse(
            id=doc.id,
            knowledge_base_id=doc.knowledge_base_id,
            title=doc.title,
            file_type=doc.file_type,
            file_size=doc.file_size,
            status=doc.status,
            compiled_at=doc.compiled_at,
            error_message=doc.error_message,
            created_at=doc.created_at,
        )
        for doc in documents
    ]


@router.post("/bases/{kb_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """上传文档并提交编译任务到后台队列"""
    # 检查知识库
    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    # 检查文件类型
    allowed_types = {"pdf", "docx", "md", "markdown", "html", "htm", "txt"}
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}",
        )

    # 保存文件
    upload_dir = DATA_DIR / "knowledge" / str(kb_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_id = str(uuid.uuid4())[:8]
    file_name = f"{file_id}.{file_ext}"
    file_path = upload_dir / file_name

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 创建文档记录
    doc = KBDocumentModel(
        knowledge_base_id=kb_id,
        title=file.filename or file_name,
        file_path=str(file_path),
        file_type=file_ext,
        file_size=len(content),
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 提交编译任务到 ARQ 队列
    try:
        from app.services.task_queue import submit_document_compilation
        task_id = await submit_document_compilation(doc.id, kb_id)
        # 可以在这里返回 task_id，让前端轮询任务状态
    except Exception as e:
        # 如果 ARQ 不可用，回退到同步处理（to_thread 避免阻塞事件循环）
        import asyncio
        import logging
        logging.getLogger(__name__).warning(f"ARQ submission failed, falling back to sync: {e}")
        from app.services.knowledge.ingest_pipeline import process_document_ingest
        from app.services.task_queue import build_llm_gateway

        llm_gateway = build_llm_gateway()
        await asyncio.to_thread(process_document_ingest, doc.id, kb_id, llm_gateway)

    return DocumentResponse(
        id=doc.id,
        knowledge_base_id=doc.knowledge_base_id,
        title=doc.title,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        compiled_at=doc.compiled_at,
        error_message=doc.error_message,
        created_at=doc.created_at,
    )


@router.delete("/bases/{kb_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """删除文档：清理文件、Wiki 页面 sources 引用与图谱链接。"""
    doc = db.get(KBDocumentModel, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    source_ref = f"kb_document:{doc_id}"

    # 1) 找出引用该文档的 Wiki 页面
    pages = db.execute(
        select(KBWikiPageModel).where(
            KBWikiPageModel.knowledge_base_id == kb_id,
            KBWikiPageModel.is_active.is_(True),
        )
    ).scalars().all()

    removed_page_ids: list[int] = []
    for page in pages:
        try:
            sources = json.loads(page.sources_json) if page.sources_json else []
        except json.JSONDecodeError:
            sources = []
        if source_ref not in sources:
            continue
        sources = [s for s in sources if s != source_ref]
        if sources:
            page.sources_json = json.dumps(sources, ensure_ascii=False)
        else:
            # 仅由该文档生成 → 删除页面
            removed_page_ids.append(page.id)

    # 2) 删除失效页面及其图谱边
    if removed_page_ids:
        db.execute(delete(KBWikiLinkModel).where(
            or_(
                KBWikiLinkModel.source_page_id.in_(removed_page_ids),
                KBWikiLinkModel.target_page_id.in_(removed_page_ids),
            )
        ))
        for pid in removed_page_ids:
            page = db.get(KBWikiPageModel, pid)
            if page:
                db.delete(page)

    # 3) 删除物理文件
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()


# ---------------------------------------------------------------------------
# Wiki Pages
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/wiki/pages", response_model=list[WikiPageResponse])
def list_wiki_pages(
    kb_id: int,
    page_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出 Wiki 页面（先校验知识库 visibility/scope）。"""
    from app.services.knowledge.retrieval import can_view_knowledge_base

    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    is_admin = current_user.role == "admin"
    if not can_view_knowledge_base(kb, user_id=current_user.id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    conditions = [
        KBWikiPageModel.knowledge_base_id == kb_id,
        KBWikiPageModel.is_active.is_(True),
    ]
    if page_type:
        conditions.append(KBWikiPageModel.page_type == page_type)

    stmt = select(KBWikiPageModel).where(and_(*conditions)).order_by(KBWikiPageModel.title).offset(offset).limit(limit)
    result = db.execute(stmt)
    pages = result.scalars().all()

    return [
        WikiPageResponse(
            id=page.id,
            knowledge_base_id=page.knowledge_base_id,
            title=page.title,
            slug=page.slug,
            page_type=page.page_type,
            content=page.content,
            sources=json.loads(page.sources_json) if page.sources_json else [],
            authority_level=page.authority_level,
            created_at=page.created_at,
            updated_at=page.updated_at,
        )
        for page in pages
    ]


@router.get("/bases/{kb_id}/wiki/pages/{page_id}", response_model=WikiPageResponse)
def get_wiki_page(
    kb_id: int,
    page_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取 Wiki 页面详情（private=owner/admin）。"""
    from app.services.knowledge.retrieval import can_view_knowledge_base

    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    is_admin = current_user.role == "admin"
    if not can_view_knowledge_base(kb, user_id=current_user.id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    page = db.get(KBWikiPageModel, page_id)
    if not page or page.knowledge_base_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

    return WikiPageResponse(
        id=page.id,
        knowledge_base_id=page.knowledge_base_id,
        title=page.title,
        slug=page.slug,
        page_type=page.page_type,
        content=page.content,
        sources=json.loads(page.sources_json) if page.sources_json else [],
        authority_level=page.authority_level,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@router.post("/bases/{kb_id}/search", response_model=list[SearchResultItem])
def search_knowledge_base(
    kb_id: int,
    request: SearchRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """搜索知识库（按当前用户权限过滤 private/scope）。"""
    from app.services.knowledge.retrieval import KnowledgeRetrieval

    retrieval = KnowledgeRetrieval(db)
    results = retrieval.search(
        query=request.query,
        knowledge_base_ids=[kb_id],
        user_id=current_user.id,
        page_type=request.page_type,
        max_results=request.max_results,
        is_admin=current_user.role == "admin",
    )

    return [
        SearchResultItem(
            page_id=r.page_id,
            title=r.title,
            content=r.content[:500] + "..." if len(r.content) > 500 else r.content,
            page_type=r.page_type,
            score=r.score,
            sources=r.sources,
            authority_level=r.authority_level,
        )
        for r in results
    ]


# ---------------------------------------------------------------------------
# Review Items
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/reviews")
def list_review_items(
    kb_id: int,
    status_filter: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出审核任务"""
    from app.services.knowledge.retrieval import can_view_knowledge_base

    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")
    is_admin = current_user.role == "admin"
    if not can_view_knowledge_base(kb, user_id=current_user.id, is_admin=is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    conditions = [KBReviewItemModel.knowledge_base_id == kb_id]
    if status_filter:
        conditions.append(KBReviewItemModel.status == status_filter)

    stmt = select(KBReviewItemModel).where(and_(*conditions)).order_by(KBReviewItemModel.created_at.desc()).offset(offset).limit(limit)
    result = db.execute(stmt)
    items = result.scalars().all()

    return [
        {
            "id": item.id,
            "knowledge_base_id": item.knowledge_base_id,
            "review_type": item.review_type,
            "title": item.title,
            "description": item.description,
            "options": json.loads(item.options_json) if item.options_json else [],
            "status": item.status,
            "resolved_by": item.resolved_by,
            "resolved_at": item.resolved_at,
            "resolution_note": item.resolution_note,
            "created_at": item.created_at,
        }
        for item in items
    ]


# ---------------------------------------------------------------------------
# Review Item Update
# ---------------------------------------------------------------------------


@router.patch("/bases/{kb_id}/reviews/{review_id}")
def update_review_item(
    kb_id: int,
    review_id: int,
    status: str = Query(..., pattern="^(approved|rejected|resolved)$"),
    resolution_note: str = "",
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """处理审核任务"""
    review = db.get(KBReviewItemModel, review_id)
    if not review or review.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="Review item not found")

    review.status = status
    review.resolution_note = resolution_note
    review.resolved_by = current_user.id
    review.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(review)

    return {
        "id": review.id,
        "status": review.status,
        "resolved_by": review.resolved_by,
        "resolved_at": review.resolved_at,
    }


# ---------------------------------------------------------------------------
# Knowledge Graph
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/graph")
def get_knowledge_graph(
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取知识图谱数据（节点和边）"""
    # 获取所有页面作为节点
    pages_stmt = select(KBWikiPageModel).where(
        KBWikiPageModel.knowledge_base_id == kb_id,
        KBWikiPageModel.is_active.is_(True),
    )
    pages = db.execute(pages_stmt).scalars().all()

    # 获取所有链接作为边
    links_stmt = select(KBWikiLinkModel).where(
        KBWikiLinkModel.source_page_id.in_([p.id for p in pages])
    )
    links = db.execute(links_stmt).scalars().all()

    return {
        "nodes": [
            {
                "id": p.id,
                "label": p.title,
                "type": p.page_type,
                "authority": p.authority_level,
            }
            for p in pages
        ],
        "edges": [
            {
                "source": l.source_page_id,
                "target": l.target_page_id,
                "type": l.link_type,
            }
            for l in links
            if l.target_page_id in [p.id for p in pages]
        ],
    }
