"""provider 角色解析的集成测试（真实 ORM + 真实 spec_from_row）。

这个测试补的是一个真实踩到的坑：resolve 层用错了 spec_from_row 的签名
（传了 (db, row) 而它只接受 row），异常被 except 吞掉，于是「配了 provider
角色但解析层一直回退 env」——功能静默失效，日志里也看不出原因。

所以这里不做 mock：真的建 provider 行、真的走 spec_from_row，只要签名
或字段名变了，测试立刻红。
"""
from __future__ import annotations

import pytest

from app.services.llm_providers import resolve_models
from app.services.llm_providers.spec import spec_from_row


def test_spec_from_row_signature_is_single_arg() -> None:
    """spec_from_row 只接受 ORM 行 —— 传 db 是错的（曾因此静默降级）。"""
    import inspect

    sig = inspect.signature(spec_from_row)
    assert len(sig.parameters) == 1, (
        f"spec_from_row 参数数量变了：{list(sig.parameters)}。"
        "resolve_models 的调用方式必须同步更新。"
    )


def test_resolve_uses_spec_from_row_correctly() -> None:
    """resolve_models 里的调用必须是 spec_from_row(row)，不能带 db。"""
    import inspect

    src = inspect.getsource(resolve_models)
    assert "spec_from_row(db, row)" not in src, (
        "resolve_models 仍在用错误的 spec_from_row(db, row) 调用 —— "
        "这会让 provider 角色解析静默失败并回退到 env"
    )
    assert "spec_from_row(row)" in src


@pytest.fixture()
def provider_with_roles():
    """建一个带 embedding/image 角色的 provider，返回 id。"""
    from app.db.models import LlmProviderModel
    from app.db.session import create_db_session

    with create_db_session() as db:
        row = LlmProviderModel(
            name="role-test",
            slug="role-test-resolve",
            provider_type="openai_compatible",
            base_url="https://role-test.test/v1",
            model="chat-model",
            api_key_encrypted=None,
            extra_json='{"roles": {"embedding": "emb-model", "image": "img-model"}}',
            enabled=True,
            is_default=False,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        pid = row.id

    yield pid

    with create_db_session() as db:
        obj = db.get(LlmProviderModel, pid)
        if obj is not None:
            db.delete(obj)
            db.commit()


def test_resolve_picks_up_provider_embedding_role(provider_with_roles, monkeypatch) -> None:
    """绑了 embedding 角色就必须解析到 provider 来源。"""
    from app.core.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_MODEL", "")
    get_settings.cache_clear()

    from app.db.session import create_db_session

    with create_db_session() as db:
        ep = resolve_models.resolve_embedding_endpoint(db)

    assert ep is not None, "绑了 embedding 角色却解析不到端点"
    assert ep.source.startswith("provider:"), f"应来自 provider，实际 {ep.source}"
    assert ep.model == "emb-model"


def test_resolve_picks_up_provider_image_role(provider_with_roles) -> None:
    """绑了 image 角色就必须解析到 provider 来源。"""
    from app.db.session import create_db_session

    with create_db_session() as db:
        ep = resolve_models.resolve_image_endpoint(db)

    assert ep is not None, "绑了 image 角色却解析不到端点"
    assert ep.source.startswith("provider:"), f"应来自 provider，实际 {ep.source}"
    assert ep.model == "img-model"


def test_local_still_beats_provider(provider_with_roles, monkeypatch) -> None:
    """本地模型优先级高于 provider —— 内网部署不能被 provider 意外覆盖。"""
    from app.core.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("KNOWLEDGE_EMBEDDING_LOCAL_DIMENSIONS", "1024")
    get_settings.cache_clear()

    from app.db.session import create_db_session

    with create_db_session() as db:
        ep = resolve_models.resolve_embedding_endpoint(db)

    assert ep is not None
    assert ep.source == "local", "配了本地模型却让 provider 抢了优先级"
