"""知识库工具

LLM 可搜索公司知识库：
- search_knowledge_base: 搜索知识库中的 Wiki 页面
- list_knowledge_bases: 列出可用的知识库

这让 LLM 可以在回答用户问题时，主动查询公司知识库获取相关信息。
"""

from __future__ import annotations

from typing import Any

from wuwei.tools import ToolRegistry


def register_knowledge_tools(registry: ToolRegistry) -> None:
    """注册知识库工具"""

    @registry.tool(
        name="search_knowledge_base",
        display_name="搜索知识库",
        description="搜索公司知识库中的 Wiki 页面。当用户的问题可能涉及公司制度、产品知识、技术方案等组织知识时，主动调用此工具检索。",
    )
    def search_knowledge_base(
        query: str,
        knowledge_base_id: int | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        """搜索知识库。

        参数:
            query: 搜索查询（描述你想查找的知识）
            knowledge_base_id: 指定知识库 ID（可选，不指定则搜索所有知识库）
            max_results: 返回结果数量（默认 5）

        返回:
            匹配的 Wiki 页面列表，包含标题、内容摘要、来源等信息
        """
        from app.services.agent_service import _current_session_id
        from app.services.session_storage import DatabaseAgentStorage
        from app.db.session import SessionLocal
        from app.services.knowledge.retrieval import KnowledgeRetrieval

        session_id = _current_session_id.get()
        if not session_id:
            return {"error": "无法获取当前会话", "results": []}

        storage = DatabaseAgentStorage()
        owner_id = storage.get_owner_id(session_id)
        if not owner_id:
            return {"error": "无法获取用户信息", "results": []}

        knowledge_base_ids = [knowledge_base_id] if knowledge_base_id else None

        db = SessionLocal()
        try:
            retrieval = KnowledgeRetrieval(db)
            results = retrieval.search(
                query=query,
                knowledge_base_ids=knowledge_base_ids,
                user_id=owner_id,
                max_results=max_results,
            )
        finally:
            db.close()

        return {
            "results": [
                {
                    "page_id": r.page_id,
                    "title": r.title,
                    "content": r.content[:1000] + "..." if len(r.content) > 1000 else r.content,
                    "page_type": r.page_type,
                    "score": round(r.score, 3),
                    "sources": r.sources,
                    "authority_level": r.authority_level,
                }
                for r in results
            ],
            "count": len(results),
        }

    @registry.tool(
        name="list_knowledge_bases",
        display_name="列出知识库",
        description="列出当前用户可访问的所有知识库。",
    )
    def list_knowledge_bases() -> dict[str, Any]:
        """列出可用的知识库。

        返回:
            知识库列表，包含 ID、名称、描述、页面数量等信息
        """
        from app.db.session import SessionLocal
        from sqlalchemy import select, func
        from app.db.models import KnowledgeBaseModel, KBWikiPageModel

        db = SessionLocal()
        try:
            stmt = select(KnowledgeBaseModel).where(KnowledgeBaseModel.is_active == True)
            result = db.execute(stmt)
            knowledge_bases = result.scalars().all()

            bases = []
            for kb in knowledge_bases:
                page_count = db.execute(
                    select(func.count()).select_from(KBWikiPageModel).where(
                        KBWikiPageModel.knowledge_base_id == kb.id,
                        KBWikiPageModel.is_active == True,
                    )
                )

                bases.append({
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "purpose": kb.purpose,
                    "scope": kb.scope,
                    "page_count": page_count.scalar() or 0,
                })
        finally:
            db.close()

        return {
            "knowledge_bases": bases,
            "count": len(bases),
        }

    @registry.tool(
        name="read_wiki_page",
        display_name="读取 Wiki 页面",
        description="读取指定 Wiki 页面的完整内容。当 search_knowledge_base 返回的结果需要更详细的信息时，调用此工具。",
    )
    def read_wiki_page(page_id: int) -> dict[str, Any]:
        """读取 Wiki 页面详情。

        参数:
            page_id: 页面 ID

        返回:
            页面的完整内容
        """
        from app.db.session import SessionLocal
        from app.db.models import KBWikiPageModel
        import json

        db = SessionLocal()
        try:
            page = db.get(KBWikiPageModel, page_id)
            if not page:
                return {"error": f"页面不存在: {page_id}"}

            try:
                sources = json.loads(page.sources_json) if page.sources_json else []
            except json.JSONDecodeError:
                sources = []

            try:
                conflicts = json.loads(page.conflicts_json) if page.conflicts_json else []
            except json.JSONDecodeError:
                conflicts = []

            return {
                "page_id": page.id,
                "title": page.title,
                "content": page.content,
                "page_type": page.page_type,
                "sources": sources,
                "authority_level": page.authority_level,
                "conflicts": conflicts,
            }
        finally:
            db.close()
