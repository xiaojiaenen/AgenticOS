"""pgvector 可选加速路径（数据库评估文档 阶段 2：新能力优先按 PG 设计）。

**形态**：纯库 + 可选 PG 扩展（不新增任何外部系统，3F.0 红线）。PG 是
本机已装/生产已部署的数据库，pgvector 是它上面的一个扩展。

**语义**：
- ``pgvector_available()``：探测扩展 + 列类型可用性（connection 级缓存）；
  探测失败 / 扩展不存在 / 非 PG 方言 → False，调用方自动走应用侧余弦。
- ``similarity_search_chunks()``：把「拉全量 embedding → 应用侧逐行余弦」
  换成库内 ``embedding <=> :query`` 排序（HNSW/IVFFlat 索引自动生效）。
  余弦距离转相似度：``1 - distance``（pgvector cosine operator 的值域
  [0, 2]，0 = 同向）。
- 未迁移到 vector 列的存量库（embedding 仍是 bytes/Text）探测不通过，
  行为与旧路径完全一致 —— 零迁移负担。

启用方式（生产 PG）：
    CREATE EXTENSION IF NOT EXISTS vector;
    ALTER TABLE kb_chunks ALTER COLUMN embedding TYPE vector USING ...
    CREATE INDEX ... USING hnsw (embedding vector_cosine_ops);
之后检索代码无需任何改动（本模块探测到 vector 列自动切换）。
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy import bindparam, text

logger = logging.getLogger("agenticos.knowledge.pgvector")

#: connection 级探测缓存（id(conn) → bool），避免每次查询都 probe
_probe_cache: dict[int, bool] = {}
_probe_lock = threading.Lock()


def pgvector_available(db) -> bool:
    """当前 session 的连接上 pgvector（vector 列类型）是否可用。

    条件（全部满足才 True）：
    1. 方言是 postgresql；
    2. ``'vector'`` 类型注册存在（``pg_type`` 查得到，即扩展已建）；
    3. ``kb_chunks.embedding`` 的数据类型是 vector（存量库未迁移 → False）。
    """
    key = id(db)
    with _probe_lock:
        cached = _probe_cache.get(key)
    if cached is not None:
        return cached

    ok = False
    try:
        if db.get_bind().dialect.name != "postgresql":
            ok = False
        else:
            type_exists = db.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector')")
            ).scalar()
            if type_exists:
                col_type = db.execute(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = 'kb_chunks' AND column_name = 'embedding'"
                    )
                ).scalar()
                ok = str(col_type or "").lower() == "vector"
    except Exception as e:  # noqa: BLE001 —— 探测失败 = 不可用，别挡检索
        logger.debug("pgvector probe failed: %s", e)
        ok = False

    with _probe_lock:
        _probe_cache[key] = ok
    if ok:
        logger.info("pgvector 加速路径已启用（kb_chunks.embedding 是 vector 列）")
    return ok


def reset_probe_cache() -> None:
    """清探测缓存（测试用 / 迁移刚执行完的进程内刷新）。"""
    with _probe_lock:
        _probe_cache.clear()


def similarity_search_chunks(
    db,
    *,
    query_vector: list[float],
    knowledge_base_ids: list[int],
    top_k: int,
    min_similarity: float,
    page_type: str | None = None,
) -> list[tuple[int, float, str]]:
    """pgvector 库内余弦检索（段级）。

    Returns:
        ``[(page_id, similarity, chunk_content)]``，按相似度降序、已按
        ``min_similarity`` 过滤、页级 max 聚合后按 ``top_k`` 截断 —— 与
        应用侧余弦路径的返回口径一致，调用方无需感知后端差异。

    Raises:
        任何 SQL 异常原样抛出（调用方捕获后降级到应用侧余弦）。
    """
    vector_literal = "[" + ",".join(f"{v:.7g}" for v in query_vector) + "]"
    page_type_filter = "AND p.page_type = :page_type" if page_type else ""

    sql = text(
        """
        SELECT c.page_id,
               1 - (c.embedding <=> CAST(:q AS vector)) AS similarity,
               c.content
        FROM kb_chunks c
        JOIN kb_wiki_pages p ON p.id = c.page_id
        WHERE c.knowledge_base_id IN :kb_ids
          AND c.embedding IS NOT NULL
          AND p.is_active = true
          {page_type_filter}
        ORDER BY c.embedding <=> CAST(:q AS vector)
        LIMIT :top_k
        """.replace("{page_type_filter}", page_type_filter)
    ).bindparams(bindparam("kb_ids", expanding=True))

    params: dict = {
        "q": vector_literal,
        "kb_ids": list(knowledge_base_ids),
        # 页级 max 聚合前多取，防止同页多段挤占名额
        "top_k": max(1, int(top_k) * 4),
    }
    if page_type:
        params["page_type"] = page_type

    rows = db.execute(sql, params).all()
    out: list[tuple[int, float, str]] = []
    seen: dict[int, float] = {}
    for page_id, similarity, content in rows:
        sim = float(similarity or 0.0)
        if sim < min_similarity:
            continue
        pid = int(page_id)
        # 页级 max 聚合（同一页取最佳段）
        if pid not in seen or sim > seen[pid]:
            seen[pid] = sim
            out.append((pid, sim, content or ""))
    out.sort(key=lambda item: item[1], reverse=True)
    return out[: max(1, int(top_k))]
