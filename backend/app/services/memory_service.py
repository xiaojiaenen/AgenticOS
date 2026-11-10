"""用户记忆服务（分层蒸馏版）

架构：
- L0 原始对话：完整留存，用于回溯与重新蒸馏
- L1 Atom: 事实/偏好/技术栈/项目（每轮提取）
- L2 Scenario: 场景块（每 memory_l2_aggregate_turns 轮聚合）
- L3 Persona: 用户长期画像（每 memory_l3_persona_turns 轮更新）

检索：BM25 + 向量 + RRF 融合
装配：按 Agent 模式动态控制字符预算

本模块只保留向后兼容入口，具体逻辑委派给：
- memory_pipeline: 蒸馏流程
- memory_retriever: 混合检索
- memory_loadout: 按 mode 装配
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select

from app.db.models import MemoryModel
from app.db.session import create_db_session

_logger = logging.getLogger("memory_service")


class UserMemoryService:
    """记忆服务入口（向后兼容旧 API）"""

    async def add_memory(
        self,
        user_id: int,
        content: str,
        *,
        memory_type: str = "fact",
        importance: float = 0.5,
        tags: list[str] | None = None,
        source: str = "auto",
    ) -> int:
        """添加 L1 atom（向后兼容）

        走 pipeline 内部保存逻辑，自动生成向量。
        """
        from app.services.memory_pipeline import get_pipeline

        atom_id = await get_pipeline()._save_atom(
            user_id,
            {
                "content": content,
                "type": memory_type,
                "importance": importance,
            },
            tags=tags,
            source=source,
        )
        return atom_id or 0

    async def search_memory(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """搜索记忆（向后兼容，走混合检索）

        返回旧格式以兼容前端。
        """
        from app.services.memory_retriever import get_retriever

        hits = await get_retriever().retrieve(
            user_id, query,
            layers=("L1", "L2"),
            limit=limit,
        )

        # 兼容旧返回格式（L3 画像不返回到列表）
        return [
            {
                "id": h.get("id"),
                "user_id": user_id,
                "content": h.get("content", ""),
                "memory_type": h.get("memory_type", "fact"),
                "importance": h.get("importance", 0.5),
                "tags": [],
                "source": h.get("source", "auto"),
                "layer": h.get("layer", "L1"),
                "created_at": h.get("created_at"),
            }
            for h in hits
            if h.get("layer") != "L3"
        ]

    async def get_memory_context(
        self,
        user_id: int,
        query: str,
        *,
        limit: int = 3,
    ) -> str:
        """获取记忆上下文（旧 API，agent_service 调用）

        委派给 loadout（默认 general 模式）。
        """
        from app.services.memory_loadout import assemble_memory_context

        return await assemble_memory_context(user_id, query, "general")

    async def get_all_memories(
        self,
        user_id: int,
        *,
        limit: int = 200,
        offset: int = 0,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取用户所有 L1 atom 记忆（管理后台用，分页返回）"""

        def _run():
            with create_db_session() as db:
                stmt = (
                    select(MemoryModel)
                    .where(MemoryModel.user_id == user_id)
                    .where(MemoryModel.layer == "L1")
                )
                if q:
                    stmt = stmt.where(MemoryModel.content.contains(q))
                return db.scalars(
                    stmt.order_by(MemoryModel.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                ).all()

        rows = await asyncio.to_thread(_run)
        return [self._row_to_dict(r) for r in rows]

    async def count_memories(self, user_id: int, *, q: str | None = None) -> int:
        """带过滤条件的记忆总数（分页控件需要 total 才能算总页数）"""

        def _run():
            with create_db_session() as db:
                stmt = (
                    select(MemoryModel.id)
                    .where(MemoryModel.user_id == user_id)
                    .where(MemoryModel.layer == "L1")
                )
                if q:
                    stmt = stmt.where(MemoryModel.content.contains(q))
                return len(db.scalars(stmt).all())

        return await asyncio.to_thread(_run)

    async def get_all_memories_admin(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        """管理员：获取所有用户的 L1 记忆（分页返回）"""

        def _run():
            with create_db_session() as db:
                stmt = select(MemoryModel).where(MemoryModel.layer == "L1")
                if q:
                    stmt = stmt.where(MemoryModel.content.contains(q))
                return db.scalars(
                    stmt.order_by(MemoryModel.user_id, MemoryModel.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                ).all()

        rows = await asyncio.to_thread(_run)
        return [self._row_to_dict(r) for r in rows]

    async def count_memories_admin(self, *, q: str | None = None) -> int:
        """管理员：全量记忆总数（含过滤条件）"""

        def _run():
            with create_db_session() as db:
                stmt = select(MemoryModel.id).where(MemoryModel.layer == "L1")
                if q:
                    stmt = stmt.where(MemoryModel.content.contains(q))
                return len(db.scalars(stmt).all())

        return await asyncio.to_thread(_run)

    async def delete_memory(self, memory_id: int, user_id: int | None = None) -> bool:
        """删除一条 L1 atom（同步删除向量 + FTS 索引）"""
        from app.services.memory_vector_store import get_vector_store
        from app.services.memory_bm25 import get_bm25_backend

        def _run() -> MemoryModel | None:
            with create_db_session() as db:
                row = db.get(MemoryModel, memory_id)
                if row is None:
                    return None
                if user_id is not None and row.user_id != user_id:
                    return None
                # 先取出 content 供 FTS 删除（external content 需要原文）
                content = row.content
                db.delete(row)
                db.commit()
                return MemoryModel(
                    id=memory_id,
                    user_id=row.user_id if hasattr(row, "user_id") else 0,
                    content=content,
                )

        row = await asyncio.to_thread(_run)
        if row is None:
            return False

        # 异步清理向量 + FTS 索引（不阻塞返回）
        try:
            await get_bm25_backend().remove_document(memory_id, row.content)
        except Exception as e:
            _logger.debug(f"FTS 删除失败 id={memory_id}: {e}")

        asyncio.create_task(get_vector_store().delete("atom", memory_id))
        return True

    async def extract_and_save_memories(
        self,
        user_id: int,
        user_message: str,
        assistant_response: str,
        llm_gateway=None,
    ) -> None:
        """旧 API 兼容：转走 pipeline.on_turn_complete"""
        from app.services.memory_pipeline import get_pipeline

        await get_pipeline().on_turn_complete(
            user_id, None, user_message, assistant_response, mode="general"
        )

    @staticmethod
    def _row_to_dict(row: MemoryModel) -> dict[str, Any]:
        tags: list[str] = []
        if row.tags_json:
            try:
                tags = json.loads(row.tags_json)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": row.id,
            "user_id": row.user_id,
            "content": row.content,
            "memory_type": row.memory_type,
            "importance": row.importance,
            "tags": tags,
            "source": row.source,
            "layer": row.layer,
            "scenario_id": row.scenario_id,
            "access_count": row.access_count,
            "visibility": row.visibility,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_accessed_at": row.last_accessed_at.isoformat() if row.last_accessed_at else None,
        }

    async def get_persona(self, user_id: int) -> dict[str, Any] | None:
        """获取用户 L3 画像"""
        from app.db.models import MemoryPersonaModel

        def _run():
            with create_db_session() as db:
                return db.scalars(
                    select(MemoryPersonaModel).where(
                        MemoryPersonaModel.user_id == user_id
                    )
                ).first()

        row = await asyncio.to_thread(_run)
        if not row:
            return None

        import json
        return {
            "identity": json.loads(row.identity_json or "{}"),
            "preferences": json.loads(row.preferences_json or "{}"),
            "tech_stack": json.loads(row.tech_stack_json or "[]"),
            "goals": json.loads(row.goals_json or "[]"),
            "projects": json.loads(row.projects_json or "[]"),
            "version": row.version,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def list_scenarios(self, user_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """列出用户 L2 场景块"""
        from app.db.models import MemoryScenarioModel

        def _run():
            with create_db_session() as db:
                return db.scalars(
                    select(MemoryScenarioModel).where(
                        MemoryScenarioModel.user_id == user_id
                    ).order_by(MemoryScenarioModel.updated_at.desc()).limit(limit)
                ).all()

        rows = await asyncio.to_thread(_run)
        import json
        return [
            {
                "id": r.id,
                "title": r.title,
                "summary": r.summary,
                "tags": json.loads(r.tags_json) if r.tags_json else [],
                "atom_ids": json.loads(r.atom_ids_json) if r.atom_ids_json else [],
                "access_count": r.access_count,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        ]

    async def get_portrait(self, user_id: int) -> dict[str, Any]:
        """「AI 眼中的你」：把 L3 画像 + L1 事实分布 + L2 场景聚合成一张画像卡。

        纯读取 + 确定性文案，不调用 LLM；画像缺失时返回空结构而非报错，
        前端据此引导用户「多聊几句，让 AI 更懂你」。
        """
        import json
        from datetime import datetime

        from sqlalchemy import func

        from app.core.timezone import app_now, to_app_timezone
        from app.db.models import MemoryModel, MemoryScenarioModel

        persona = await self.get_persona(user_id)

        def _run():
            with create_db_session() as db:
                type_rows = db.execute(
                    select(MemoryModel.memory_type, func.count(MemoryModel.id))
                    .where(MemoryModel.user_id == user_id, MemoryModel.layer == "L1")
                    .group_by(MemoryModel.memory_type)
                ).all()
                total = sum(c for _, c in type_rows)
                earliest = db.scalar(
                    select(func.min(MemoryModel.created_at)).where(MemoryModel.user_id == user_id)
                )
                recent = db.scalars(
                    select(MemoryModel)
                    .where(MemoryModel.user_id == user_id, MemoryModel.layer == "L1")
                    .order_by(MemoryModel.importance.desc(), MemoryModel.created_at.desc())
                    .limit(12)
                ).all()
                scenario_count = db.scalar(
                    select(func.count(MemoryScenarioModel.id)).where(MemoryScenarioModel.user_id == user_id)
                ) or 0
                return type_rows, total, earliest, recent, scenario_count

        type_rows, total, earliest, recent, scenario_count = await asyncio.to_thread(_run)

        since = to_app_timezone(earliest) if earliest else None
        days_known = (app_now() - since).days if since else 0
        atoms_by_type = {t: c for t, c in type_rows}

        if total == 0:
            summary = "AI 还不怎么了解你。多聊几句，它会慢慢记住你的偏好与正在做的事。"
        else:
            summary = (
                f"AI 已经认识你 {days_known} 天，记住了 {total} 条关于你的事"
                f"{'，并提炼出 ' + str(scenario_count) + ' 个关注主题' if scenario_count else ''}。"
                "下面是它眼中的你 —— 你可以随时纠正或删除。"
            )

        return {
            "has_persona": persona is not None,
            "identity": (persona or {}).get("identity", {}),
            "preferences": (persona or {}).get("preferences", {}),
            "tech_stack": (persona or {}).get("tech_stack", []),
            "goals": (persona or {}).get("goals", []),
            "projects": (persona or {}).get("projects", []),
            "persona_updated_at": (persona or {}).get("updated_at"),
            "atom_count": total,
            "atoms_by_type": atoms_by_type,
            "scenario_count": scenario_count,
            "days_known": days_known,
            "memory_since": since.date().isoformat() if since else None,
            "summary": summary,
            "recent_atoms": [
                {
                    "id": a.id,
                    "content": a.content,
                    "memory_type": a.memory_type,
                    "importance": a.importance,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                }
                for a in recent
            ],
        }


# 单例（沿用 ThreadSafeSingleton）
from app.core.singleton import ThreadSafeSingleton  # noqa: E402

_memory_service_singleton = ThreadSafeSingleton(UserMemoryService)


def get_memory_service() -> UserMemoryService:
    """获取记忆服务单例"""
    return _memory_service_singleton.get()
