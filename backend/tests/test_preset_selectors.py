"""公开仓库的默认选择器里不能有站点特有的 DOM id。

这个测试覆盖一个真实发生的泄露：#UserIDShort / #modalButton 是某企业
SSO 登录页的元素 id，曾被写进 DEFAULT_USERNAME_SELECTORS /
DEFAULT_SUBMIT_SELECTORS —— 两个声明为「企业 SSO 通用形态」的常量。

站点特有的选择器应当由预设（内部插件）在 LoginFlow 里显式声明，
而不是混进默认值。
"""
from __future__ import annotations

from app.services.llm_providers import presets

# 已知属于特定站点的 DOM id / class（出现即视为泄露）
SITE_SPECIFIC_MARKERS = ("UserIDShort", "modalButton")


def test_default_selectors_contain_no_site_specific_ids() -> None:
    for marker in SITE_SPECIFIC_MARKERS:
        joined = " ".join(
            (*presets.DEFAULT_USERNAME_SELECTORS,
             *presets.DEFAULT_PASSWORD_SELECTORS,
             *presets.DEFAULT_SUBMIT_SELECTORS)
        )
        assert marker not in joined, (
            f"默认选择器里出现站点特有 id「{marker}」。"
            "这类选择器应放在预设的 LoginFlow 里，不要写进默认值。"
        )


def test_default_selectors_only_use_standard_forms() -> None:
    """默认值只允许标准形态，不允许站点特有的 id 选择器。

    标准形态：``input[name=...]``、``input[type=...]``、``button[type=...]``、
    ``button:has-text(...)``。``#xxx`` 这种 id 选择器一律视为站点特有。
    """
    for selector in (*presets.DEFAULT_USERNAME_SELECTORS, *presets.DEFAULT_SUBMIT_SELECTORS):
        # id 选择器属于站点特有，一律不允许出现在默认值
        assert not selector.lstrip().startswith("#"), (
            f"默认值里不允许 id 选择器：{selector}"
        )
        # 必须基于标签或伪类，而不是裸 class/id
        assert selector.startswith(("input[", "button[", "button:has-text(")), (
            f"非标准形态的选择器：{selector}"
        )


def test_generic_presets_fall_back_to_defaults() -> None:
    """通用厂商预设必须能用默认选择器登录（不能被移除的 id 影响）。"""
    for preset in presets.GENERIC_PRESETS:
        assert preset.login.username_selectors, f"{preset.slug} 缺少用户名选择器"
        assert preset.login.submit_selectors, f"{preset.slug} 缺少提交选择器"


def test_external_preset_can_override_selectors(tmp_path, monkeypatch) -> None:
    """站点特有选择器必须能通过预设覆盖 —— 这是它们唯一合法的存放位置。"""
    import textwrap

    from app.services.llm_providers import presets as p

    (tmp_path / "site.py").write_text(
        textwrap.dedent(
            '''
            from app.services.llm_providers.presets import LoginFlow, ProviderPreset

            SITE = ProviderPreset(
                slug="site_override",
                label="站点覆盖测试",
                provider_type="enterprise_cookie",
                base_url="https://site.test/v1",
                model="m",
                login=LoginFlow(
                    username_selectors=("#SiteUser",),
                    submit_selectors=("#SiteSubmit",),
                ),
            )
            PRESETS = [SITE]
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROVIDER_PRESETS_DIR", str(tmp_path))
    p.PRESETS.pop("site_override", None)
    p.load_external_presets()

    preset = p.PRESETS["site_override"]
    assert preset.login.username_selectors == ("#SiteUser",)
    assert preset.login.submit_selectors == ("#SiteSubmit",)
