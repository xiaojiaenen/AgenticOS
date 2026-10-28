"""厂商预设、账号池轮换、模型目录。

这三块对应三类「只在真实企业网关上才会暴露」的问题：

1. **预设**：登录按钮叫「授权并登录」、证书自签、会话 Cookie 异步写入 ——
   这些知识如果散在代码里，接第二家网关就要复制一遍 if 分支。
2. **账号池**：单个企业账号被限流时不能整站不可用，选号必须能轮转、
   能把坏号踢出去、恢复后能复活。
3. **模型目录**：上游的模型 ID 和请求体里的模型名常常不是同一个东西，
   靠人手填只能等到 404 才发现。
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.timezone import app_now
from app.db.models import (
    LlmModelCatalogModel,
    LlmProviderCredentialModel,
    LlmProviderModel,
)
from app.db.session import create_db_session
from app.services.llm_providers import catalog, credentials, discovery, presets
from app.services.llm_providers.spec import (
    ProviderConfigError,
    create_provider,
    invalidate_cache,
    resolve_model_for_role,
    spec_from_row,
)


@pytest.fixture(autouse=True)
def _clean_providers():
    """每个用例从空表开始：本模块多处复用 slug，残留会撞唯一约束。"""
    from sqlalchemy import delete

    def _wipe() -> None:
        with create_db_session() as db:
            db.execute(delete(LlmModelCatalogModel))
            db.execute(delete(LlmProviderCredentialModel))
            db.execute(delete(LlmProviderModel))
            db.commit()
        invalidate_cache()

    _wipe()
    yield
    _wipe()

# ---------------------------------------------------------------------------
# 1. 厂商预设
# ---------------------------------------------------------------------------


def test_preset_fills_empty_fields_but_keeps_explicit_ones():
    """预设只补空缺。显式传入的地址不能被预设覆盖 —— 内网可能有多个入口。"""
    with create_db_session() as db:
        filled = create_provider(
            db, name="百通", slug="bt", provider_type="", base_url="", preset_slug="gree_baitong"
        )
        db.commit()
        assert filled.provider_type == "enterprise_cookie"
        assert filled.base_url.endswith("/agents/baitong")
        assert filled.model == "Qwen3.6-35B-A3B"

        custom = create_provider(
            db,
            name="百通自建",
            slug="bt2",
            provider_type="",
            base_url="https://10.1.127.22/agents/baitong",
            model="Qwen3.8-27B",
            preset_slug="gree_baitong",
        )
        db.commit()
        assert custom.base_url == "https://10.1.127.22/agents/baitong"
        assert custom.model == "Qwen3.8-27B"


def test_preset_carries_login_flow_into_extra():
    """登录动作必须随预设一起入库，否则自动登录会退回通用选择器并失败。"""
    with create_db_session() as db:
        row = create_provider(
            db, name="百通", slug="bt", provider_type="", base_url="", preset_slug="gree_baitong"
        )
        db.commit()
        spec = spec_from_row(row)

    flow = presets.resolve_login_flow(spec.extra)
    assert flow.submit_text == "授权并登录"
    assert flow.ignore_https_errors is True
    assert "SESSION" in flow.required_cookies
    assert flow.cookie_poll_attempts >= 10
    # networkidle 在有常驻轮询的 SPA 上永远不静默，必须用 domcontentloaded
    assert flow.wait_until == "domcontentloaded"


def test_preset_transport_puts_nonstandard_fields_into_extra_body():
    """``enable_thinking`` 只能走 extra_body。

    平铺进 ``chat.completions.create()`` 会抛 TypeError（openai 2.x 没有
    ``**kwargs``），所以它绝不能出现在 transport 顶层。
    """
    with create_db_session() as db:
        row = create_provider(
            db, name="百通", slug="bt", provider_type="", base_url="", preset_slug="gree_baitong"
        )
        db.commit()
        spec = spec_from_row(row)

    transport = presets.resolve_transport(spec.extra)
    assert transport.insecure_tls is True
    assert transport.extra_body.get("enable_thinking") is False
    assert "enable_thinking" not in spec.extra


def test_extra_rejects_non_openai_top_level_keys():
    """在顶层写 ``enable_thinking`` 必须当场拒绝，不能等对话时崩。"""
    with create_db_session() as db:
        with pytest.raises(ProviderConfigError, match="不支持的键"):
            create_provider(
                db,
                name="A",
                slug="a",
                provider_type="openai_compatible",
                base_url="https://a.example.com",
                model="m",
                api_key="k",
                extra={"enable_thinking": False},
            )


def test_extra_rejects_unknown_role():
    with create_db_session() as db:
        with pytest.raises(ProviderConfigError, match="未知用途"):
            create_provider(
                db,
                name="A",
                slug="a",
                provider_type="openai_compatible",
                base_url="https://a.example.com",
                model="m",
                api_key="k",
                extra={"roles": {"dialogue": "x"}},
            )


def test_extra_rejects_out_of_range_temperature():
    with create_db_session() as db:
        with pytest.raises(ProviderConfigError, match="temperature"):
            create_provider(
                db,
                name="A",
                slug="a",
                provider_type="openai_compatible",
                base_url="https://a.example.com",
                model="m",
                api_key="k",
                extra={"temperature": 9},
            )


def test_login_flow_override_keeps_unspecified_fields():
    """运维改一个按钮文案时，不该把整份 LoginFlow 抄一遍。

    抄漏的字段会退回默认值 —— 这个坑很隐蔽：改了 submit_text 之后
    required_cookies 变空，登录「成功」了但拿到的是没有会话的废 Cookie。
    """
    extra = presets.merge_preset_into_extra(presets.GREE_BAITONG)
    extra["login"] = {"submit_text": "立即登录"}

    flow = presets.resolve_login_flow(extra)
    assert flow.submit_text == "立即登录"
    # 未覆盖的字段来自预设，不是默认值
    assert flow.ignore_https_errors is True
    assert "SESSION" in flow.required_cookies


# ---------------------------------------------------------------------------
# 2. 账号池
# ---------------------------------------------------------------------------


@pytest.fixture
def gateway_provider():
    with create_db_session() as db:
        row = create_provider(
            db, name="网关", slug="gw", provider_type="enterprise_cookie",
            base_url="https://gw.example.com", model="gw-model",
        )
        db.commit()
        provider_id = row.id
    return provider_id


def _add_account(provider_id: int, name: str, *, priority: int = 100) -> int:
    with create_db_session() as db:
        row = credentials.add_account(
            db, provider_id, label=name, username=name, password="p", priority=priority
        )
        db.commit()
        credential_id = row.id
    with create_db_session() as db:
        credentials.save_manual_cookie(db, provider_id, cookie=f"SESSION={name}", credential_id=credential_id)
        db.commit()
    return credential_id


def test_accounts_rotate_on_least_recently_used(gateway_provider):
    """三个号轮流用，配额才会摊开。总选同一个 = 只有一份配额。"""
    ids = [_add_account(gateway_provider, f"u{i}") for i in range(1, 4)]

    picked = [credentials.acquire(gateway_provider).credential_id for _ in range(4)]
    assert picked[:3] == ids
    # 第 4 次回到最久未用的那个
    assert picked[3] == ids[0]


def test_priority_beats_least_used(gateway_provider):
    """主力号（priority 小）应该优先，而不是被轮换规则无差别稀释。"""
    main = _add_account(gateway_provider, "main", priority=10)
    _add_account(gateway_provider, "spare", priority=90)

    assert credentials.acquire(gateway_provider).credential_id == main


def test_account_leaves_rotation_after_repeated_failures(gateway_provider):
    """连续失败到阈值后必须被排除，否则坏号会一直吃到流量。"""
    bad = _add_account(gateway_provider, "bad")
    good = _add_account(gateway_provider, "good")

    for _ in range(credentials.MAX_CONSECUTIVE_FAILURES):
        credentials.mark_cookie_invalid(bad, "upstream 401")

    picked = {credentials.acquire(gateway_provider).credential_id for _ in range(3)}
    assert bad not in picked
    assert good in picked


def test_single_failure_does_not_exclude_account(gateway_provider):
    """偶发一次 401（比如上游抖动）不该把账号踢出池子。"""
    only = _add_account(gateway_provider, "only")
    credentials.mark_cookie_invalid(only, "once")

    assert credentials.acquire(gateway_provider).credential_id == only


def test_disabled_account_is_skipped(gateway_provider):
    disabled = _add_account(gateway_provider, "off")
    active = _add_account(gateway_provider, "on")

    with create_db_session() as db:
        row = db.get(LlmProviderCredentialModel, disabled)
        row.disabled = True
        db.commit()

    assert credentials.acquire(gateway_provider).credential_id == active


def test_expired_account_is_skipped(gateway_provider):
    expired = _add_account(gateway_provider, "old")
    fresh = _add_account(gateway_provider, "new")
    with create_db_session() as db:
        row = db.get(LlmProviderCredentialModel, expired)
        row.expire_at = app_now() - timedelta(minutes=1)
        db.commit()

    assert credentials.acquire(gateway_provider).credential_id == fresh


def test_multiple_accounts_are_allowed_per_provider(gateway_provider):
    """旧结构对 provider_id 有唯一约束，第二条账号会直接写不进去。"""
    _add_account(gateway_provider, "a")
    _add_account(gateway_provider, "b")
    with create_db_session() as db:
        assert len(credentials.list_credentials(db, gateway_provider)) == 2


def test_refresh_candidates_are_per_account(gateway_provider):
    """续期粒度是账号：一个号过期不该把整池的登录态都重做一遍。"""
    ok = _add_account(gateway_provider, "ok")
    stale = _add_account(gateway_provider, "stale")
    with create_db_session() as db:
        row = db.get(LlmProviderCredentialModel, stale)
        row.expire_at = app_now() - timedelta(minutes=1)
        db.commit()

    candidates = credentials.list_refresh_candidates()
    assert (gateway_provider, stale) in candidates
    assert (gateway_provider, ok) not in candidates


# ---------------------------------------------------------------------------
# 3. 模型目录
# ---------------------------------------------------------------------------

GREE_PAYLOAD = {
    "default": {"textGenerationModels": {"base": "qwen3.6-35b"}},
    "models": {
        "qwen3.6-35b": {
            "model": "qwen3.6-35b",
            "name": "Qwen3.6-35B-A3B",
            "taskType": "text-generation",
            "maxTokens": 262144,
            "body": {"model": "Qwen3.6-35B-A3B", "temperature": 0.7, "enable_thinking": False},
        },
        "qwen3.6-35b-vl": {
            "model": "qwen3.6-35b-vl",
            "name": "Qwen3.6-35B-A3B",
            "taskType": "image-text-to-text",
            "maxTokens": 131072,
            "body": {"temperature": 0.7},
        },
    },
}


def test_parse_gree_registry_keeps_key_and_name_apart():
    """百通的 ``model``（ID）和 ``name``（请求体要填的）必须分别保留。"""
    models = discovery.parse_gree_registry(GREE_PAYLOAD)
    assert len(models) == 2
    by_key = {item.model_key: item for item in models}
    assert by_key["qwen3.6-35b"].model_name == "Qwen3.6-35B-A3B"
    assert by_key["qwen3.6-35b"].task_type == "text-generation"
    assert by_key["qwen3.6-35b"].max_tokens == 262144
    # 采样参数被挑出来，非标字段不混进来
    assert by_key["qwen3.6-35b"].extra.get("temperature") == 0.7
    assert "enable_thinking" not in by_key["qwen3.6-35b"].extra


def test_parse_openai_models_shape():
    models = discovery.parse_openai_models({"data": [{"id": "gpt-4o"}, {"id": "o3"}]})
    assert [item.model_key for item in models] == ["gpt-4o", "o3"]
    assert all(item.model_name == item.model_key for item in models)


def test_parse_models_payload_accepts_parser_name():
    assert discovery.parse_models_payload(GREE_PAYLOAD, parser="gree_registry")
    assert discovery.parse_models_payload({"data": [{"id": "x"}]}, parser="openai_models")
    # 解析器名字拼错时退回 OpenAI 形态，不抛异常
    assert discovery.parse_models_payload({"data": [{"id": "x"}]}, parser="nope")


def test_catalog_upsert_is_idempotent(gateway_provider):
    """反复点「同步」不能把已有的行刷成重复行。"""
    items = [item.as_dict() for item in discovery.parse_gree_registry(GREE_PAYLOAD)]
    with create_db_session() as db:
        added, _ = catalog.upsert_models(db, gateway_provider, items)
        db.commit()
        assert added == 2

    with create_db_session() as db:
        added, updated = catalog.upsert_models(db, gateway_provider, items)
        db.commit()
        assert added == 0
        assert updated == 2
        assert len(catalog.list_models(db, gateway_provider)) == 2


def test_catalog_updates_name_when_upstream_renames(gateway_provider):
    with create_db_session() as db:
        catalog.upsert_models(
            db, gateway_provider,
            [{"model_key": "m1", "model_name": "Old-Name", "task_type": "text-generation"}],
        )
        db.commit()

    with create_db_session() as db:
        catalog.upsert_models(
            db, gateway_provider,
            [{"model_key": "m1", "model_name": "New-Name", "task_type": "text-generation"}],
        )
        db.commit()
        rows = catalog.list_models(db, gateway_provider)
        assert rows[0].model_name == "New-Name"


# ---------------------------------------------------------------------------
# 4. 用途绑定
# ---------------------------------------------------------------------------


def test_role_falls_back_to_chat_then_model():
    from dataclasses import replace

    from app.services.llm_providers.spec import ProviderSpec

    spec = ProviderSpec(
        name="A", slug="a", provider_type="openai_compatible",
        base_url="https://a.example.com", model="main-model",
        extra={"roles": {"chat": "chat-model", "fast": "fast-model"}},
    )
    assert resolve_model_for_role(spec, "fast") == "fast-model"
    # 未绑定的用途退回 chat，而不是直接报错
    assert resolve_model_for_role(spec, "vision") == "chat-model"
    # 连 chat 都没绑时退回提供商主模型
    bare = replace(spec, extra={})
    assert resolve_model_for_role(bare, "fast") == "main-model"


def test_role_binding_endpoint_persists(gateway_provider):
    """走服务层验证绑定写入，端点层另有 HTTP 用例。"""
    from app.services.llm_providers.spec import parse_extra, update_provider

    with create_db_session() as db:
        catalog.upsert_models(
            db, gateway_provider,
            [
                {"model_key": "a", "model_name": "Chat-A", "task_type": "text-generation"},
                {"model_key": "b", "model_name": "Fast-B", "task_type": "text-generation"},
            ],
        )
        row = db.get(LlmProviderModel, gateway_provider)
        extra = parse_extra(row.extra_json)
        extra["roles"] = {"chat": "Chat-A", "fast": "Fast-B"}
        update_provider(db, row, fields={"extra": extra})
        db.commit()
        db.refresh(row)
        assert parse_extra(row.extra_json)["roles"]["chat"] == "Chat-A"
