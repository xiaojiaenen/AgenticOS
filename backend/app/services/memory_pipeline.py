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
import json
import logging
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
from app.services.memory_embedder import get_embedder
from app.services.memory_vector_store import get_vector_store

_logger = logging.getLogger("memory_pipeline")
_settings = get_settings()


class MemoryPipeline:
    """异步蒸馏 Pipeline"""

    def __init__(self) -> None:
        # user_id -> 累计轮次（内存计数，重启后从 0 开始；可接受）
        self._turn_counts: dict[int, int] = {}

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
        self._turn_counts[user_id] = self._turn_counts.get(user_id, 0) + 1
        turn = self._turn_counts[user_id]

        # 2. L1 提取（每轮都执行，复用旧 prompt）
        atoms = await self._extract_atoms(user_message, assistant_message)
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
    async def _extract_atoms(self, user_msg: str, assistant_msg: str) -> list[dict]:
        """LLM 提取事实/偏好/技术栈/项目"""
        try:
            from wuwei.llm import LLMGateway
            from wuwei.core.message import SystemMessage, HumanMessage

            gateway = LLMGateway.from_env()
            prompt = ATOM_EXTRACTION_PROMPT.format(
                user_msg=user_msg,
                assistant_msg=assistant_msg[:1500],
            )
            resp = await gateway.generate(messages=[
                SystemMessage(content="你是记忆提取器，只输出 JSON 数组。"),
                HumanMessage(content=prompt),
            ])
            content = (resp.message.content or "[]").strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            atoms = json.loads(content.strip())
            return atoms if isinstance(atoms, list) else []
        except Exception as e:
            _logger.debug(f"L1 提取失败: {e}")
            return []

    async def _save_atom(self, user_id: int, atom: dict) -> int | None:
        """保存 L1 atom，同时异步生成向量写入 vector store"""
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
                    tags_json=json.dumps(["auto-extracted"], ensure_ascii=False),
                    source="auto",
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

    # ── L2 ──
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

            from wuwei.llm import LLMGateway
            from wuwei.core.message import SystemMessage, HumanMessage

            gateway = LLMGateway.from_env()
            prompt = SCENARIO_AGGREGATION_PROMPT.format(
                atoms_json=json.dumps(atoms_payload, ensure_ascii=False)
            )
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

            from wuwei.llm import LLMGateway
            from wuwei.core.message import SystemMessage, HumanMessage

            gateway = LLMGateway.from_env()

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


_pipeline_singleton: MemoryPipeline | None = None


def get_pipeline() -> MemoryPipeline:
    """获取 pipeline 单例"""
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = MemoryPipeline()
    return _pipeline_singleton


# ── Prompts ──

ATOM_EXTRACTION_PROMPT = """从以下对话中提取用户的关键信息作为记忆 atom。

只提取以下类型：
- fact: 用户的身份信息（姓名、职业、所在地等）
- preference: 用户的偏好（喜欢什么、不喜欢什么、审美倾向）
- tech: 用户的技术栈（使用什么语言、框架、工具）
- project: 用户的项目信息（在做什么项目、遇到什么问题）

用户消息: {user_msg}
AI 回复: {assistant_msg}

输出 JSON 数组，每个元素：
{{
  "content": "简短明确的记忆内容",
  "type": "fact|preference|tech|project",
  "importance": 0.1-1.0
}}

如果没有值得提取的信息，返回 []。

示例：
[
  {{"content": "用户叫张三", "type": "fact", "importance": 0.9}},
  {{"content": "用户偏好 Vue 3 + TypeScript", "type": "tech", "importance": 0.7}}
]"""

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
