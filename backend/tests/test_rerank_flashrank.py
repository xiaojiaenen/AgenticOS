"""检索重排回归（docs/design/系统改造总方案.md 战线 B4 自研归位）。

- 启发式四信号 ``score_result`` 行为保持（原契约，召回测试依赖）；
- FlashRank 后端可用时 ``rerank_scores`` 返回 0~1 分且顺序对齐；
- 模型不可用时返回 None（调用方降级），绝不抛异常打断检索链路；
- ``blend_score`` 权重边界（0/1/越界）收敛。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.knowledge import rerank


# ── 启发式（原实现，行为不回归）────────────────────────────────────────


def test_score_result_range_and_monotonicity():
    base = rerank.score_result(base_score=0.8, query_terms=["端口", "超时"], text="服务的端口是 8080，默认超时 30s", channels=["bm25", "vector"])
    assert 0.0 <= base <= 1.0
    # 命中全部查询词的文本得分应高于只命中一个词的
    partial = rerank.score_result(base_score=0.8, query_terms=["端口", "超时"], text="服务的端口是 8080", channels=["bm25"])
    assert base > partial


def test_score_result_empty_inputs_safe():
    assert rerank.score_result(base_score=0.5, query_terms=[], text="x", channels=None) >= 0
    assert rerank.score_result(base_score=0.5, query_terms=["a"], text="", channels=None) >= 0


def test_explain_returns_all_signals():
    info = rerank.explain(base_score=0.6, query_terms=["端口"], text="端口 8080", channels=["bm25", "vector"])
    assert set(info) == {"base", "coverage", "proximity", "agreement", "final"}


# ── FlashRank 路径 ─────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state():
    rerank.reset_flashrank_state()
    yield
    rerank.reset_flashrank_state()


def test_rerank_scores_degrades_to_none_on_load_failure():
    """模型加载失败（离线环境）→ 返回 None，不抛异常。"""
    with patch.object(rerank, "_get_flashrank_ranker", return_value=None):
        assert rerank.rerank_scores("查询", ["doc1", "doc2"]) is None


def test_rerank_scores_empty_inputs():
    with patch.object(rerank, "_get_flashrank_ranker", return_value=None):
        assert rerank.rerank_scores("", ["a"]) is None
        assert rerank.rerank_scores("q", []) is None


def test_rerank_scores_inference_failure_degrades():
    """推理抛异常 → 捕获返回 None（检索链路不因重排挂掉）。"""
    ranker = MagicMock()
    ranker.rerank.side_effect = RuntimeError("onnx boom")
    with patch.object(rerank, "_get_flashrank_ranker", return_value=ranker):
        assert rerank.rerank_scores("q", ["a", "b"]) is None


def test_rerank_scores_order_aligned():
    """返回分数与输入顺序对齐（按 id 回填，不依赖 ranker 的输出排序）。"""
    fake = MagicMock()

    def _rerank(request):
        # 故意乱序返回：id=1 分高、id=0 分低
        return [
            {"id": 1, "text": request.passages[1]["text"], "score": 0.9},
            {"id": 0, "text": request.passages[0]["text"], "score": 0.2},
        ]

    fake.rerank.side_effect = _rerank
    with patch.object(rerank, "_get_flashrank_ranker", return_value=fake):
        scores = rerank.rerank_scores("q", ["first-doc", "second-doc"])
    assert scores == [0.2, 0.9]


def test_rerank_scores_clamped():
    fake = MagicMock()
    fake.rerank.return_value = [{"id": 0, "text": "x", "score": 1.7}]
    with patch.object(rerank, "_get_flashrank_ranker", return_value=fake):
        assert rerank.rerank_scores("q", ["x"]) == [1.0]


def test_rerank_scores_real_model_when_available():
    """真模型冒烟：环境能加载模型时跑一次真实推理（不可用则跳过）。"""
    ranker = rerank._get_flashrank_ranker()
    if ranker is None:
        pytest.skip("FlashRank 模型不可用（离线/未下载），降级路径已单测覆盖")
    scores = rerank.rerank_scores(
        "redis 连接超时怎么配置",
        [
            "Redis 连接超时由 socket_timeout 控制，默认 5 秒，生产建议放大到 60 秒。",
            "今天天气不错，适合散步。",
            "redis-py 的 from_url 可以设置 decode_responses=True。",
        ],
    )
    assert scores is not None and len(scores) == 3
    assert all(0.0 <= s <= 1.0 for s in scores)
    # 贴题的 Redis 超时段落应该比"天气"段落分高
    assert scores[0] > scores[1]


def test_blend_score_weight_bounds():
    assert rerank.blend_score(flashrank=1.0, heuristic=0.0, weight=1.0) == 1.0
    assert rerank.blend_score(flashrank=0.8, heuristic=0.4, weight=0.0) == 0.4
    mid = rerank.blend_score(flashrank=0.8, heuristic=0.4, weight=0.5)
    assert mid == 0.6
    # 越界权重收敛到 [0,1]
    assert rerank.blend_score(flashrank=1.0, heuristic=0.0, weight=99) == 1.0
    assert rerank.blend_score(flashrank=0.5, heuristic=0.5, weight=-3) == 0.5
