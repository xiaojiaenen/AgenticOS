"""模型目录同步「对齐上游」：prune 语义与失效绑定清理。

背景：`upsert_models` 原本只增不删，上游下架的模型会永远留在目录里，
用户看到的清单和真实可用模型越差越远。现在同步 = 完全对齐上游。

代价：被删模型若正被 `roles` 引用，那条绑定会失效。端点必须同步清理，
否则会留下「界面显示已绑定、调用时静默回退」的脏状态 —— 最难排查。
"""

from __future__ import annotations

import uuid

import pytest

from app.db.models import LlmProviderModel
from app.db.session import create_db_session
from app.services.llm_providers import catalog
from app.services.llm_providers.spec import parse_extra, update_provider


def _make_provider() -> int:
    with create_db_session() as db:
        row = LlmProviderModel(
            name=f"prune-{uuid.uuid4().hex[:8]}",
            slug=f"prune-{uuid.uuid4().hex[:8]}",
            provider_type="openai_compatible",
            base_url="https://example.test/v1",
            model="main-model",
            enabled=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)


def _cleanup(provider_id: int) -> None:
    with create_db_session() as db:
        catalog.clear_models(db, provider_id)
        row = db.get(LlmProviderModel, provider_id)
        if row is not None:
            db.delete(row)
        db.commit()


def test_prune_removes_models_missing_upstream():
    provider_id = _make_provider()
    try:
        with create_db_session() as db:
            catalog.upsert_models(
                db, provider_id,
                [
                    {"model_key": "keep", "model_name": "Keep", "task_type": "text-generation"},
                    {"model_key": "drop", "model_name": "Drop", "task_type": "text-generation"},
                ],
            )
            db.commit()

        # 第二次同步上游只剩 keep
        with create_db_session() as db:
            added, updated, removed = catalog.upsert_models(
                db, provider_id,
                [{"model_key": "keep", "model_name": "Keep", "task_type": "text-generation"}],
                prune=True,
            )
            db.commit()

            assert added == 0
            assert updated == 1
            assert removed == 1
            remaining = {row.model_key for row in catalog.list_models(db, provider_id)}
            assert remaining == {"keep"}
    finally:
        _cleanup(provider_id)


def test_prune_false_keeps_history():
    """默认不 prune：保持历史行为，避免旧调用方被静默改变语义。"""
    provider_id = _make_provider()
    try:
        with create_db_session() as db:
            catalog.upsert_models(
                db, provider_id,
                [
                    {"model_key": "a", "model_name": "A", "task_type": "text-generation"},
                    {"model_key": "b", "model_name": "B", "task_type": "text-generation"},
                ],
            )
            db.commit()

        with create_db_session() as db:
            _, _, removed = catalog.upsert_models(
                db, provider_id,
                [{"model_key": "a", "model_name": "A", "task_type": "text-generation"}],
            )
            db.commit()
            assert removed == 0
            assert len(catalog.list_models(db, provider_id)) == 2
    finally:
        _cleanup(provider_id)


def test_models_removed_by_prune_previews_names():
    """端点要在删之前知道哪些**名字**会消失，才能清绑定。

    顺序不能反：prune 之后目录里就查不到这些名字了。
    """
    provider_id = _make_provider()
    try:
        with create_db_session() as db:
            catalog.upsert_models(
                db, provider_id,
                [
                    {"model_key": "keep", "model_name": "Keep-Model", "task_type": "text-generation"},
                    {"model_key": "drop", "model_name": "Drop-Model", "task_type": "text-generation"},
                ],
            )
            db.commit()

        with create_db_session() as db:
            disappearing = catalog.models_removed_by_prune(
                db, provider_id, {"keep"}
            )
            assert disappearing == {"Drop-Model"}
            # 预览不产生副作用
            assert len(catalog.list_models(db, provider_id)) == 2
    finally:
        _cleanup(provider_id)


def test_retired_roles_are_dropped_silently():
    """旧库里的 reasoner / vision 绑定加载时不报错，静默丢弃。

    报错会让历史 provider 直接不可编辑 —— 用户什么都没做，只是升级了版本。
    这两个角色已无任何运行时消费方，留着既无害也无用。
    """
    provider_id = _make_provider()
    try:
        with create_db_session() as db:
            row = db.get(LlmProviderModel, provider_id)
            extra = parse_extra(row.extra_json)
            extra["roles"] = {
                "chat": "Main",
                "reasoner": "Deep",   # 已下线
                "vision": "VLM",      # 已下线
                "fast": "Quick",
            }
            # 不应抛 ProviderConfigError
            update_provider(db, row, fields={"extra": extra})
            db.commit()

        with create_db_session() as db:
            row = db.get(LlmProviderModel, provider_id)
            roles = parse_extra(row.extra_json).get("roles") or {}
            assert roles == {"chat": "Main", "fast": "Quick"}
    finally:
        _cleanup(provider_id)


def test_role_options_carry_follows_main_flag():
    """role_options 必须告诉前端「留空是否真的回退主模型」。

    chat / fast 走 /chat/completions，留空回退主模型；
    image / embedding 走独立端点，留空 = 未绑定（主模型做不了这些）。
    前端据此渲染不同文案，否则「跟随主模型」是误导。
    """
    from app.services.llm_providers.presets import MODEL_ROLES, ROLES_FOLLOWING_MAIN

    assert ROLES_FOLLOWING_MAIN == frozenset({"chat", "fast"})
    assert set(MODEL_ROLES) == {"chat", "fast", "image", "embedding"}
    # 已下线的角色不在任何可见集合里
    assert "reasoner" not in MODEL_ROLES
    assert "vision" not in MODEL_ROLES
