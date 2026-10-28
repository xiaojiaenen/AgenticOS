"""知识库冲突**定期巡检**（与编译期冲突检测互补）。

编译期的 ``detect_conflicts_sync`` 只做「新页面 vs 已有页面」的单向比对，
因此有一个天然盲区：两个都已经存在的页面若从没在同一次编译里相遇
（历史导入、分两批上传、批量重建索引），它们之间的矛盾**永远不会被发现**。

本模块对整个知识库做一次全量配对扫描来补这个洞：

1. **候选生成**：标题 bigram 倒排索引 → 只保留共享 bigram ≥2 的页面对，
   避免 O(n²) 全量两两比对（万页库也能在秒级出候选）；
2. **同主题确认**：正文 bigram Jaccard > ``CONTENT_OVERLAP`` 才继续，
   过滤「标题像但讲的是两件事」的假阳性；
3. **规则判定**：复用 ``WikiCompiler._check_conflict_rule``，**双向各跑一次**
   （该规则不对称：「新内容含否定、旧内容含肯定」才算冲突）；
4. **去重落库**：同一对页面已存在 pending 的 ``conflict_resolution`` 审核项时跳过，
   所以巡检可以反复跑而不会把复核队列刷满。

巡检**不修改任何页面内容**，只往 ``kb_review_items`` 写待人工裁决的条目。
"""

from __future__ import annotations

import json
import logging
from itertools import combinations
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KBReviewItemModel, KBWikiPageModel
from app.services.knowledge.tokenizer import char_bigrams
from app.services.knowledge.wiki_compiler import WikiCompiler, WikiPageDraft

logger = logging.getLogger("knowledge.conflict_scan")

# 单库单次扫描的页面上限：超出部分本轮流式跳过（返回 truncated 标记），
# 避免一个超大知识库把 worker 卡满（arq job_timeout 默认 600s）。
DEFAULT_MAX_PAGES = 800

# 标题相似度下限（bigram Jaccard）。0.5 相当于「标题有一半的字面重叠」
TITLE_SIMILARITY = 0.5

# 正文关键词重叠下限。0.12 是为了容纳「同一主题用不同措辞写」的情况，
# 再低就会把同领域但不相干的页面配到一起。
CONTENT_OVERLAP = 0.12

# 每个页面最多保留多少个候选对（按共享 bigram 数降序）
MAX_CANDIDATES_PER_PAGE = 6

# 参与去重比对的审核项状态：已裁决的不再拦，允许复检发现"又冲突了"
_BLOCKING_STATUSES = ("pending",)

# 审核项标题前缀，便于前端与去重逻辑识别「巡检产出」
_REVIEW_TITLE_PREFIX = "内容冲突"


def _bigrams(text: str) -> set[str]:
    """字符级 bigram 集合（委托 tokenizer，避免与编译器各写一套漂移）。"""
    return char_bigrams(text)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _load_pages(db: Session, kb_id: int, max_pages: int) -> tuple[list[dict], bool]:
    """加载待扫描页面（只取比对需要的字段，不拉整段正文进 ORM 会话缓存）。"""
    stmt = (
        select(
            KBWikiPageModel.id,
            KBWikiPageModel.title,
            KBWikiPageModel.page_type,
            KBWikiPageModel.content,
        )
        .where(
            KBWikiPageModel.knowledge_base_id == kb_id,
            KBWikiPageModel.is_active.is_(True),
        )
        .order_by(KBWikiPageModel.id)
    )
    rows = db.execute(stmt).all()
    truncated = len(rows) > max_pages
    pages = [
        {"id": int(r[0]), "title": r[1] or "", "page_type": r[2] or "", "content": r[3] or ""}
        for r in rows[:max_pages]
    ]
    return pages, truncated


