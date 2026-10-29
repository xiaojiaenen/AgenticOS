"""百通内置预设回归（合并内部版后防丢失）。"""
from __future__ import annotations

from app.services.llm_providers import presets


def test_gree_baitong_is_builtin() -> None:
    """合并内部版后，百通预设必须内置 —— 部署不再依赖 PROVIDER_PRESETS_DIR。"""
    preset = presets.PRESETS.get("gree_baitong")
    assert preset is not None, "GREE_BAITONG 预设丢失 —— 内部版合并被回退了？"
    assert preset.base_url == "https://agents.gree.com/agents/baitong"
    assert preset.model == "Qwen3.6-35B-A3B"
    assert preset.login.required_cookies == ("SESSION",)
    # 站点特有选择器应在预设里（默认选择器保持通用）
    assert "#UserIDShort" in preset.login.username_selectors
    assert "#modalButton" in preset.login.submit_selectors


def test_generic_presets_still_present() -> None:
    slugs = {p.slug for p in presets.GENERIC_PRESETS}
    assert {"openai", "deepseek", "ollama"} <= slugs


def test_registry_parser_alias_for_legacy_config() -> None:
    """历史 extra_json 里写死的 gree_registry 必须继续可用。"""
    from app.services.llm_providers.discovery import parse_models_payload

    out = parse_models_payload(
        {"models": {"m1": {"name": "N", "model": "m1"}}}, parser="gree_registry"
    )
    assert out and out[0]["model_name"] == "N"
