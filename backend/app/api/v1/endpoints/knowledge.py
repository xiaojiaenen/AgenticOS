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

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, delete, or_
from sqlalchemy.orm import Session

from app.api.deps import filter_readable_kb_ids, get_current_user, get_db, require_admin, require_kb_access
from app.db.models import (
    UserModel,
    KnowledgeBaseModel,
    KBDocumentModel,
    KBWikiPageModel,
    KBWikiLinkModel,
    KBChunkModel,
    KBAccessControlModel,
    KBIngestTaskModel,
    KBReviewItemModel,
)
from app.core.data_path import DATA_DIR

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


def _audit(request, db, *, action: str, current_user: UserModel, result: str = "allow", **fields) -> None:
    """知识库写操作的审计（端点内显式调用，不引中间件）。"""
    from app.services.audit_service import record, request_context

    ctx = request_context(request)
    try:
        record(
            db, action=action, actor=current_user, result=result,
            ip=ctx["ip"], user_agent=ctx["user_agent"], **fields,
        )
    except Exception:  # noqa: BLE001 -- 审计异常不得让知识库操作失败
        import logging

        logging.getLogger("agenticos.audit").warning("audit %s failed", action, exc_info=True)


def _grant_kb_ownership(db, kb_id: int, owner: UserModel) -> None:
    """知识库创建者拿到该库的读写删直接授权（幂等）。

    owner 的直接授权是 ``p, user:<id>, *, kb:<id>, <act>`` —— 域写 ``*``，
    这样调岗换部门后 owner 权限不随之丢失。
    """
    from app.services.permission_service import get_permission_service, subject_for_user

    service = get_permission_service()
    subject = subject_for_user(owner)
    for act in ("read", "write", "delete"):
        service.add_policy(subject, "*", f"kb:{kb_id}", act)


def _kb_access(db, request, current_user: UserModel, kb_id: int, action: str):
    """require_kb_access + 拒绝审计。

    越权尝试本身就是审计里最值得看的一类事件，所以 403 也要落库
    （result=deny），而不是像普通异常那样静默返回。
    """

    try:
        return require_kb_access(db, current_user, kb_id, action)
    except HTTPException as exc:
        _audit(
            request, db, action=f"knowledge.{action}", current_user=current_user, result="deny",
            resource_type="knowledge_base", resource_id=kb_id,
            detail={"status_code": exc.status_code},
        )
        raise


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
    # 命中片段：页内与查询最相关的一段（段落级向量命中的那一段）
    snippet: str = ""
    # 命中通道：["bm25", "vector"]，用于解释排序
    matched_by: list[str] = []


class KBACLEntry(BaseModel):
    principal_type: str = Field("user", pattern="^(user)$")
    # 二选一：已知用 ID，界面按邮箱加人时用 email（后端解析成 ID）
    principal_id: Optional[int] = None
    principal_email: Optional[str] = None
    role: str = Field("viewer", pattern="^(viewer|editor|admin)$")


