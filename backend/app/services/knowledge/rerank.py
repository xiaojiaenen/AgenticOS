"""检索结果的本地启发式重排（无外部 reranker 依赖）。

为什么需要重排
--------------
混合召回给出的分只有「通道内相对强弱」，没有回答一个问题：**这段文字真的
回答了提问吗**。BM25 会因为一个高频词把整段抬高，向量会因为整体主题相近
把边角料排前面。重排补的是「查询与命中片段之间的贴合度」。

为什么不用 cross-encoder
------------------------
bge-reranker / Cohere Rerank 效果好，但要多一份模型托管或一次外部调用，
并且会给检索链路引入 p95 抖动。这里先用四个可解释的本地信号顶上，
接口留成同一个 ``score_result``，将来换真 reranker 只需要替换实现。

四个信号
--------
- **coverage**：查询词在命中片段里的覆盖率 —— 问「端口和超时」只命中「端口」
  的段，不该排第一；
- **proximity**：命中词的邻近度 —— 同一句话里出现的「端口」「8080」比分散在
  段首段尾更有意义；
- **agreement**：通道一致性 —— 字面通道和语义通道同时选中，可信度高于单通道；
- **base**：融合后的原始分（保留召回阶段的排序信息，权重最高）。

``final = 0.55*base + 0.25*coverage + 0.12*proximity + 0.08*agreement``
四项权重和为 1，结果天然落在 0~1，与检索对外承诺的 score 语义一致。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence

from app.services.knowledge.tokenizer import tokenize

WEIGHT_BASE = 0.55
WEIGHT_COVERAGE = 0.25
WEIGHT_PROXIMITY = 0.12
WEIGHT_AGREEMENT = 0.08

AGREEMENT_BOTH = 1.0
AGREEMENT_SINGLE = 0.5
AGREEMENT_NONE = 0.0


def lexical_signals(query_terms: Sequence[str], text: str) -> tuple[float, float]:
    """计算 (覆盖率, 邻近度)，两者均在 0~1。

    覆盖率按「去重后的查询词」算，避免长查询里同一个词出现三次把分母撑大。
    邻近度取覆盖全部命中词的最短 token 窗口：窗口越紧凑越接近 1。
    """
    terms = {t for t in query_terms if t}
    if not terms or not text:
        return 0.0, 0.0

    tokens = tokenize(text)
    if not tokens:
        return 0.0, 0.0

    positions: dict[str, list[int]] = defaultdict(list)
    for idx, token in enumerate(tokens):
        if token in terms:
            positions[token].append(idx)

    matched = [t for t in terms if positions.get(t)]
    coverage = len(matched) / len(terms)
    if len(matched) < 2:
        return coverage, 0.0

    flat = sorted((pos, term) for term, poses in positions.items() for pos in poses)
    best_span: int | None = None
    window: dict[str, int] = defaultdict(int)
    covered = 0
    left = 0

    for right, (right_pos, right_term) in enumerate(flat):
        if window[right_term] == 0:
            covered += 1
        window[right_term] += 1

        while covered == len(matched):
            span = right_pos - flat[left][0] + 1
            if best_span is None or span < best_span:
                best_span = span
            left_term = flat[left][1]
            window[left_term] -= 1
            if window[left_term] == 0:
                covered -= 1
            left += 1

    if best_span is None:
        return coverage, 0.0
    # 命中词天然占 len(matched) 个 token，多余的那部分是「中间夹了多少无关词」
    slack = max(0, best_span - len(matched))
    proximity = 1.0 / (1.0 + slack / len(matched))
    return coverage, proximity


def channel_agreement(channels: Iterable[str] | None) -> float:
    """通道一致性分：双通道命中 > 单通道命中 > 无通道信息。"""
    names = {c for c in (channels or []) if c}
    if len(names) >= 2:
        return AGREEMENT_BOTH
    if names:
        return AGREEMENT_SINGLE
    return AGREEMENT_NONE


def score_result(
    *,
    base_score: float,
    query_terms: Sequence[str],
    text: str,
    channels: Iterable[str] | None,
) -> float:
    """重排后的最终分（0~1）。"""
    coverage, proximity = lexical_signals(query_terms, text)
    score = (
        WEIGHT_BASE * max(0.0, min(1.0, base_score))
        + WEIGHT_COVERAGE * coverage
        + WEIGHT_PROXIMITY * proximity
        + WEIGHT_AGREEMENT * channel_agreement(channels)
    )
    return round(max(0.0, min(1.0, score)), 6)


def explain(
    *,
    base_score: float,
    query_terms: Sequence[str],
    text: str,
    channels: Iterable[str] | None,
) -> dict[str, float]:
    """返回各信号取值，用于召回测试里解释「为什么这条排前面」。"""
    coverage, proximity = lexical_signals(query_terms, text)
    agreement = channel_agreement(channels)
    return {
        "base": round(max(0.0, min(1.0, base_score)), 6),
        "coverage": round(coverage, 6),
        "proximity": round(proximity, 6),
        "agreement": round(agreement, 6),
        "final": score_result(
            base_score=base_score,
            query_terms=query_terms,
            text=text,
            channels=channels,
        ),
    }
