"""知识库召回测试。

借鉴 Dify / Cherry Studio 的做法：用一个**问题集**对知识库跑批检索，
报告每个问题的命中情况、排序与得分。价值在于把"调召回参数"从试错变成
可复现的回归——改切片策略、改 TopK、改阈值后重跑，直接对比命中率变化。

问题集优先取知识库已有的 review items（人工审核时登记的"标准问题"），
没有则退回该知识库页面的标题自动生成探针问题。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("knowledge.recall_test")


@dataclass
class RecallCase:
    """单条测试用例。"""

    question: str
    # 期望命中的页面标题片段（任一命中即算命中）；为空表示只统计排序
    expect_titles: list[str] = field(default_factory=list)
    source: str = "auto"


@dataclass
class RecallCaseResult:
    question: str
    hits: list[dict[str, Any]]
    matched: bool
    rank_of_first_expected: int | None
    score_of_first_expected: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "hits": self.hits,
            "matched": self.matched,
            "rank_of_first_expected": self.rank_of_first_expected,
            "score_of_first_expected": self.score_of_first_expected,
        }


@dataclass
class RecallReport:
    total: int
    matched: int
    hit_rate: float
    avg_rank: float | None
    cases: list[RecallCaseResult]
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "matched": self.matched,
            "hit_rate": round(self.hit_rate, 4),
            "avg_rank": round(self.avg_rank, 2) if self.avg_rank is not None else None,
            "cases": [c.to_dict() for c in self.cases],
            "params": self.params,
        }


def build_probe_cases(knowledge_base_id: int, limit: int = 8) -> list[RecallCase]:
    """用知识库内页面标题生成探针问题集（无人工问题集时的兜底）。

    直接查库拿标题，避免本模块依赖检索层；标题即期望命中项，
    因此报告能给出确定性的"命中率"而非只看有没有结果。
    """
    from sqlalchemy import select

    from app.db.models import KBWikiPageModel, KnowledgeBaseModel
    from app.db.session import create_db_session

    def _load() -> list[RecallCase]:
        with create_db_session() as db:
            kb = db.get(KnowledgeBaseModel, knowledge_base_id)
            if kb is None:
                return []
            pages = db.scalars(
                select(KBWikiPageModel.title)
                .where(
                    KBWikiPageModel.knowledge_base_id == knowledge_base_id,
                    KBWikiPageModel.is_active.is_(True),
                )
                .order_by(KBWikiPageModel.id.asc())
                .limit(limit)
            ).all()
            return [
                RecallCase(question=title, expect_titles=[title], source="probe")
                for title in pages
                if title and title.strip()
            ]

    return _load()


def _matches(title: str, expectations: list[str]) -> bool:
    lowered = title.lower()
    return any(exp.lower() in lowered for exp in expectations if exp)


async def run_recall_test(
    knowledge_base_id: int,
    search_fn: Callable[..., Any],
    *,
    questions: list[str] | None = None,
    top_k: int = 5,
    score_threshold: float | None = None,
    page_type: str | None = None,
    user_id: int | None = None,
    is_admin: bool = False,
) -> RecallReport:
    """对指定知识库跑一批探针问题，返回召回报告。

    ``search_fn`` 由调用方注入（通常是 ``KnowledgeRetrieval.search``），
    避免本模块反向依赖检索实现。
    """
    cases: list[RecallCase] = []
    if questions:
        cases = [RecallCase(question=q.strip()) for q in questions if q and q.strip()]

    if not cases:
        # 无显式问题集：用知识库内的页面标题自动生成探针问题
        # （标题本身就是文档主题，用它做查询能测出该页是否可被召回）
        cases = build_probe_cases(knowledge_base_id)

    params = {
        "top_k": top_k,
        "score_threshold": score_threshold,
        "page_type": page_type,
    }

    results: list[RecallCaseResult] = []
    for case in cases:
        raw = await asyncio.to_thread(
            search_fn,
            query=case.question,
            knowledge_base_ids=[knowledge_base_id],
            user_id=user_id,
            page_type=page_type,
            max_results=top_k,
            is_admin=is_admin,
            score_threshold=score_threshold,
        )
        hits = [
            {
                "page_id": getattr(r, "page_id", None),
                "title": getattr(r, "title", ""),
                "score": round(float(getattr(r, "score", 0.0)), 4),
                "page_type": getattr(r, "page_type", ""),
            }
            for r in (raw or [])
        ]
        rank = None
        score = None
        matched = bool(hits) if not case.expect_titles else False
        if case.expect_titles:
            for index, hit in enumerate(hits, start=1):
                if _matches(hit["title"], case.expect_titles):
                    matched = True
                    rank = index
                    score = hit["score"]
                    break
        else:
            rank = 1 if hits else None
            score = hits[0]["score"] if hits else None

        results.append(
            RecallCaseResult(
                question=case.question,
                hits=hits,
                matched=matched,
                rank_of_first_expected=rank,
                score_of_first_expected=score,
            )
        )

    total = len(results)
    matched_count = sum(1 for r in results if r.matched)
    ranks = [r.rank_of_first_expected for r in results if r.rank_of_first_expected]
    report = RecallReport(
        total=total,
        matched=matched_count,
        hit_rate=(matched_count / total) if total else 0.0,
        avg_rank=(sum(ranks) / len(ranks)) if ranks else None,
        cases=results,
        params=params,
    )
    logger.info(
        "recall test kb=%s: %s/%s hit_rate=%.2f",
        knowledge_base_id, matched_count, total, report.hit_rate,
    )
    return report