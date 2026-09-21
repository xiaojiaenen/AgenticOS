"""混合检索器：BM25 + 向量 + RRF 融合 + 字符预算。

策略：
1. 并行三路检索：BM25 + 向量 + L3 画像
2. BM25 + 向量结果用 RRF 融合
3. 字符预算控制总注入长度
4. L3 画像头部插入（不占预算）
5. 异步更新访问统计
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.timezone import app_now
from app.db.models import MemoryModel, MemoryPersonaModel, MemoryScenarioModel
from app.db.session import create_db_session
from app.services.memory_bm25 import get_bm25_backend
from app.services.memory_embedder import get_embedder
from app.services.memory_vector_store import get_vector_store

_logger = logging.getLogger("memory_retriever")
_settings = get_settings()


class MemoryRetriever:
    """混合检索器"""

    async def retrieve(
        self,
        user_id: int,
        query: str,
        *,
        layers: tuple[str, ...] = ("L1", "L2"),
        char_budget: int | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """检索记忆，返回融合排序后的结果列表"""
        budget = char_budget or _settings.memory_retrieval_char_budget

        # 并行三路检索
        bm25_task = asyncio.create_task(
            self._safe_bm25(user_id, query, layers, _settings.memory_bm25_top_k)
        )
        vec_task = asyncio.create_task(
            self._safe_vector(user_id, query, layers, _settings.memory_vector_top_k)
        )
        l3_task = asyncio.create_task(self._get_persona(user_id))

        bm25_hits, vec_hits, persona = await asyncio.gather(bm25_task, vec_task, l3_task)

        # 加载 scenario 内容（向量/BM25 命中的 scenario_id 需要补全文本）
        vec_hits = await self._enrich_scenario_content(vec_hits)
        bm25_hits = await self._enrich_scenario_content(bm25_hits)

        # RRF 融合 BM25 + 向量
        fused = self._rrf_fuse(bm25_hits, vec_hits, k=_settings.memory_rrf_k)

        # 应用字符预算
        result = self._apply_budget(fused, budget, limit)

        # L3 画像头部插入（不占预算）
        if persona:
            result.insert(0, {
                "layer": "L3",
                "content": persona,
                "score": 1.0,
                "source": "persona",
            })

        # 异步更新访问统计（不阻塞主流程）
        atom_ids = [r["id"] for r in result if r.get("layer") == "L1" and "id" in r]
        scenario_ids = [r["id"] for r in result if r.get("layer") == "L2" and "id" in r]
        if atom_ids or scenario_ids:
            asyncio.create_task(self._touch_access(atom_ids, scenario_ids))

        return result

    async def _safe_bm25(self, user_id, query, layers, limit) -> list[dict]:
        try:
            return await get_bm25_backend().search(user_id, query, layers, limit)
        except Exception as e:
            _logger.warning(f"BM25 检索失败: {e}")
            return []

    async def _safe_vector(self, user_id, query, layers, limit) -> list[dict]:
        try:
            embedder = get_embedder()
            vec_store = get_vector_store()
            query_vec = await embedder.embed(query)
            if all(v == 0.0 for v in query_vec):
                return []  # embedding 失败（如 API key 未配置）
            hits = await vec_store.search(
                query_vec, user_id, layers,
                entity_types=("atom", "scenario"),
                limit=limit,
            )
            # 标记来源
            for h in hits:
                h["source"] = "vector"
            return hits
        except Exception as e:
            _logger.warning(f"向量检索失败: {e}")
            return []

    async def _enrich_scenario_content(self, hits: list[dict]) -> list[dict]:
        """对 L2 scenario 命中补全 title/summary 内容"""
        scenario_ids = [h["entity_id"] for h in hits if h.get("entity_type") == "scenario"]
        if not scenario_ids:
            return hits

        def _run():
            with create_db_session() as db:
                rows = db.scalars(
                    select(MemoryScenarioModel)
                    .where(MemoryScenarioModel.id.in_(scenario_ids))
                ).all()
                return {r.id: r for r in rows}

        try:
            scenarios = await asyncio.to_thread(_run)
            for h in hits:
                if h.get("entity_type") == "scenario":
                    sc = scenarios.get(h["entity_id"])
                    if sc:
                        h["id"] = sc.id  # 统一 id 字段供 RRF 融合
                        h["content"] = sc.summary
                        h["title"] = sc.title
                        h["layer"] = "L2"
            return hits
        except Exception as e:
            _logger.warning(f"补全 scenario 内容失败: {e}")
            return hits

    async def _get_persona(self, user_id: int) -> str | None:
        """获取 L3 画像，格式化为简短文本"""
        def _run():
            with create_db_session() as db:
                return db.scalars(
                    select(MemoryPersonaModel)
                    .where(MemoryPersonaModel.user_id == user_id)
                ).first()

        try:
            persona = await asyncio.to_thread(_run)
        except Exception as e:
            _logger.warning(f"读取画像失败: {e}")
            return None

        if not persona:
            return None

        parts: list[str] = []
        identity = json.loads(persona.identity_json or "{}")
        prefs = json.loads(persona.preferences_json or "{}")
        tech = json.loads(persona.tech_stack_json or "[]")
        goals = json.loads(persona.goals_json or "[]")
        projects = json.loads(persona.projects_json or "[]")

        if identity and any(identity.values()):
            parts.append(f"用户画像: {json.dumps(identity, ensure_ascii=False)}")
        if tech:
            parts.append(f"技术栈: {', '.join(tech)}")
        if goals:
            parts.append(f"目标: {'; '.join(goals)}")
        if projects:
            proj_names = [p.get("name", "") for p in projects if isinstance(p, dict) and p.get("name")]
            if proj_names:
                parts.append(f"活跃项目: {', '.join(proj_names)}")
        if prefs and any(prefs.values()):
            parts.append(f"偏好: {json.dumps(prefs, ensure_ascii=False)}")

        return "\n".join(parts) if parts else None

    @staticmethod
    def _rrf_fuse(*ranked_lists, k=60) -> list[dict]:
        """Reciprocal Rank Fusion

        k=60 是标准值，越小头部权重越集中
        """
        scores: dict[int, float] = {}
        items: dict[int, dict] = {}

        for lst in ranked_lists:
            for rank, item in enumerate(lst):
                item_id = item.get("id") or item.get("entity_id")
                if item_id is None:
                    continue
                scores[item_id] = scores.get(item_id, 0) + 1 / (k + rank + 1)
                if item_id not in items:
                    items[item_id] = item

        fused = []
        for item_id, score in sorted(scores.items(), key=lambda x: -x[1]):
            item = items[item_id].copy()
            item["fused_score"] = score
            fused.append(item)
        return fused

    @staticmethod
    def _apply_budget(hits: list[dict], budget: int, limit: int) -> list[dict]:
        """字符预算控制：按 fused_score 顺序填充，超出则截断"""
        result: list[dict] = []
        used = 0
        for hit in hits[:limit * 2]:  # 多取一些候选
            content = hit.get("content", "")
            if not content:
                continue
            if used + len(content) > budget:
                remaining = budget - used
                if remaining > 50:  # 剩余空间还够放有用的内容
                    hit = {**hit, "content": content[:remaining] + "..."}
                    result.append(hit)
                break
            result.append(hit)
            used += len(content)
            if len(result) >= limit:
                break
        return result

    async def _touch_access(self, atom_ids: list[int], scenario_ids: list[int]) -> None:
        """异步更新访问统计"""
        if not atom_ids and not scenario_ids:
            return

        def _run():
            with create_db_session() as db:
                if atom_ids:
                    db.execute(
                        update(MemoryModel)
                        .where(MemoryModel.id.in_(atom_ids))
                        .values(
                            access_count=MemoryModel.access_count + 1,
                            last_accessed_at=app_now(),
                        )
                    )
                if scenario_ids:
                    db.execute(
                        update(MemoryScenarioModel)
                        .where(MemoryScenarioModel.id.in_(scenario_ids))
                        .values(
                            access_count=MemoryScenarioModel.access_count + 1,
                            last_accessed_at=app_now(),
                        )
                    )
                db.commit()

        try:
            await asyncio.to_thread(_run)
        except Exception as e:
            _logger.debug(f"访问统计更新失败: {e}")


_retriever_singleton: MemoryRetriever | None = None


def get_retriever() -> MemoryRetriever:
    """获取检索器单例"""
    global _retriever_singleton
    if _retriever_singleton is None:
        _retriever_singleton = MemoryRetriever()
    return _retriever_singleton
