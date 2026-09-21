"""BM25 检索：FTS5（SQLite）/ MATCH AGAINST（MySQL）抽象层。

自动按 DATABASE_URL 选择后端：
- sqlite: FTS5 虚拟表 + bm25() 函数
- mysql: FULLTEXT 索引 + MATCH AGAINST
- 其他: 降级到 SQLite FTS5
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from app.db.session import create_db_session, engine

_logger = logging.getLogger("memory_bm25")


def _detect_backend() -> str:
    dialect = engine.dialect.name
    if dialect == "sqlite":
        return "sqlite_fts"
    if dialect == "mysql":
        return "mysql_match"
    return "sqlite_fts"


class MemoryBM25Backend:
    """BM25 抽象基类"""

    async def search(
        self,
        user_id: int,
        query: str,
        layers: tuple[str, ...],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def rebuild_index(self) -> None:
        """重建索引（首次启动或数据迁移时调用）"""
        raise NotImplementedError


class SQLiteFTSBackend(MemoryBM25Backend):
    """SQLite FTS5 虚拟表"""

    _initialized = False

    async def _ensure_index(self) -> None:
        if self._initialized:
            return

        def _run():
            with engine.begin() as conn:
                # 创建 FTS5 虚拟表（external content 模式）
                conn.execute(text("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(
                        content,
                        content='memories',
                        content_rowid='id',
                        tokenize='unicode61'
                    )
                """))
                # 首次全量同步（仅未索引的行）
                conn.execute(text("""
                    INSERT INTO memories_fts(rowid, content)
                    SELECT id, content FROM memories
                    WHERE content IS NOT NULL
                      AND id NOT IN (SELECT rowid FROM memories_fts)
                """))
        try:
            await asyncio.to_thread(_run)
            self._initialized = True
        except Exception as e:
            _logger.warning(f"FTS5 索引初始化失败: {e}")
            self._initialized = True  # 避免重复尝试

    async def search(
        self,
        user_id: int,
        query: str,
        layers: tuple[str, ...],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        await self._ensure_index()

        if not query.strip():
            return []

        # FTS5 查询：使用 OR 提高召回
        fts_query = " OR ".join(query.split())
        layer_params = {f"layer_{i}": layer for i, layer in enumerate(layers)}
        in_clause = ", ".join(f":layer_{i}" for i in range(len(layers)))

        sql = text(f"""
            SELECT m.id, m.content, m.memory_type, m.layer, m.scenario_id,
                   bm25(memories_fts) AS score
            FROM memories_fts
            JOIN memories m ON m.id = memories_fts.rowid
            WHERE memories_fts MATCH :query
              AND m.user_id = :user_id
              AND m.layer IN ({in_clause})
            ORDER BY score ASC
            LIMIT :limit
        """)

        def _run():
            with create_db_session() as db:
                return db.execute(sql, {
                    "query": fts_query,
                    "user_id": user_id,
                    **layer_params,
                    "limit": limit,
                }).fetchall()

        try:
            rows = await asyncio.to_thread(_run)
            return [{
                "id": r[0], "content": r[1], "memory_type": r[2],
                "layer": r[3], "scenario_id": r[4],
                "score": float(r[5]),
            } for r in rows]
        except Exception as e:
            _logger.warning(f"SQLite FTS5 查询失败: {e}")
            return []

    async def rebuild_index(self) -> None:
        def _run():
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM memories_fts"))
                conn.execute(text("""
                    INSERT INTO memories_fts(rowid, content)
                    SELECT id, content FROM memories
                    WHERE content IS NOT NULL
                """))
        try:
            await asyncio.to_thread(_run)
            _logger.info("FTS5 索引已重建")
        except Exception as e:
            _logger.warning(f"FTS5 重建失败: {e}")


class MySQLMatchBackend(MemoryBM25Backend):
    """MySQL FULLTEXT 索引"""

    _initialized = False

    async def _ensure_index(self) -> None:
        if self._initialized:
            return

        def _run():
            with engine.begin() as conn:
                # 检查是否为 MySQL 8+ 且支持 ngram
                try:
                    # 尝试创建 ngram FULLTEXT 索引（支持中文）
                    conn.execute(text(
                        "CREATE FULLTEXT INDEX idx_memories_content_ft_ngram "
                        "ON memories(content) WITH PARSER ngram"
                    ))
                    _logger.info("Created ngram FULLTEXT index for Chinese support")
                except Exception:
                    # 回退到普通 FULLTEXT
                    try:
                        conn.execute(text(
                            "CREATE FULLTEXT INDEX idx_memories_content_ft "
                            "ON memories(content)"
                        ))
                    except Exception:
                        pass  # 已存在
        try:
            await asyncio.to_thread(_run)
            self._initialized = True
        except Exception as e:
            _logger.warning(f"MySQL FULLTEXT 索引创建失败: {e}")
            self._initialized = True

    async def search(
        self,
        user_id: int,
        query: str,
        layers: tuple[str, ...],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        await self._ensure_index()

        if not query.strip():
            return []

        # MySQL IN 子句需要单独的参数
        layer_params = {f"layer_{i}": layer for i, layer in enumerate(layers)}
        in_clause = ", ".join(f":layer_{i}" for i in range(len(layers)))

        # 判断查询是否包含中文，中文使用 LIKE 回退
        import re
        has_chinese = bool(re.search(r'[一-鿿]', query))

        if has_chinese:
            # 中文查询：将查询拆分为单个词，使用 OR 连接
            # 这样 "用户偏好 技术栈" 会匹配包含 "用户偏好" 或 "技术栈" 的内容
            words = [w.strip() for w in query.split() if w.strip()]
            if not words:
                return []

            # 为每个词创建 LIKE 条件
            like_conditions = []
            like_params = {}
            for i, word in enumerate(words):
                param_name = f"like_{i}"
                like_conditions.append(f"content LIKE :{param_name}")
                like_params[param_name] = f"%{word}%"

            where_clause = " OR ".join(like_conditions)

            sql = text(f"""
                SELECT id, content, memory_type, layer, scenario_id,
                       1.0 AS score
                FROM memories
                WHERE user_id = :user_id
                  AND layer IN ({in_clause})
                  AND ({where_clause})
                ORDER BY id DESC
                LIMIT :limit
            """)
            params = {
                "user_id": user_id,
                **like_params,
                **layer_params,
                "limit": limit,
            }
        else:
            # 英文查询：使用 FULLTEXT
            sql = text(f"""
                SELECT id, content, memory_type, layer, scenario_id,
                       MATCH(content) AGAINST(:query IN BOOLEAN MODE) AS score
                FROM memories
                WHERE user_id = :user_id
                  AND layer IN ({in_clause})
                  AND MATCH(content) AGAINST(:query IN BOOLEAN MODE)
                ORDER BY score DESC
                LIMIT :limit
            """)
            params = {
                "query": query, "user_id": user_id,
                **layer_params, "limit": limit,
            }

        def _run():
            with create_db_session() as db:
                return db.execute(sql, params).fetchall()

        try:
            rows = await asyncio.to_thread(_run)
            return [{
                "id": r[0], "content": r[1], "memory_type": r[2],
                "layer": r[3], "scenario_id": r[4],
                "score": float(r[5]),
            } for r in rows]
        except Exception as e:
            _logger.warning(f"MySQL 查询失败: {e}")
            return []

    async def rebuild_index(self) -> None:
        # MySQL FULLTEXT 自动维护，无需重建
        pass


_backend_singleton: MemoryBM25Backend | None = None


def get_bm25_backend() -> MemoryBM25Backend:
    """获取 BM25 后端单例"""
    global _backend_singleton
    if _backend_singleton is None:
        kind = _detect_backend()
        if kind == "mysql_match":
            _backend_singleton = MySQLMatchBackend()
        else:
            _backend_singleton = SQLiteFTSBackend()
    return _backend_singleton
