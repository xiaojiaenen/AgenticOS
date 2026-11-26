"""检索结果重排（docs/design/系统改造总方案.md 战线 B4 自研归位）。

为什么需要重排
--------------
混合召回给出的分只有「通道内相对强弱」，没有回答一个问题：**这段文字真的
回答了提问吗**。BM25 会因为一个高频词把整段抬高，向量会因为整体主题相近
把边角料排前面。重排补的是「查询与命中片段之间的贴合度」。

两级实现
--------
- **启发式四信号**（本模块原有实现，``score_result``）：coverage / proximity /
  agreement / base 加权，可解释、零依赖、零抖动，仍然是对外的兜底路径。
- **FlashRank cross-encoder**（``rerank_scores``，战线 B4 新增）：本地 ONNX
  模型（当前用 MiniLM-L-12-v2，首次使用自动下载到用户缓存目录，之后离线
  可用）；L-12 比文档最初写的 L-6 精度更高、体积/冷启动更重，这是有意的
  质量取舍。接口原本就留成 ``score_result`` 一条缝，现在把缝扩成批量入口
  ``rerank_scores`` —— 模型不可用（离线/下载失败）时返回 None，调用方无缝
  落回启发式，检索永不因重排挂掉。

``final = w*flashrank + (1-w)*heuristic``（w 默认 0.65，可配
``KB_RERANK_FLASHRANK_WEIGHT``）。cross-encoder 有 p95 抖动，只对 top-K
候选精排（``KB_RERANK_TOP_K``，默认 20）。

选型说明：jina-reranker 自托管权重是 CC-BY-NC（商用受限），不采用；
bge-reranker-v2-m3 精度更高但模型大得多，规模上来后再评估。
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Iterable, Sequence

from app.services.knowledge.tokenizer import tokenize

logger = logging.getLogger("agenticos.knowledge.rerank")

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


# ═══ FlashRank cross-encoder（战线 B4 自研归位）══════════════════════════

#: 轻量首选模型（量化 ONNX / CPU 友好，首次使用自动下载 ~22MB 到缓存目录，
#: 之后离线可用）；多语言/高精度档（rank-T5-flan 等）按规模再评估。
#: 许可说明：flashrank 库为 Apache-2.0，模型权重仓库为 CC-BY-SA（平台内部
#: 使用无碍；对外再分发模型文件时需保留署名与同方式共享）。
FLASHRANK_MODEL_NAME = "ms-marco-MiniLM-L-12-v2"

_flashrank_ranker = None
_flashrank_failed = False
_flashrank_lock = threading.Lock()


def _get_flashrank_ranker():
    """懒加载 FlashRank Ranker 单例；任何失败都降级（返回 None）且不重试。

    失败不重试的理由：失败原因（离线/磁盘满/依赖缺失）在进程生命周期内
    通常不变，重试只会把每次检索都拖慢一次下载超时。
    """
    global _flashrank_ranker, _flashrank_failed
    if _flashrank_failed:
        return None
    if _flashrank_ranker is not None:
        return _flashrank_ranker
    with _flashrank_lock:
        if _flashrank_failed:
            return None
        if _flashrank_ranker is not None:
            return _flashrank_ranker
        try:
            from flashrank import Ranker

            _flashrank_ranker = Ranker(model_name=FLASHRANK_MODEL_NAME)
            logger.info("FlashRank 重排器已加载（model=%s）", FLASHRANK_MODEL_NAME)
        except Exception as exc:  # noqa: BLE001 —— 任何加载失败都降级启发式
            _flashrank_failed = True
            _flashrank_ranker = None
            logger.warning("FlashRank 不可用（%s），检索重排降级为启发式四信号", exc)
        return _flashrank_ranker


def reset_flashrank_state() -> None:
    """重置懒加载状态（测试用）。"""
    global _flashrank_ranker, _flashrank_failed
    with _flashrank_lock:
        _flashrank_ranker = None
        _flashrank_failed = False


def rerank_scores(query: str, texts: Sequence[str]) -> list[float] | None:
    """FlashRank 批量打分：返回与 ``texts`` 顺序对齐的 0~1 相关度列表。

    模型不可用时返回 None —— 调用方据此落回启发式实现。查询或候选为空
    也返回 None（没有可精排的东西，无需降级告警）。
    """
    if not query or not texts:
        return None
    ranker = _get_flashrank_ranker()
    if ranker is None:
        return None
    try:
        from flashrank import RerankRequest

        passages = [{"id": idx, "text": text or " "} for idx, text in enumerate(texts)]
        ranked = ranker.rerank(RerankRequest(query=query, passages=passages))
        scores = [0.0] * len(texts)
        for item in ranked:
            scores[int(item["id"])] = max(0.0, min(1.0, float(item.get("score", 0.0))))
        return scores
    except Exception as exc:  # noqa: BLE001 —— 推理失败也按不可用处理
        logger.warning("FlashRank 推理失败（%s），本批降级启发式", exc)
        return None


def blend_score(*, flashrank: float, heuristic: float, weight: float) -> float:
    """线性融合，结果仍收敛在 0~1（对外 score 语义不变）。"""
    weight = max(0.0, min(1.0, weight))
    value = weight * max(0.0, min(1.0, flashrank)) + (1.0 - weight) * max(0.0, min(1.0, heuristic))
    return round(value, 6)
