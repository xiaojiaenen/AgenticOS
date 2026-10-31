"""分层蒸馏 Pipeline：L0 → L1 → L2 → L3

触发时机（在 agent_service 对话结束时调用 on_turn_complete）：
- L0: 每轮落库（无 LLM 调用，必执行）
- L1: 每轮 LLM 提取 atoms + 生成向量
- L2: 每 memory_l2_aggregate_turns 轮聚合 scenario（异步）
- L3: 每 memory_l3_persona_turns 轮更新画像（异步）

每层失败都不影响其他层（容错隔离）。
"""

from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.timezone import app_now
from app.db.models import (
    MemoryConversationModel,
    MemoryModel,
    MemoryPersonaModel,
    MemoryScenarioModel,
)
from app.db.session import create_db_session
from app.services.llm_factory import build_llm
from app.services.memory_embedder import get_embedder
from app.services.memory_service import get_memory_service
from app.services.memory_vector_store import get_vector_store

_logger = logging.getLogger("memory_pipeline")
_settings = get_settings()

# LLM 蒸馏/提取任务的并发上限（fire-and-forget 任务也受此约束，防止打满上游）
_LLM_CONCURRENCY = 3
_llm_semaphore = asyncio.Semaphore(_LLM_CONCURRENCY)

# ── L1 提取整合参数 ──
# 单轮最多入库的记忆条数（再干净的提取也不该一轮塞一堆）
_MAX_ATOMS_PER_TURN = 3
# 参与去重对照的既有记忆检索条数
_CONSOLIDATION_RETRIEVE_K = 8
# 既有记忆参与对照的最低相似度（低于此值与本轮对话无关，对照无意义）
_CONSOLIDATION_MIN_RELEVANCE = 0.45
# 硬闸阈值：
# - difflib 只拦接近复制的（实测真实重复对散布在 0.58-0.93，字符相似度不可靠）
# - 语义重复主要靠向量余弦（0.92：同义不同措辞几乎必然高于此）
_SIMILAR_DUP_THRESHOLD = 0.85
_SEMANTIC_DUP_THRESHOLD = 0.92
# 存量去重：向量余弦相似度阈值（同义记忆聚类）
_DEDUPE_SIMILARITY_THRESHOLD = 0.92

# _turn_counts 最多保留的 user 数，超过后按 LRU 淘汰
_TURN_COUNTS_MAX_USERS = 10000


