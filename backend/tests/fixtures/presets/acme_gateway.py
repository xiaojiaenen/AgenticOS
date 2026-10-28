"""测试用企业网关预设（虚构厂商 acme，不含任何真实内网信息）。

这个文件演示内部部署该怎么放自己的预设：导出 PRESETS 列表，
设置 PROVIDER_PRESETS_DIR 指向所在目录即可被加载。
"""

from app.services.llm_providers.presets import (
    LoginFlow,
    ProbeSpec,
    ProviderPreset,
    TransportOptions,
)

ACME_GATEWAY = ProviderPreset(
    slug="acme_gateway",
    label="Acme 企业网关（测试用）",
    provider_type="enterprise_cookie",
    base_url="https://ai.acme.test/agents/gateway",
    model="acme-chat-v1",
    login_url="https://ai.acme.test/login/oauth2/code/ar",
    login=LoginFlow(
        submit_text="授权并登录",
        wait_until="domcontentloaded",
        settle_ms=4_000,
        success_url="**/chat/home",
        success_timeout_ms=60_000,
        required_cookies=("SESSION",),
        cookie_domain="ai.acme.test",
        cookie_poll_attempts=30,
        cookie_poll_interval_ms=2_000,
        ignore_https_errors=True,
    ),
    transport=TransportOptions(
        insecure_tls=True,
        browser_user_agent=True,
        extra_body={"enable_thinking": False},
    ),
    probe=ProbeSpec(
        kind="registry",
        path="/json/model-configs.json",
        scope="origin",
        parser="registry_models",
    ),
    roles={"chat": "acme-chat-v1", "fast": "acme-chat-v1"},
    notes="企业内网 SSO 网关（测试夹具）。",
)

PRESETS = [ACME_GATEWAY]
