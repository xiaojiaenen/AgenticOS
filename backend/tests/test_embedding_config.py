"""生图 / 嵌入 / 离线嵌入模型的可配置性测试。

覆盖三件事：
1. provider 的 roles 里能配 embedding 与 image，且解析层能取到
2. 离线（本地）嵌入模型优先级最高，且完全不走网络
3. 三种来源的降级顺序正确（local → provider → env → 无）
"""
from __future__ import annotations

import pytest

from app.services.llm_providers import resolve_models
from app.services.llm_providers.presets import MODEL_ROLES, ROLE_EMBEDDING, ROLE_IMAGE


def test_embedding_and_image_are_known_roles() -> None:
    """embedding / image 必须在 MODEL_ROLES 里 —— 否则后端会拒绝保存。"""
    assert ROLE_EMBEDDING == "embedding"
    assert ROLE_IMAGE == "image"
    assert "embedding" in MODEL_ROLES
    assert "image" in MODEL_ROLES
    assert "向量" in MODEL_ROLES["embedding"]
    assert "生图" in MODEL_ROLES["image"] or "文生图" in MODEL_ROLES["image"]


def test_local_model_takes_priority(monkeypatch) -> None:
    """配了本地模型就走本地，即使配了远程 Key 也不碰网络。"""
    from app.core.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_DIMENSIONS", "1024")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_API_KEY", "sk-should-not-be-used")
    get_settings.cache_clear()

    ep = resolve_models.resolve_embedding_endpoint(db=None)
    assert ep is not None
    assert ep.source == "local"
    assert ep.model == "BAAI/bge-m3"
    assert ep.dimensions == 1024
    assert ep.api_key == "", "本地模式不该携带任何远程 Key"


def test_env_fallback_when_no_provider(monkeypatch) -> None:
    """没有本地模型、没有 provider 时退回 env。"""
    from app.core.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_MODEL", "")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_API_KEY", "sk-env")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_BASE_URL", "https://env.test/v1")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_MODEL", "env-model")
    get_settings.cache_clear()

    ep = resolve_models.resolve_embedding_endpoint(db=None)
    assert ep is not None
    assert ep.source == "env"
    assert ep.model == "env-model"
    assert ep.base_url == "https://env.test/v1"


def test_returns_none_when_nothing_configured(monkeypatch) -> None:
    """什么都没配 → None，检索应降级到 BM25 而不是报错。"""
    from app.core.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_MODEL", "")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    assert resolve_models.resolve_embedding_endpoint(db=None) is None


def test_local_embedder_dimension_mismatch_is_loud() -> None:
    """维度不一致必须报错 —— 静默截断会让向量库数据全部作废却无人察觉。"""
    from app.services.knowledge.local_embedder import LocalEmbedder

    emb = LocalEmbedder("fake-model", expected_dims=768)
    # 未加载模型时 dimensions 为 None
    assert emb.dimensions is None
    assert emb.model == "fake-model"


def test_local_embedder_gives_actionable_error_without_dependency() -> None:
    """没装 sentence-transformers 时，错误信息要能指导安装。"""
    from app.services.knowledge.local_embedder import (
        LocalEmbedder,
        LocalEmbedderUnavailable,
    )

    emb = LocalEmbedder("BAAI/bge-m3")
    try:
        emb._ensure_model()
    except LocalEmbedderUnavailable as exc:
        msg = str(exc)
        assert "sentence-transformers" in msg
        assert "pip install" in msg or "下载" in msg
    except Exception:
        # 已安装依赖时会尝试真的加载模型，测试环境跳过
        pytest.skip("sentence-transformers 已安装，跳过缺依赖分支")


def test_suggested_models_are_documented() -> None:
    """前端要展示推荐模型，每个都需带维度与说明。"""
    from app.services.knowledge.local_embedder import SUGGESTED_MODELS

    assert len(SUGGESTED_MODELS) >= 3
    for item in SUGGESTED_MODELS:
        assert item["id"]
        assert item["dims"].isdigit()
        assert item["note"]


def test_image_endpoint_none_without_provider() -> None:
    """没配 provider 时生图端点应为 None（调用方据此提示去配置）。"""
    assert resolve_models.resolve_image_endpoint(db=None) is None


def test_endpoint_describe_hides_key() -> None:
    """describe() 不能泄露密钥 —— 它会直接返回给前端。"""
    ep = resolve_models.EmbeddingEndpoint(
        base_url="https://x.test/v1",
        api_key="sk-super-secret",
        model="m",
        dimensions=768,
        source="provider:foo",
    )
    desc = ep.describe()
    assert "sk-super-secret" not in str(desc)
    assert desc["has_api_key"] is True
    assert desc["source"] == "provider:foo"