def _candidate_pairs(pages: list[dict]) -> list[tuple[int, int]]:
    """标题 bigram 倒排 → 共享 bigram 数 ≥2 的候选对（按相似度降序取前 N）。"""
    index: dict[str, list[int]] = {}
    title_bigrams: list[set[str]] = []
    for idx, page in enumerate(pages):
        grams = _bigrams(page["title"])
        title_bigrams.append(grams)
        for gram in grams:
            index.setdefault(gram, []).append(idx)

    scored: dict[tuple[int, int], int] = {}
    for posting in index.values():
        if len(posting) < 2:
            continue
        for a, b in combinations(sorted(posting), 2):
            scored[(a, b)] = scored.get((a, b), 0) + 1

    # 每页只保留共享 bigram 最多的若干候选，避免"通用词标题"把候选数炸开
    per_page: dict[int, list[tuple[int, int]]] = {}
    for (a, b), shared in scored.items():
        if shared < 2:
            continue
        per_page.setdefault(a, []).append((shared, b))
        per_page.setdefault(b, []).append((shared, a))

    chosen: set[tuple[int, int]] = set()
    for idx, cands in per_page.items():
        for _shared, other in sorted(cands, reverse=True)[:MAX_CANDIDATES_PER_PAGE]:
            chosen.add((min(idx, other), max(idx, other)))

    # 标题相似度二次过滤 + 按相似度降序
    ranked: list[tuple[float, int, int]] = []
    for a, b in chosen:
        similarity = _jaccard(title_bigrams[a], title_bigrams[b])
        if similarity >= TITLE_SIMILARITY:
            ranked.append((similarity, a, b))
    ranked.sort(reverse=True)
    return [(a, b) for _sim, a, b in ranked]


def _existing_pairs(db: Session, kb_id: int) -> set[frozenset[int]]:
    """已存在待裁决审核项的页面对集合（用于幂等去重）。"""
    rows = db.execute(
        select(KBReviewItemModel.related_page_ids_json).where(
            KBReviewItemModel.knowledge_base_id == kb_id,
            KBReviewItemModel.review_type == "conflict_resolution",
            KBReviewItemModel.status.in_(_BLOCKING_STATUSES),
        )
    ).all()

    pairs: set[frozenset[int]] = set()
    for (raw,) in rows:
        try:
            ids = [int(i) for i in json.loads(raw or "[]")]
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        # 只有单页的旧记录（编译期产出）无法判断另一侧，按「与该页相关」全部拦掉
        for page_id in ids:
            pairs.add(frozenset({page_id}))
        if len(ids) >= 2:
            pairs.add(frozenset(ids[:2]))
    return pairs


def _pair_already_flagged(
    existing: set[frozenset[int]], a: int, b: int
) -> bool:
    """该页面对是否已被待裁决项覆盖。

    编译期产出的审核项只记了已有页 id（新页当时还没落库），所以单页记录
    也要视为「已标记」——宁可漏报一次，也不要把复核队列刷重复。
    """
    return frozenset({a, b}) in existing or frozenset({a}) in existing or frozenset({b}) in existing


def _build_review_item(kb_id: int, a: dict, b: dict, nature: str) -> KBReviewItemModel:
    return KBReviewItemModel(
        knowledge_base_id=kb_id,
        review_type="conflict_resolution",
        title=f"{_REVIEW_TITLE_PREFIX}: {a['title']} / {b['title']}"[:500],
        description=(
            f"定期巡检发现：页面「{a['title']}」与「{b['title']}」存在矛盾 —— {nature}\n"
            f"（由冲突巡检自动产出，不修改任何正文，请人工确认后裁决）"
        ),
        options_json=json.dumps(
            [
                {"action": "adopt_new", "label": "采纳前者"},
                {"action": "keep_existing", "label": "保留后者"},
                {"action": "merge", "label": "合并两者"},
                {"action": "skip", "label": "跳过（误报）"},
            ],
            ensure_ascii=False,
        ),
        related_page_ids_json=json.dumps([a["id"], b["id"]]),
        related_document_ids_json="[]",
    )


