"""RAGAS 旁路 PoC 测试（fake ragas 模块锁定数据集构造契约）。"""

from __future__ import annotations

import sys
import types

import pytest

from app.services.eval_ragas_poc import (
    DEFAULT_METRICS,
    RagSample,
    cheap_offline_metrics,
    evaluate_rag_batch,
)
from app.services.llm_providers.spec import ProviderConfigError


def _install_fake_ragas(scores_by_metric: dict[str, float], captured: dict):
    """注入 fake ragas 模块：record 调用参数，to_pandas 返回每样本分数。"""
    fake = types.ModuleType("ragas")
    fake_metrics_mod = types.ModuleType("ragas.metrics")
    for name in DEFAULT_METRICS:
        setattr(fake_metrics_mod, name, f"<metric:{name}>")
    fake.metrics = fake_metrics_mod

    def fake_evaluate(dataset, **kwargs):
        captured["dataset"] = dataset
        captured["kwargs"] = kwargs
        import pandas as pd

        rows = []
        for d in dataset:
            row = {m: scores_by_metric.get(m, 0.9) for m in kwargs["metrics_meta"]}
            rows.append(row)
        return SimpleNamespace(to_pandas=lambda: pd.DataFrame(rows))

    fake.evaluate = fake_evaluate
    sys.modules["ragas"] = fake
    sys.modules["ragas.metrics"] = fake_metrics_mod
    return fake


class SimpleNamespace:
    """局部别名（避免顶部 import 混淆）。"""

    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture
def fake_ragas_installed(monkeypatch):
    """假装 ragas 已安装 + pandas 可用。"""
    pytest.importorskip("pandas")
    captured: dict = {}
    # fake_evaluate 里读取 metrics_meta 传递分数（绕过真实 metric 对象）
    scores = {"faithfulness": 0.95, "answer_relevancy": 0.8,
              "context_precision": 0.7, "context_recall": 0.6}

    fake = types.ModuleType("ragas")
    fake_metrics_mod = types.ModuleType("ragas.metrics")
    for name in DEFAULT_METRICS:
        setattr(fake_metrics_mod, name, f"<metric:{name}>")
    fake.metrics = fake_metrics_mod

    def fake_evaluate(dataset, **kwargs):
        captured["dataset"] = dataset
        captured["kwargs"] = kwargs
        import pandas as pd

        rows = [{m: scores.get(m, None) for m in DEFAULT_METRICS} for _ in dataset]
        fake._df = pd.DataFrame(rows)
        fake._scores = scores
        return types.SimpleNamespace(to_pandas=lambda: fake._df)

    fake.evaluate = fake_evaluate
    monkeypatch.setitem(sys.modules, "ragas", fake)
    monkeypatch.setitem(sys.modules, "ragas.metrics", fake_metrics_mod)
    return captured


@pytest.mark.asyncio
async def test_dataset_contract_and_averages(fake_ragas_installed):
    samples = [
        RagSample(question="如何备份", answer="用 xtrabackup", contexts=["备份文档"], ground_truth="每周备份"),
        RagSample(question="如何恢复", answer="binlog 回放", contexts=["恢复文档"], ground_truth="binlog"),
    ]
    report = await evaluate_rag_batch(samples)
    # 字段名契约：ragas SingleTurnSample 命名（user_input/response/retrieved_contexts/reference）
    d0 = fake_ragas_installed["dataset"][0]
    assert d0 == {
        "user_input": "如何备份",
        "response": "用 xtrabackup",
        "retrieved_contexts": ["备份文档"],
        "reference": "每周备份",
    }
    # 指标对象被传入（从 ragas.metrics 取的默认四指标）
    kw = fake_ragas_installed["kwargs"]
    assert len(kw["metrics"]) == len(DEFAULT_METRICS)
    # 聚合均值（fake 给每样本同一分数）
    assert report.averages["faithfulness"] == 0.95
    assert report.samples[0]["scores"]["context_recall"] == 0.6


@pytest.mark.asyncio
async def test_ragas_missing_gives_actionable_error(monkeypatch):
    # 确保没有可导入的 ragas
    monkeypatch.setitem(sys.modules, "ragas", None)
    with pytest.raises(ProviderConfigError, match="uv add ragas"):
        await evaluate_rag_batch([RagSample("q", "a", ["c"])])


@pytest.mark.asyncio
async def test_empty_samples_rejected():
    with pytest.raises(ValueError, match="样本为空"):
        await evaluate_rag_batch([])


def test_cheap_offline_metrics_hit_and_overlap():
    samples = [
        RagSample("缓存雪崩怎么办", "加随机抖动", ["Redis 缓存雪崩应对"], expected_page_title="Redis 缓存雪崩应对"),
        RagSample("发票报销", "十个工作日", ["报销流程"], expected_page_title="报销流程"),
        RagSample("无关问题", "不知道", ["别的页面"], expected_page_title=None),
    ]
    report = cheap_offline_metrics(samples)
    # 前两条 hit（期望标题出现在 contexts），第三条不计入
    assert report.averages["hit_rate"] == 1.0
    # overlap 在 [0,1] 且第三条也计
    assert 0 <= report.averages["context_overlap"] <= 1
    assert len(report.samples) == 3