class MemoryPipeline:
    """异步蒸馏 Pipeline"""

    def __init__(self) -> None:
        # user_id -> 累计轮次（内存计数，重启后从 0 开始；可接受）
        # OrderedDict 实现 LRU：超过上限淘汰最久未活跃的 user
        self._turn_counts: OrderedDict[int, int] = OrderedDict()

    def _bump_turn_count(self, user_id: int) -> int:
        self._turn_counts[user_id] = self._turn_counts.get(user_id, 0) + 1
        self._turn_counts.move_to_end(user_id)
        while len(self._turn_counts) > _TURN_COUNTS_MAX_USERS:
            self._turn_counts.popitem(last=False)
        return self._turn_counts[user_id]

    async def on_turn_complete(
        self,
        user_id: int,
        session_id: str | None,
        user_message: str,
        assistant_message: str,
        *,
        mode: str = "general",
        tokens_used: int = 0,
    ) -> None:
        """对话轮次结束钩子（fire-and-forget 调用）"""
        # 1. L0 落库（永远执行，无 LLM 调用）
        await self._save_conversation(
            user_id, session_id, user_message, assistant_message, mode, tokens_used
        )

        # 累计轮次
        turn = self._bump_turn_count(user_id)

        # 2. L1 提取（每轮执行；Mem0 式"检索既有 → 单次 LLM 加性提取 → 硬闸去重"）
        atoms = await self._extract_and_consolidate(user_id, user_message, assistant_message)
        for atom in atoms:
            await self._save_atom(user_id, atom)

        # 3. L2 聚合（每 N 轮）
        if turn % _settings.memory_l2_aggregate_turns == 0:
            asyncio.create_task(self._aggregate_scenarios(user_id))

        # 4. L3 画像更新（每 N 轮）
        if turn % _settings.memory_l3_persona_turns == 0:
            asyncio.create_task(self._update_persona(user_id))

    # ── L0 ──
    async def _save_conversation(
        self,
        user_id: int,
        session_id: str | None,
        user_msg: str,
        assistant_msg: str,
        mode: str,
        tokens: int,
    ) -> None:
        def _run():
            with create_db_session() as db:
                db.add(MemoryConversationModel(
                    user_id=user_id,
                    session_id=session_id,
                    user_message=user_msg,
                    assistant_message=assistant_msg,
                    tokens_used=tokens,
                    metadata_json=json.dumps({"mode": mode}, ensure_ascii=False),
                ))
                db.commit()

        try:
            await asyncio.to_thread(_run)
        except Exception as e:
            _logger.warning(f"L0 落库失败: {e}")

    # ── L1 ──
    async def _extract_and_consolidate(
        self, user_id: int, user_msg: str, assistant_msg: str
    ) -> list[dict]:
        """Mem0 式两阶段 L1 提取（单次 LLM 调用）。

        旧实现的两个毛病（用户实测 31 条"ORION 项目"重复记忆的根因）：
        1. 每轮无条件提取，prompt 没有"什么不该记"的负面清单 ——
           一次性的界面操作流水、进行时状态全被蒸馏入库；
        2. 与既有记忆的去重只有「前 50 字符完全相同」——
           措辞稍有不同的同一事实（"项目代号是 ORION"/"用户的项目代号为 ORION"）
           每轮都能过闸，越积越多。

        新流程：
        - Phase 1 向量检索该用户与本轮对话最相关的既有 L1 记忆（top-K）；
        - Phase 2 单次 LLM 调用：把既有记忆（带编号）和新对话一起交给模型，
          只输出「净新增」的记忆（语义等价的直接跳过）—— 提取与去重同一次完成；
        - 硬闸（代码，不信任 LLM）：MD5 精确去重 + 前 50 字符前缀去重 +
          与既有记忆的字符相似度闸（difflib，换措辞的重复拦在入库前）。
        """
        from wuwei.core.message import SystemMessage, HumanMessage

        conversation = f"用户: {user_msg}\nAI: {assistant_msg[:1500]}"

        # Phase 1: 取既有记忆做对照。进程内余弦检索（embed 全量缓存）——
        # Redis FT.SEARCH 在线上实测 KNN 恒返回 0 结果（RediSearch 2.10.20
        # build 缺陷），检索侧已全面改为进程内余弦，不再依赖它。
        existing: list[dict[str, Any]] = []
        try:
            embedder = get_embedder()
            query_vector = await embedder.embed(conversation[:1000])

            def _fetch_recent():
                with create_db_session() as db:
                    return db.scalars(
                        select(MemoryModel)
                        .where(MemoryModel.user_id == user_id)
                        .where(MemoryModel.layer == "L1")
                        .order_by(MemoryModel.created_at.desc())
                        .limit(200)
                    ).all()

            rows = await asyncio.to_thread(_fetch_recent)
            scored: list[tuple[float, str]] = []
            for row in rows:
                try:
                    vec = await embedder.embed(row.content)
                except Exception:  # noqa: BLE001 -- 无向量条目不参与对照
                    continue
                score = self._cosine(query_vector, vec)
                if score >= _CONSOLIDATION_MIN_RELEVANCE:
                    scored.append((score, row.content))
            scored.sort(reverse=True)
            existing = [{"memory_id": 0, "content": c} for _, c in scored[:_CONSOLIDATION_RETRIEVE_K]]
        except Exception as e:
            _logger.debug(f"L1 既有记忆检索失败，退化为无对照提取: {e}")
            existing = []

        # Phase 2: 单次 LLM 提取（prompt 里带既有记忆，让模型只输出净新增）
        existing_block = (
            "\n".join(f"{i + 1}. {item['content']}" for i, item in enumerate(existing))
            if existing
            else "（暂无相关记忆）"
        )
        try:
            gateway = build_llm(role="fast", max_tokens=1024, timeout=60)
            prompt = ATOM_EXTRACTION_PROMPT.format(
                existing_memories=existing_block,
                conversation=conversation,
            )
            async with _llm_semaphore:
                resp = await gateway.generate(messages=[
                    SystemMessage(content="你是记忆提取器，只输出 JSON 对象。"),
                    HumanMessage(content=prompt),
                ])
            atoms = _parse_extraction_json(resp.message.content)
        except Exception as e:
            _logger.debug(f"L1 提取失败: {e}")
            return []

        if not isinstance(atoms, list):
            return []

        # 每轮上限：再干净的提取也不该一轮塞进一堆记忆
        atoms = atoms[:_MAX_ATOMS_PER_TURN]

        # 硬闸（代码，不信任 LLM 的去重判断）：
        #   MD5 精确 → 前 50 字符前缀 → difflib 字符相似 → 向量余弦。
        # difflib 只能拦住接近复制的（实测真实重复对散布在 0.58-0.93，
        # 字符相似度并不可靠），语义重复主要靠余弦；existing/新记忆的
        # 向量都有 Redis 缓存，稳态下近乎零成本。
        existing_vectors: list[list[float] | None] = []
        for item in existing:
            try:
                existing_vectors.append(await get_embedder().embed(item["content"]))
            except Exception:  # noqa: BLE001 -- 单条向量失败只降级该条的余弦闸
                existing_vectors.append(None)

        kept: list[dict] = []
        kept_vectors: list[list[float]] = []
        for atom in atoms:
            if not isinstance(atom, dict) or not str(atom.get("content", "")).strip():
                continue
            content = str(atom["content"]).strip()
            try:
                new_vector = await get_embedder().embed(content)
            except Exception:  # noqa: BLE001
                new_vector = None
            if await self._is_duplicate(
                content, new_vector,
                [item["content"] for item in existing], existing_vectors,
            ):
                _logger.info(f"L1 硬闸拦截重复记忆: {content[:60]}")
                continue
            if await self._is_duplicate(
                content, new_vector,
                [k["content"] for k in kept], kept_vectors,
            ):
                continue
            kept.append(atom)
            if new_vector is not None:
                kept_vectors.append(new_vector)
        return kept

    async def _fetch_existing_contents(self, memory_ids: list[int]) -> list[dict[str, Any]]:
        """按向量检索命中的 entity_id 取回既有记忆内容（保持检索排序）。"""
        def _run():
            with create_db_session() as db:
                rows = db.scalars(
                    select(MemoryModel).where(MemoryModel.id.in_(memory_ids))
                ).all()
                by_id = {r.id: r for r in rows}
                return [
                    {"memory_id": mid, "content": by_id[mid].content}
                    for mid in memory_ids
                    if mid in by_id
                ]

        return await asyncio.to_thread(_run)

    async def _fetch_recent_memories(self, user_id: int, k: int) -> list[dict[str, Any]]:
        """DB 回退：最近 k 条 L1 记忆（向量检索不可用时的对照来源）。"""
        def _run():
            with create_db_session() as db:
                return [
                    {"memory_id": r.id, "content": r.content}
                    for r in db.scalars(
                        select(MemoryModel)
                        .where(MemoryModel.user_id == user_id)
                        .where(MemoryModel.layer == "L1")
                        .order_by(MemoryModel.created_at.desc())
                        .limit(k)
                    ).all()
                ]

        return await asyncio.to_thread(_run)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    @staticmethod
    async def _is_duplicate(
        content: str,
        content_vector: list[float] | None,
        existing_contents: list[str],
        existing_vectors: list[list[float] | None],
    ) -> bool:
        """代码级重复闸：MD5 / 前缀 / difflib / 向量余弦，任一命中即重复。

        difflib 实测对真实重复对散布在 0.58-0.93（"用户在做 ORION 项目" vs
        "用户正在进行 ORION 项目的界面开发" 只有 0.73），所以只保留高阈值
        拦接近复制；语义重复交给向量余弦。
        """
        md5 = hashlib.md5(content.encode()).hexdigest()
        for index, existing in enumerate(existing_contents):
            if hashlib.md5(existing.encode()).hexdigest() == md5:
                return True
            if existing[:50] == content[:50]:
                return True
            if difflib.SequenceMatcher(None, content[:120], existing[:120]).ratio() >= _SIMILAR_DUP_THRESHOLD:
                return True
            if (
                content_vector is not None
                and index < len(existing_vectors)
                and existing_vectors[index] is not None
                and MemoryPipeline._cosine(content_vector, existing_vectors[index]) >= _SEMANTIC_DUP_THRESHOLD
            ):
                return True
        return False

    async def _extract_atoms(self, user_msg: str, assistant_msg: str) -> list[dict]:
        """兼容保留：无 user_id 上下文的裸提取（仅测试/脚本使用）。"""
        return await self._extract_and_consolidate(0, user_msg, assistant_msg)

    async def _save_atom(
        self,
        user_id: int,
        atom: dict,
        *,
        tags: list[str] | None = None,
        source: str | None = None,
    ) -> int | None:
        """保存 L1 atom，同时异步生成向量写入 vector store，并维护 FTS。"""
        if not isinstance(atom, dict) or not atom.get("content"):
            return None

        content = str(atom["content"]).strip()
        if not content:
            return None

        # 去重检查：同一用户、相似内容（前50字符相同）的记忆不重复保存
        def _check_duplicate() -> bool:
            with create_db_session() as db:
                from sqlalchemy import func
                existing = db.scalars(
                    select(MemoryModel).where(
                        MemoryModel.user_id == user_id,
                        MemoryModel.layer == "L1",
                        func.substr(MemoryModel.content, 1, 50) == content[:50],
                    )
                ).first()
                return existing is not None

        try:
            is_dup = await asyncio.to_thread(_check_duplicate)
            if is_dup:
                _logger.debug(f"Duplicate atom skipped: {content[:50]}")
                return None
        except Exception:
            pass  # 去重检查失败不影响保存

        def _run() -> int:
            with create_db_session() as db:
                row = MemoryModel(
                    user_id=user_id,
                    content=content,
                    memory_type=str(atom.get("type", "fact")),
                    importance=float(atom.get("importance", 0.5)),
                    tags_json=json.dumps(
                        tags if tags else ["auto-extracted"],
                        ensure_ascii=False,
                    ),
                    source=source or "auto",
                    layer="L1",
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return row.id

        try:
            atom_id = await asyncio.to_thread(_run)
        except Exception as e:
            _logger.warning(f"L1 atom 保存失败: {e}")
            return None

        # 同步维护 BM25/FTS 索引
        try:
            from app.services.memory_bm25 import get_bm25_backend
            await get_bm25_backend().index_document(atom_id, content)
        except Exception as e:
            _logger.debug(f"FTS index 失败 id={atom_id}: {e}")

        # 异步生成向量（不阻塞主流程）
        asyncio.create_task(self._embed_and_upsert(atom_id, "atom", user_id, "L1", content))
        _logger.info(f"Saved L1 atom for user {user_id}: {content[:50]}...")
        return atom_id

    async def _embed_and_upsert(
        self,
        entity_id: int,
        entity_type: str,    # "atom" | "scenario"
        user_id: int,
        layer: str,
        text: str,
    ) -> None:
        """生成向量并写入 vector store + 更新 DB 的 embedding 元信息"""
        try:
            embedder = get_embedder()
            vec_store = get_vector_store()

            vector = await embedder.embed(text)
            await vec_store.upsert(entity_id, entity_type, user_id, layer, text, vector)

            # 更新 DB 记录的 embedding 元信息（标记已生成向量）
            table = MemoryModel if entity_type == "atom" else MemoryScenarioModel

            def _run():
                with create_db_session() as db:
                    db.execute(
                        update(table)
                        .where(table.id == entity_id)
                        .values(
                            embedding_model=_settings.memory_embedding_model,
                            embedding_updated_at=app_now(),
                        )
                    )
                    db.commit()

            await asyncio.to_thread(_run)
        except Exception as e:
            _logger.debug(f"Embed 失败 {entity_type}:{entity_id}: {e}")

    # ── 存量去重 ──
    async def dedupe_user_memories(self, user_id: int, *, dry_run: bool = False) -> dict:
        """对既有 L1 记忆做一次相似度聚类去重。

        针对历史遗留的重复记忆（同一事实被蒸馏成 N 条）：向量相似度
        ≥ threshold 的归为一组，组内保留 importance 最高、更新的那条，
        其余删除（DB + FTS + 向量索引同步清理）。
        """
        def _fetch():
            with create_db_session() as db:
                return db.scalars(
                    select(MemoryModel)
                    .where(MemoryModel.user_id == user_id)
                    .where(MemoryModel.layer == "L1")
                    .order_by(MemoryModel.created_at.desc())
                    .limit(500)
                ).all()

        rows = await asyncio.to_thread(_fetch)
        if len(rows) < 2:
            return {"groups": 0, "removed": 0, "kept": len(rows), "embed_failed": 0}

        embedder = get_embedder()
        vectors: list[list[float] | None] = []
        embed_failed = 0
        for row in rows:
            try:
                vectors.append(await embedder.embed(row.content))
            except Exception:  # noqa: BLE001 -- 单条 embed 失败按 None 处理（余弦 0，不参与聚类）
                vectors.append(None)
                embed_failed += 1

        def _cosine(a: list[float] | None, b: list[float] | None) -> float:
            if not a or not b:
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            na = sum(x * x for x in a) ** 0.5
            nb = sum(y * y for y in b) ** 0.5
            return dot / (na * nb) if na and nb else 0.0

        # 贪心聚类：按（importance, 新旧）从优到劣遍历，与已保留组的代表
        # 相似度过高则归入该组待删
        order = sorted(
            range(len(rows)),
            key=lambda i: (-float(rows[i].importance or 0), i),
        )
        keep_indices: list[int] = []
        remove_ids: list[int] = []
        for i in order:
            if any(_cosine(vectors[i], vectors[j]) >= _DEDUPE_SIMILARITY_THRESHOLD for j in keep_indices):
                remove_ids.append(rows[i].id)
            else:
                keep_indices.append(i)

        removed = 0
        if not dry_run:
            for memory_id in remove_ids:
                try:
                    if await get_memory_service().delete_memory(memory_id, None):
                        removed += 1
                except Exception as e:  # noqa: BLE001 -- 单条失败不中断
                    _logger.warning(f"dedupe 删除 {memory_id} 失败: {e}")
        if embed_failed:
            # 失效必须可见：embed 大面积失败时聚类结果不可信
            _logger.warning(f"dedupe: {embed_failed}/{len(rows)} embed failed, result unreliable")
        return {
            "groups": len(keep_indices),
            "removed": removed if not dry_run else len(remove_ids),
            "kept": len(keep_indices),
            "embed_failed": embed_failed,
        }


    async def _aggregate_scenarios(self, user_id: int) -> None:
        """聚合 L1 atoms 为 L2 scenarios"""
        try:
            # 拉取最近未聚合的 atoms
            def _fetch_atoms():
                with create_db_session() as db:
                    return db.scalars(
                        select(MemoryModel)
                        .where(MemoryModel.user_id == user_id)
                        .where(MemoryModel.layer == "L1")
                        .where(MemoryModel.scenario_id.is_(None))
                        .order_by(MemoryModel.created_at.desc())
                        .limit(30)
                    ).all()

            atoms = await asyncio.to_thread(_fetch_atoms)
            if len(atoms) < 3:
                return  # 不足 3 条不聚合

            atoms_payload = [
                {"id": a.id, "content": a.content, "type": a.memory_type}
                for a in atoms
            ]

            from wuwei.core.message import SystemMessage, HumanMessage

            gateway = build_llm(role="fast", max_tokens=2048, timeout=90)
            prompt = SCENARIO_AGGREGATION_PROMPT.format(
                atoms_json=json.dumps(atoms_payload, ensure_ascii=False)
            )
            async with _llm_semaphore:
                resp = await gateway.generate(messages=[
                    SystemMessage(content="你是场景聚合器，只输出 JSON 数组。"),
                    HumanMessage(content=prompt),
                ])
            content = (resp.message.content or "[]").strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            scenarios = json.loads(content.strip())
            if not isinstance(scenarios, list):
                return

            for sc in scenarios:
                if isinstance(sc, dict):
                    await self._save_scenario(user_id, sc, atoms)

            _logger.info(f"L2 aggregated {len(scenarios)} scenarios for user {user_id}")
        except Exception as e:
            _logger.warning(f"L2 聚合失败: {e}")

    async def _save_scenario(self, user_id: int, sc: dict, source_atoms: list) -> None:
        atom_contents = sc.get("atom_contents", [])
        atom_ids = [a.id for a in source_atoms if a.content in atom_contents]

        def _run() -> int:
            with create_db_session() as db:
                row = MemoryScenarioModel(
                    user_id=user_id,
                    title=str(sc.get("title", "未命名场景"))[:128],
                    summary=str(sc.get("summary", "")),
                    tags_json=json.dumps(sc.get("tags", []), ensure_ascii=False),
                    atom_ids_json=json.dumps(atom_ids) if atom_ids else None,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                return row.id

        try:
            scenario_id = await asyncio.to_thread(_run)
        except Exception as e:
            _logger.warning(f"L2 scenario 保存失败: {e}")
            return

        # 关联 atoms 到 scenario
        if atom_ids:
            def _link():
                with create_db_session() as db:
                    db.execute(
                        update(MemoryModel)
                        .where(MemoryModel.id.in_(atom_ids))
                        .values(scenario_id=scenario_id)
                    )
                    db.commit()
            try:
                await asyncio.to_thread(_link)
            except Exception as e:
                _logger.warning(f"atom 关联 scenario 失败: {e}")

        # 异步向量索引 scenario summary
        asyncio.create_task(self._embed_and_upsert(
            scenario_id, "scenario", user_id, "L2", sc.get("summary", "")
        ))

    # ── L3 ──
    async def _update_persona(self, user_id: int) -> None:
        """基于全部 L1/L2 数据更新用户画像"""
        try:
            def _fetch_data():
                with create_db_session() as db:
                    atoms = db.scalars(
                        select(MemoryModel)
                        .where(MemoryModel.user_id == user_id)
                        .where(MemoryModel.layer == "L1")
                        .order_by(MemoryModel.created_at.desc())
                        .limit(50)
                    ).all()
                    scenarios = db.scalars(
                        select(MemoryScenarioModel)
                        .where(MemoryScenarioModel.user_id == user_id)
                        .order_by(MemoryScenarioModel.created_at.desc())
                        .limit(10)
                    ).all()
                    existing = db.scalars(
                        select(MemoryPersonaModel)
                        .where(MemoryPersonaModel.user_id == user_id)
                    ).first()
                    return atoms, scenarios, existing

            atoms, scenarios, existing = await asyncio.to_thread(_fetch_data)
            if not atoms and not scenarios:
                return

            from wuwei.core.message import SystemMessage, HumanMessage

            gateway = build_llm(role="fast", max_tokens=2048, timeout=90)

            existing_profile: dict[str, Any] = {}
            if existing:
                existing_profile = {
                    "identity": json.loads(existing.identity_json or "{}"),
                    "preferences": json.loads(existing.preferences_json or "{}"),
                    "tech_stack": json.loads(existing.tech_stack_json or "[]"),
                    "goals": json.loads(existing.goals_json or "[]"),
                    "projects": json.loads(existing.projects_json or "[]"),
                }

            prompt = PERSONA_UPDATE_PROMPT.format(
                existing=json.dumps(existing_profile, ensure_ascii=False),
                atoms=json.dumps(
                    [{"content": a.content, "type": a.memory_type} for a in atoms],
                    ensure_ascii=False,
                ),
                scenarios=json.dumps(
                    [{"title": s.title, "summary": s.summary} for s in scenarios],
                    ensure_ascii=False,
                ),
            )
            async with _llm_semaphore:
                resp = await gateway.generate(messages=[
                    SystemMessage(content="你是用户画像建模器，只输出 JSON 对象。"),
                    HumanMessage(content=prompt),
                ])
            content = (resp.message.content or "{}").strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            profile = json.loads(content.strip())

            await self._save_persona(user_id, profile, existing)
            _logger.info(f"L3 persona updated for user {user_id}")
        except Exception as e:
            _logger.warning(f"L3 画像更新失败: {e}")

    async def _save_persona(self, user_id: int, profile: dict, existing) -> None:
        def _run():
            with create_db_session() as db:
                if existing:
                    existing.identity_json = json.dumps(
                        profile.get("identity", {}), ensure_ascii=False
                    )
                    existing.preferences_json = json.dumps(
                        profile.get("preferences", {}), ensure_ascii=False
                    )
                    existing.tech_stack_json = json.dumps(
                        profile.get("tech_stack", []), ensure_ascii=False
                    )
                    existing.goals_json = json.dumps(
                        profile.get("goals", []), ensure_ascii=False
                    )
                    existing.projects_json = json.dumps(
                        profile.get("projects", []), ensure_ascii=False
                    )
                    existing.version += 1
                else:
                    db.add(MemoryPersonaModel(
                        user_id=user_id,
                        identity_json=json.dumps(
                            profile.get("identity", {}), ensure_ascii=False
                        ),
                        preferences_json=json.dumps(
                            profile.get("preferences", {}), ensure_ascii=False
                        ),
                        tech_stack_json=json.dumps(
                            profile.get("tech_stack", []), ensure_ascii=False
                        ),
                        goals_json=json.dumps(
                            profile.get("goals", []), ensure_ascii=False
                        ),
                        projects_json=json.dumps(
                            profile.get("projects", []), ensure_ascii=False
                        ),
                    ))
                db.commit()

        try:
            await asyncio.to_thread(_run)
        except Exception as e:
            _logger.warning(f"画像保存失败: {e}")


def _parse_extraction_json(raw: str | None) -> list[dict]:
    """解析 LLM 提取输出。新格式是 {"memories": [...]}，兼容旧的裸数组。"""
    if not raw:
        return []
    content = raw.strip()
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    try:
        parsed = json.loads(content.strip())
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get("memories", [])
    return parsed if isinstance(parsed, list) else []


_pipeline_singleton: MemoryPipeline | None = None


def get_pipeline() -> MemoryPipeline:
    """获取 pipeline 单例"""
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = MemoryPipeline()
    return _pipeline_singleton


# ── Prompts ──

ATOM_EXTRACTION_PROMPT = """你是用户的长期记忆管理员。从下面这轮对话中提取**值得跨会话记住**的信息。

只提取这几类（每条必须是对未来对话有用的稳定事实）：
- fact: 用户身份信息（姓名、职业、团队、所在产品/项目背景）
- preference: 稳定的偏好（技术选型倾向、风格偏好、明确表达的喜好）
- tech: 用户的技术栈（语言、框架、工具）
- project: 用户项目的**背景事实**（项目叫什么、做什么、有哪些模块）

## 什么必须跳过（同样重要）

以下内容**一条都不要提取**：
- 进行时流水："正在做X面板"、"正在开发Y界面" —— 这类一次性任务状态下一个会话就过时了；只在引入**新的**项目/模块名称时提取项目背景本身
- 本次会话就能完成的操作细节：点了什么按钮、选了什么选项、调了什么工具、页面长什么样
- 对话里已经解决的一次性问题（报错修复、临时配置）
- AI 回复中对用户原话的复述、客套话、总结
- 与「已有记忆」语义相同的内容 —— 换了个说法也算重复

## 已有记忆（这些事实系统已经记住了，不要重复提取）

{existing_memories}

规则：
- 若本轮对话与某条已有记忆**语义相同**（只是措辞不同）→ 不要输出
- 若本轮对话在已有记忆之上**有真正的新增细节**（新模块、新决定、新变化）→ 只提取新增的那部分
- 每条记忆必须自包含（脱离本轮对话也能看懂），简短明确
- 最多输出 3 条；没有值得记的就输出空数组

## 本轮对话

{conversation}

输出 JSON 对象（不要输出其他文字）：
{{"memories": [
  {{"content": "简短明确的记忆内容", "type": "fact|preference|tech|project", "importance": 0.1-1.0}}
]}}

没有值得提取的信息时输出 {{"memories": []}}。"""

SCENARIO_AGGREGATION_PROMPT = """基于以下 L1 atom 列表，识别可聚合的场景块（L2 scenario）。

聚合规则：
- 同一项目/主题/活动周期的 atoms 合并为一个 scenario
- 每个 scenario 必须包含至少 2 个 atom
- 标题简洁（≤20字），summary 概括场景背景

atoms:
{atoms_json}

输出 JSON 数组：
[{{
  "title": "场景标题",
  "summary": "场景摘要（100-200字）",
  "atom_contents": ["原 atom 内容1", "原 atom 内容2"],
  "tags": ["tag1", "tag2"]
}}]

如果 atoms 之间关联度低，返回空数组 []。"""

PERSONA_UPDATE_PROMPT = """基于用户的现有画像和历史记忆，更新用户长期画像（L3）。

现有画像：
{existing}

近期 atoms：
{atoms}

近期 scenarios：
{scenarios}

输出 JSON 对象（合并已有 + 新增信息，去重保持简洁）：
{{
  "identity": {{"name": "", "role": "", "location": "", "age_group": ""}},
  "preferences": {{"ui_style": "", "communication": "", "likes": [], "dislikes": []}},
  "tech_stack": ["Python", "FastAPI", "Vue 3"],
  "goals": ["短期目标1", "长期目标2"],
  "projects": [{{"name": "", "status": "active|paused|done", "summary": ""}}]
}}

字段留空时返回空字符串或空数组。"""