def scan_knowledge_base(
    db: Session,
    kb_id: int,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    use_llm: bool = False,
) -> dict[str, Any]:
    """扫描单个知识库的跨页面矛盾，把新发现写入复核队列。

    Args:
        db: 数据库会话（由调用方控制事务，本函数只 ``flush`` 不 ``commit``）。
        kb_id: 知识库 ID。
        max_pages: 本轮参与扫描的页面上限。
        use_llm: 规则未命中时是否再让 LLM 判一次（默认关闭，避免定时任务烧 token）。

    Returns:
        统计字典：``pages_scanned`` / ``pairs_checked`` / ``conflicts_found`` /
        ``created`` / ``skipped_existing`` / ``truncated``。
    """
    stats: dict[str, Any] = {
        "knowledge_base_id": kb_id,
        "pages_scanned": 0,
        "pairs_checked": 0,
        "candidate_pairs": 0,
        "conflicts_found": 0,
        "created": 0,
        "skipped_existing": 0,
        "truncated": False,
    }

    pages, truncated = _load_pages(db, kb_id, max_pages)
    stats["pages_scanned"] = len(pages)
    stats["truncated"] = truncated
    if len(pages) < 2:
        return stats

    pairs = _candidate_pairs(pages)
    stats["candidate_pairs"] = len(pairs)
    if not pairs:
        return stats

    # 规则判定不依赖 LLM；use_llm=False 时传 None 让编译器跳过 LLM 分支
    compiler = WikiCompiler(None if not use_llm else _gateway_or_none())

    existing = _existing_pairs(db, kb_id)

    for a_idx, b_idx in pairs:
        page_a, page_b = pages[a_idx], pages[b_idx]

        # 同主题确认：正文关键词重叠太低 → 不是同一个话题，跳过
        if _jaccard(_bigrams(page_a["content"]), _bigrams(page_b["content"])) < CONTENT_OVERLAP:
            continue

        stats["pairs_checked"] += 1

        if _pair_already_flagged(existing, page_a["id"], page_b["id"]):
            stats["skipped_existing"] += 1
            continue

        conflict = _detect_both_ways(compiler, page_a, page_b)
        if conflict is None:
            continue

        stats["conflicts_found"] += 1
        db.add(_build_review_item(kb_id, page_a, page_b, conflict))
        existing.add(frozenset({page_a["id"], page_b["id"]}))
        stats["created"] += 1

    if stats["created"]:
        db.flush()

    return stats


def _gateway_or_none():
    """可选 LLM 网关；未配置时返回 None（自动退化为纯规则）。"""
    try:
        from app.services.task_queue import build_llm_gateway

        return build_llm_gateway()
    except Exception:  # noqa: BLE001 —— LLM 不可用不得让巡检失败
        logger.debug("conflict scan: LLM gateway unavailable, rule-only", exc_info=True)
        return None


def _detect_both_ways(compiler: WikiCompiler, page_a: dict, page_b: dict):
    """双向各跑一次规则判定。

    ``_check_conflict_rule(new, existing)`` 的逻辑不对称：它检查「new 里的否定词
    vs existing 里的肯定词」。只跑一个方向会漏掉反过来的情况，所以两侧都试。
    """
    for left, right in ((page_a, page_b), (page_b, page_a)):
        draft = WikiPageDraft(
            title=left["title"],
            page_type=left["page_type"],
            content=left["content"],
        )
        conflict = compiler._check_conflict_rule(draft, right)  # noqa: SLF001 —— 复用同一条规则，避免两套判定漂移
        if conflict is not None:
            conflict.existing_page_id = right["id"]
            conflict.existing_page_title = right["title"]
            return conflict
    return None


def scan_all_knowledge_bases(
    db: Session,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    knowledge_base_ids: Iterable[int] | None = None,
) -> dict[str, Any]:
    """巡检所有活跃知识库（供 arq cron 调用）。"""
    from app.db.models import KnowledgeBaseModel

    stmt = select(KnowledgeBaseModel.id).where(KnowledgeBaseModel.is_active.is_(True))
    if knowledge_base_ids is not None:
        stmt = stmt.where(KnowledgeBaseModel.id.in_(list(knowledge_base_ids)))
    kb_ids = [int(row[0]) for row in db.execute(stmt).all()]

    total = {
        "knowledge_bases": 0,
        "pages_scanned": 0,
        "pairs_checked": 0,
        "created": 0,
        "skipped_existing": 0,
        "per_kb": [],
    }
    for kb_id in kb_ids:
        try:
            stats = scan_knowledge_base(db, kb_id, max_pages=max_pages)
        except Exception as exc:  # noqa: BLE001 —— 单库失败不影响其他库
            logger.warning("conflict scan failed for kb=%s: %s", kb_id, exc, exc_info=True)
            continue
        total["knowledge_bases"] += 1
        total["pages_scanned"] += stats["pages_scanned"]
        total["pairs_checked"] += stats["pairs_checked"]
        total["created"] += stats["created"]
        total["skipped_existing"] += stats["skipped_existing"]
        total["per_kb"].append(stats)

    return total