class KBACLReplace(BaseModel):
    entries: list[KBACLEntry] = Field(default_factory=list)


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
    """列出当前用户可见的知识库（Casbin 行级过滤 + visibility/scope 过滤）。"""
    candidates = db.execute(
        select(KnowledgeBaseModel).where(KnowledgeBaseModel.is_active.is_(True))
    ).scalars().all()
    readable = filter_readable_kb_ids(db, current_user, [kb.id for kb in candidates])
    all_kbs = [kb for kb in candidates if kb.id in readable]

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
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
):
    """创建知识库（仅 admin；创建者自动获得该库的读写删授权）"""
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
            detail=f"标识已存在：{slug}",
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

    _grant_kb_ownership(db, kb.id, current_user)
    _audit(
        http_request, db, action="knowledge.create", current_user=current_user,
        resource_type="knowledge_base", resource_id=kb.id,
        detail={"slug": kb.slug, "scope": kb.scope, "visibility": kb.visibility},
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
        document_count=0,
        page_count=0,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.get("/bases/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(
    http_request: Request,
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取知识库详情（Casbin 行级过滤 + visibility/scope）。"""
    kb = _kb_access(db, http_request, current_user, kb_id, "read")

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
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """更新知识库（需 kb:write；admin 全权，dept_admin 限本部门）"""
    kb = _kb_access(db, http_request, current_user, kb_id, "write")

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

    _audit(
        http_request, db, action="knowledge.update", current_user=current_user,
        resource_type="knowledge_base", resource_id=kb.id,
        detail=request.model_dump(exclude_none=True),
    )

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
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """删除知识库（需 kb:delete）"""
    kb = _kb_access(db, http_request, current_user, kb_id, "delete")
    slug = kb.slug
    # 删除相关数据（顺序：叶子 → 主干，切片/授权先清，避免悬空引用）
    db.execute(delete(KBChunkModel).where(KBChunkModel.knowledge_base_id == kb_id))
    db.execute(delete(KBAccessControlModel).where(
        KBAccessControlModel.knowledge_base_id == kb_id
    ))
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

    _audit(
        http_request, db, action="knowledge.delete", current_user=current_user,
        resource_type="knowledge_base", resource_id=kb_id, detail={"slug": slug},
    )


# ---------------------------------------------------------------------------
# 共享成员（知识库行级 ACL）
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/acl", summary="列出知识库共享成员")
def list_kb_acl(
    http_request: Request,
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出显式共享给谁（owner 与 admin 不在列表中，他们天生可见）。"""
    from app.services.knowledge.acl import list_grants

    _kb_access(db, http_request, current_user, kb_id, "read")
    return {"knowledge_base_id": kb_id, "items": list_grants(db, kb_id)}


@router.put("/bases/{kb_id}/acl", summary="整体替换知识库共享成员")
def replace_kb_acl(
    http_request: Request,
    kb_id: int,
    payload: KBACLReplace,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """整体替换共享成员（幂等）。

    只允许库 owner 或系统管理员操作 —— 普通 editor 不该能把库转给别人看，
    也不能给自己提权。

    条目可以给 ``principal_id``（已知用户 ID），也可以只给 ``principal_email``
    （管理界面按邮箱加人），后者在这里解析成 ID。
    """
    from app.services.knowledge.acl import list_grants, replace_grants

    kb = _kb_access(db, http_request, current_user, kb_id, "read")
    if current_user.role != "admin" and kb.owner_id != current_user.id:
        _audit(
            http_request, db, action="knowledge.acl_update", current_user=current_user,
            result="deny", resource_type="knowledge_base", resource_id=kb_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有知识库创建者或管理员可以修改共享成员",
        )

    # 解析 email → id，并校验被授权用户真实存在（避免写入悬空授权）
    resolved: list[dict] = []
    unresolved: list[str] = []
    for entry in payload.entries:
        principal_id = entry.principal_id
        if principal_id is None:
            email = (entry.principal_email or "").strip().lower()
            if not email:
                unresolved.append("<空>")
                continue
            principal_id = db.scalar(
                select(UserModel.id).where(func.lower(UserModel.email) == email)
            )
            if principal_id is None:
                unresolved.append(email)
                continue
        resolved.append({"principal_type": "user", "principal_id": principal_id, "role": entry.role})

    # 直接传 ID 的条目也要校验存在性，否则会写出一批指向空用户的授权
    given_ids = {item["principal_id"] for item in resolved}
    if given_ids:
        existing_ids = {
            row[0]
            for row in db.execute(
                select(UserModel.id).where(UserModel.id.in_(given_ids))
            ).all()
        }
        unresolved.extend(str(missing) for missing in sorted(given_ids - existing_ids))

    if unresolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"用户不存在: {sorted(set(unresolved))}",
        )

    written = replace_grants(db, kb_id, resolved, granted_by=current_user.id)
    db.commit()
    _audit(
        http_request, db, action="knowledge.acl_update", current_user=current_user,
        resource_type="knowledge_base", resource_id=kb_id,
        detail={"entries": written},
    )
    return {"knowledge_base_id": kb_id, "items": list_grants(db, kb_id)}


# ---------------------------------------------------------------------------
# Document Management
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/documents", response_model=list[DocumentResponse])
def list_documents(
    http_request: Request,
    kb_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出知识库中的文档"""
    _kb_access(db, http_request, current_user, kb_id, "read")

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
    http_request: Request,
    kb_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """上传文档并提交编译任务到后台队列（需 kb:write）"""
    # 检查知识库
    kb = _kb_access(db, http_request, current_user, kb_id, "write")

    # 检查文件类型
    allowed_types = {"pdf", "docx", "md", "markdown", "html", "htm", "txt"}
    file_ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename else ""
    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件类型：{file_ext}",
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

    _audit(
        http_request, db, action="knowledge.document_upload", current_user=current_user,
        resource_type="kb_document", resource_id=doc.id,
        detail={"knowledge_base_id": kb_id, "file_type": file_ext, "file_size": len(content)},
    )

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
    http_request: Request,
    kb_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """删除文档：清理文件、Wiki 页面 sources 引用与图谱链接（需 kb:delete）。"""
    _kb_access(db, http_request, current_user, kb_id, "delete")
    doc = db.get(KBDocumentModel, doc_id)
    if not doc or doc.knowledge_base_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

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

    _audit(
        http_request, db, action="knowledge.document_delete", current_user=current_user,
        resource_type="kb_document", resource_id=doc_id, detail={"knowledge_base_id": kb_id},
    )


# ---------------------------------------------------------------------------
# Wiki Pages
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/wiki/pages", response_model=list[WikiPageResponse])
def list_wiki_pages(
    http_request: Request,
    kb_id: int,
    page_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出 Wiki 页面（先做知识库行级鉴权）。"""
    _kb_access(db, http_request, current_user, kb_id, "read")

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
    http_request: Request,
    kb_id: int,
    page_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取 Wiki 页面详情（先做知识库行级鉴权）。"""
    _kb_access(db, http_request, current_user, kb_id, "read")

    page = db.get(KBWikiPageModel, page_id)
    if not page or page.knowledge_base_id != kb_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")

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


class RecallTestRequest(BaseModel):
    """召回测试请求：跑一批问题，报告命中情况。"""

    questions: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="测试问题集；留空则用知识库页面标题自动生成探针",
    )
    top_k: int = Field(default=5, ge=1, le=50, description="每个问题取前 K 条")
    score_threshold: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="相对相关度阈值（0~1）；低于视为未命中（留空=不过滤）",
    )
    page_type: Optional[str] = Field(default=None, description="限定页面类型")


@router.post("/bases/{kb_id}/recall-test", summary="知识库召回测试")
async def recall_test(
    http_request: Request,
    kb_id: int,
    request: RecallTestRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """对知识库跑召回测试，报告命中率、平均命中排名与每题命中详情。

    用于调切片/TopK/阈值前后的效果回归对比。
    """
    from app.services.knowledge.recall_test import run_recall_test
    from app.services.knowledge.retrieval import KnowledgeRetrieval

    kb = db.get(KnowledgeBaseModel, kb_id)
    if not kb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库不存在")

    # 与其他知识库端点一致做行级鉴权：召回测试会返回正文片段，
    # 不校验权限等于把 private / 他人知识库的内容读出来
    _kb_access(db, http_request, current_user, kb_id, "read")

    report = await run_recall_test(
        kb_id,
        KnowledgeRetrieval(db).search,
        questions=request.questions,
        top_k=request.top_k,
        score_threshold=request.score_threshold,
        page_type=request.page_type,
        user_id=current_user.id,
        is_admin=current_user.role == "admin",
    )
    return report.to_dict()


@router.post("/bases/{kb_id}/search", response_model=list[SearchResultItem])
def search_knowledge_base(
    http_request: Request,
    kb_id: int,
    request: SearchRequest,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """搜索知识库（先做行级鉴权，再按用户权限过滤 private/scope）。"""
    from app.services.knowledge.retrieval import KnowledgeRetrieval

    _kb_access(db, http_request, current_user, kb_id, "read")
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
            snippet=r.snippet or (
                r.content[:500] + "..." if len(r.content) > 500 else r.content
            ),
            matched_by=r.matched_by,
        )
        for r in results
    ]


@router.post("/bases/{kb_id}/reindex", summary="重建知识库向量索引")
def reindex_knowledge_base_endpoint(
    http_request: Request,
    kb_id: int,
    force: bool = Query(default=False, description="true=全部重算（换过 embedding 模型时用）"),
    limit: Optional[int] = Query(default=None, ge=1, le=5000, description="最多处理多少页"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """为知识库页面补算 embedding 与段级切片。

    - 默认只补「还没就绪」的页面：没有页向量、或还没有任何切片（段级检索上线
      前的存量页都属于这一类）；
    - ``force=true`` 全部重算，换 embedding 模型后必须这样做；
    - 未配置 API Key 时返回 ``enabled=false``，不报错（检索此时走纯 BM25）。
    """
    from app.services.knowledge.chunk_index import chunk_stats
    from app.services.knowledge.ingest_pipeline import reindex_knowledge_base

    _kb_access(db, http_request, current_user, kb_id, "write")

    # 本端点是同步定义，FastAPI 会放到线程池执行，不会阻塞事件循环
    stats = reindex_knowledge_base(kb_id, force=force, limit=limit)
    stats.update(chunk_stats(db, kb_id))
    _audit(
        http_request, db, action="knowledge.reindex", current_user=current_user,
        resource_type="knowledge_base", resource_id=kb_id, detail=stats,
    )
    return {"knowledge_base_id": kb_id, **stats}


@router.post("/bases/{kb_id}/conflicts/scan", summary="知识库冲突巡检（跨页面配对扫描）")
def scan_conflicts_endpoint(
    http_request: Request,
    kb_id: int,
    use_llm: bool = Query(
        default=False,
        description="规则未命中时是否再让 LLM 判一次（会消耗 token，按需开启）",
    ),
    max_pages: int = Query(default=800, ge=2, le=5000, description="本轮参与扫描的页面上限"),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """全库跨页配对扫描，找出「编辑期永远不会相遇」的两个页面之间的矛盾。

    编译期的冲突检测只比对「新页面 vs 已有页面」，因此历史导入、分次上传、
    批量重建索引产生的页面之间如果有矛盾，永远不会被发现。本端点补这个盲区：

    - 只**新增**待裁决的 ``conflict_resolution`` 审核项，**不修改任何正文**；
    - 幂等：同一对页面已有待裁决项时跳过，可以反复触发；
    - 默认纯规则判定（不烧 token），``use_llm=true`` 才追加 LLM 复核。

    定时版本由 arq cron 每周一 04:23 全库执行（``scan_knowledge_conflicts_task``）。
    """
    from app.services.knowledge.conflict_scanner import scan_knowledge_base

    _kb_access(db, http_request, current_user, kb_id, "write")

    # 同步定义 → FastAPI 放线程池执行，全库扫描不阻塞事件循环
    stats = scan_knowledge_base(db, kb_id, max_pages=max_pages, use_llm=use_llm)
    db.commit()

    _audit(
        http_request, db, action="knowledge.conflict_scan", current_user=current_user,
        resource_type="knowledge_base", resource_id=kb_id, detail=stats,
    )
    return {"knowledge_base_id": kb_id, **stats}


# ---------------------------------------------------------------------------
# Review Items
# ---------------------------------------------------------------------------


@router.get("/bases/{kb_id}/reviews")
def list_review_items(
    http_request: Request,
    kb_id: int,
    status_filter: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """列出审核任务（需 kb:read）"""
    _kb_access(db, http_request, current_user, kb_id, "read")
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
    http_request: Request,
    kb_id: int,
    review_id: int,
    status: str = Query(..., pattern="^(approved|rejected|resolved)$"),
    resolution_note: str = "",
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """处理审核任务（需 kb:write）"""
    _kb_access(db, http_request, current_user, kb_id, "write")
    review = db.get(KBReviewItemModel, review_id)
    if not review or review.knowledge_base_id != kb_id:
        raise HTTPException(status_code=404, detail="审核项不存在")

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
    http_request: Request,
    kb_id: int,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """获取知识图谱数据（节点和边，需 kb:read）"""
    _kb_access(db, http_request, current_user, kb_id, "read")
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
