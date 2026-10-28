"""厂商预设：把「某家上游的特殊脾气」收敛成一份声明式配置。

为什么需要这层：企业网关各家的差异不在协议，而在**接入细节** ——

- 登录页是 SPA，要等几秒才渲染出输入框；
- 提交按钮写着「授权并登录」而不是「登录」，甚至不是 ``<button>``；
- 会话 Cookie 在跳转成功后才由前端脚本异步写入；
- 证书是内网自签的；
- 模型列表不收在 ``/models``，而在一个静态 JSON 注册表里；
- 请求体要顶层 ``enable_thinking`` 这种非标字段。

这些东西如果散在 ``auto_login.py`` / ``runtime.py`` 里用 if 判断厂商，代码会
迅速长成一片无法维护的分支。收敛到一个 dataclass 后，引擎只有一条路径，
接第二家企业网关时**只加数据、不改逻辑**。

数据库侧仍可覆盖：``provider.extra_json`` 里的 ``login`` / ``transport`` /
``probe`` 会与预设深合并（见 :func:`merge_preset_into_extra`）。上游改版时
运维能自己改配置，不必等发版。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# 登录表单的通用探测顺序。企业 SSO 五花八门，但「用户名/密码/提交」三件套
# 的选择器基本落在这些形态里；预设只在这一层之上加厂商特有的补充。
DEFAULT_USERNAME_SELECTORS: tuple[str, ...] = (
    "#UserIDShort",
    'input[name="username"]',
    'input[name="account"]',
    'input[name="user"]',
    'input[name="email"]',
    'input[name="loginId"]',
    'input[name="userId"]',
    'input[type="email"]',
    'input[type="text"][autocomplete="username"]',
    'input[type="tel"]',
)

DEFAULT_PASSWORD_SELECTORS: tuple[str, ...] = ('input[type="password"]',)

DEFAULT_SUBMIT_SELECTORS: tuple[str, ...] = (
    "#modalButton",
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("登录")',
    'button:has-text("Login")',
    'button:has-text("Sign in")',
    'button:has-text("提交")',
)


@dataclass(frozen=True)
class LoginFlow:
    """一次自动登录的完整动作描述。

    每一项都对应一个真实会踩的坑，不是可选的「丰富配置」：

    - ``settle_ms``：``goto`` 返回不代表表单已渲染，SPA 要额外等；
    - ``submit_text``：按可见文本命中，解决「按钮不是 button 标签」；
    - ``success_url``：URL 跳转是比「拿到任意 cookie」更可靠的成功判据 ——
      登录失败时 SSO 页面自己也会写 cookie；
    - ``required_cookies`` + 轮询：会话 cookie 常常是登录后由前端异步写入的，
      取一次拿不到不代表失败；
    - ``cookie_domain``：多域 SSO 会留下别的域的 cookie，混在一起发给上游
      既无意义也容易被网关当成异常请求。
    """

    entry: str = ""
    username_selectors: tuple[str, ...] = DEFAULT_USERNAME_SELECTORS
    password_selectors: tuple[str, ...] = DEFAULT_PASSWORD_SELECTORS
    submit_selectors: tuple[str, ...] = DEFAULT_SUBMIT_SELECTORS
    submit_text: str = ""
    wait_until: str = "domcontentloaded"
    settle_ms: int = 0
    success_url: str = ""
    success_timeout_ms: int = 30_000
    required_cookies: tuple[str, ...] = ()
    cookie_domain: str = ""
    cookie_poll_attempts: int = 3
    cookie_poll_interval_ms: int = 1_000
    ignore_https_errors: bool = False
    # 提交后再等一会，让 OAuth 多跳转和前端脚本有机会跑完
    after_submit_ms: int = 1_000
    extra_http_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TransportOptions:
    """请求侧的行为差异。

    ``extra_body`` 是唯一正确的「往请求体塞非标字段」的通道：openai SDK 2.x 的
    ``create()`` 没有 ``**kwargs``，把 ``enable_thinking`` 平铺成关键字参数会
    直接抛 ``TypeError``（已实测）。而 ``extra_body`` 会被 SDK 合并进 JSON。
    """

    insecure_tls: bool = False
    browser_user_agent: bool = False
    extra_body: dict[str, Any] = field(default_factory=dict)
    # SDK 默认 max_retries=2，对 Cookie 认证是纯浪费：401 重试只会再撞一次
    max_retries: int = 0


@dataclass(frozen=True)
class ProbeSpec:
    """连通性探测方式。

    ``kind=models`` 打 ``{base_url}/models``（标准 OpenAI 兼容）；
    ``kind=registry`` 打站点根下的静态注册表（这类），因为它的
    ``/models`` 是管理端接口，普通账号恒 403 —— 拿 403 当「认证失败」会把
    一份完全有效的 Cookie 判死。
    """

    kind: str = "models"
    path: str = "/models"
    # path 相对的基准：origin（站点根）或 base（base_url，含路径前缀）
    scope: str = "base"
    parser: str = "openai_models"


@dataclass(frozen=True)
class ProviderPreset:
    slug: str
    label: str
    provider_type: str
    base_url: str
    model: str = ""
    login_url: str = ""
    login: LoginFlow = field(default_factory=LoginFlow)
    transport: TransportOptions = field(default_factory=TransportOptions)
    probe: ProbeSpec = field(default_factory=ProbeSpec)
    # 用途 → 模型名。key 见 MODEL_ROLES
    roles: dict[str, str] = field(default_factory=dict)
    notes: str = ""


# 用途枚举。前四项对应「一个系统里其实有四种 LLM 负载」，
# 而不是四个厂商 —— 这也正是企业网关的静态注册表里 base/reasoner/agent/vl 的划分方式。
MODEL_ROLES: dict[str, str] = {
    "chat": "主对话（Agent 编排）",
    "reasoner": "深度思考（复杂推理、长链路规划）",
    "fast": "轻量任务（会话标题、摘要、润色）",
    "vision": "图像理解",
    "image": "文生图",
}

ROLE_CHAT = "chat"
ROLE_REASONER = "reasoner"
ROLE_FAST = "fast"
ROLE_VISION = "vision"
ROLE_IMAGE = "image"


# 内置预设：只放通用厂商（见 GENERIC_PRESETS）。
#
# 公司专属的企业网关预设（内网 SSO、自签证书、私有注册表等）**不进这个
# 字典**，而是通过 ``PROVIDER_PRESETS_DIR`` 环境变量指向的目录在启动时加载
# （见 :func:`load_external_presets`）。这样公开仓库里不含任何内网信息，
# 内部部署也无需维护一份 fork。
PRESETS: dict[str, ProviderPreset] = {}


def load_external_presets(directory: str | os.PathLike[str] | None = None) -> list[str]:
    """从外部目录加载预设插件。

    目录下每个 ``*.py`` 需导出一个 ``PRESETS`` 列表（或单个
    ``ProviderPreset``）。加载失败只记日志、不抛错 —— 一个坏插件不该让整个
    服务起不来。

    Returns:
        成功加载的 slug 列表。
    """
    import importlib.util
    import logging

    logger = logging.getLogger("agenticos.llm.presets")

    raw_dir = directory or os.environ.get("PROVIDER_PRESETS_DIR", "")
    if not raw_dir:
        return []
    root = Path(str(raw_dir)).expanduser()
    if not root.is_dir():
        logger.warning("PROVIDER_PRESETS_DIR 不存在，跳过：%s", root)
        return []

    loaded: list[str] = []
    for file in sorted(root.glob("*.py")):
        if file.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"agenticos_external_preset_{file.stem}", file
            )
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception:  # noqa: BLE001 —— 插件坏了不影响主流程
            logger.warning("外部预设加载失败：%s", file, exc_info=True)
            continue

        candidates = getattr(module, "PRESETS", None)
        if isinstance(candidates, ProviderPreset):
            candidates = [candidates]
        if not isinstance(candidates, (list, tuple)):
            continue
        for preset in candidates:
            if not isinstance(preset, ProviderPreset):
                continue
            PRESETS[preset.slug] = preset
            loaded.append(preset.slug)
            logger.info("已加载外部预设：%s（%s）", preset.slug, preset.label)
    return loaded

# 通用 OpenAI 兼容不是「预设」，但界面需要一份能一键填的模板
GENERIC_PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset(
        slug="openai",
        label="OpenAI",
        provider_type="openai_compatible",
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        transport=TransportOptions(browser_user_agent=False, max_retries=1),
    ),
    ProviderPreset(
        slug="deepseek",
        label="DeepSeek",
        provider_type="openai_compatible",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        transport=TransportOptions(max_retries=1),
    ),
    ProviderPreset(
        slug="ollama",
        label="本地 Ollama",
        provider_type="openai_compatible",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen2.5:14b",
        transport=TransportOptions(insecure_tls=True, max_retries=0),
    ),
)


def get_preset(slug: str | None) -> ProviderPreset | None:
    if not slug:
        return None
    return PRESETS.get(slug) or next(
        (item for item in GENERIC_PRESETS if item.slug == slug), None
    )


def list_presets() -> list[dict[str, Any]]:
    """给前端的预设列表。不含任何凭据，只描述「填什么就能连上」。"""
    items = [
        {
            "slug": preset.slug,
            "label": preset.label,
            "provider_type": preset.provider_type,
            "base_url": preset.base_url,
            "model": preset.model,
            "login_url": preset.login_url,
            "needs_cookie": preset.provider_type == "enterprise_cookie",
            "notes": preset.notes,
            "roles": dict(preset.roles),
        }
        for preset in (*GENERIC_PRESETS, *PRESETS.values())
    ]
    return items


def merge_preset_into_extra(preset: ProviderPreset | None) -> dict[str, Any]:
    """把预设展开成初始 ``extra``。数据库记录以此为基础，之后可局部覆盖。"""
    if preset is None:
        return {}
    return {
        "preset": preset.slug,
        "login": {
            "submit_text": preset.login.submit_text,
            "wait_until": preset.login.wait_until,
            "settle_ms": preset.login.settle_ms,
            "success_url": preset.login.success_url,
            "success_timeout_ms": preset.login.success_timeout_ms,
            "required_cookies": list(preset.login.required_cookies),
            "cookie_domain": preset.login.cookie_domain,
            "cookie_poll_attempts": preset.login.cookie_poll_attempts,
            "cookie_poll_interval_ms": preset.login.cookie_poll_interval_ms,
            "ignore_https_errors": preset.login.ignore_https_errors,
            "after_submit_ms": preset.login.after_submit_ms,
        },
        "transport": {
            "insecure_tls": preset.transport.insecure_tls,
            "browser_user_agent": preset.transport.browser_user_agent,
            "max_retries": preset.transport.max_retries,
            "extra_body": dict(preset.transport.extra_body),
        },
        "probe": {
            "kind": preset.probe.kind,
            "path": preset.probe.path,
            "scope": preset.probe.scope,
            "parser": preset.probe.parser,
        },
        "roles": dict(preset.roles),
    }


def _to_tuple(value: Any, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else fallback
    if isinstance(value, (list, tuple)):
        cleaned = tuple(str(item) for item in value if str(item).strip())
        return cleaned or fallback
    return fallback


_MISSING = object()


def _pick(source: dict[str, Any], key: str, current: Any) -> Any:
    """「键不存在」与「键存在但值为空」必须分开。

    用 ``source.get(key) or current`` 会把显式的 ``""`` / ``0`` / ``False``
    当成「没给」，于是运维永远无法把一个布尔开关关掉、也无法把 settle_ms
    调回 0。
    """
    if key not in source:
        return current
    value = source[key]
    return current if value is None else value


def resolve_login_flow(extra: dict[str, Any], *, default_entry: str = "") -> LoginFlow:
    """``preset.login`` ← ``extra.login`` 深合并。

    **基线必须取自预设，不能取自 LoginFlow 的默认值。** 运维只写一行
    ``{"login": {"submit_text": "立即登录"}}`` 时，如果基线是默认值，那么
    ``required_cookies`` / ``ignore_https_errors`` 会一起退回默认 —— 结果是
    登录「成功」但拿到的是没有会话的废 Cookie，排查起来极其费劲。
    """
    preset = get_preset(extra.get("preset"))
    base = preset.login if preset is not None else LoginFlow()
    flow = replace(base, entry=default_entry or base.entry)
    override = extra.get("login") if isinstance(extra.get("login"), dict) else {}

    if override:
        flow = replace(
            flow,
            entry=str(_pick(override, "entry", flow.entry) or ""),
            username_selectors=_to_tuple(
                override.get("username_selectors"), flow.username_selectors
            ),
            password_selectors=_to_tuple(
                override.get("password_selectors"), flow.password_selectors
            ),
            submit_selectors=_to_tuple(
                override.get("submit_selectors"), flow.submit_selectors
            ),
            submit_text=str(_pick(override, "submit_text", flow.submit_text) or ""),
            wait_until=str(_pick(override, "wait_until", flow.wait_until)),
            settle_ms=int(_pick(override, "settle_ms", flow.settle_ms) or 0),
            success_url=str(_pick(override, "success_url", flow.success_url) or ""),
            success_timeout_ms=int(
                _pick(override, "success_timeout_ms", flow.success_timeout_ms)
            ),
            required_cookies=_to_tuple(override.get("required_cookies"), flow.required_cookies),
            cookie_domain=str(_pick(override, "cookie_domain", flow.cookie_domain) or ""),
            cookie_poll_attempts=int(
                _pick(override, "cookie_poll_attempts", flow.cookie_poll_attempts)
            ),
            cookie_poll_interval_ms=int(
                _pick(override, "cookie_poll_interval_ms", flow.cookie_poll_interval_ms)
            ),
            ignore_https_errors=bool(
                _pick(override, "ignore_https_errors", flow.ignore_https_errors)
            ),
            after_submit_ms=int(_pick(override, "after_submit_ms", flow.after_submit_ms)),
            extra_http_headers={
                str(k): str(v)
                for k, v in (
                    override.get("extra_http_headers") or flow.extra_http_headers
                ).items()
            },
        )
    return flow


def resolve_transport(extra: dict[str, Any]) -> TransportOptions:
    """``preset.transport`` ← ``extra.transport`` 合并。基线同样取自预设。"""
    preset = get_preset(extra.get("preset"))
    base = preset.transport if preset is not None else TransportOptions()
    override = extra.get("transport") if isinstance(extra.get("transport"), dict) else {}
    if not override:
        return base
    return replace(
        base,
        insecure_tls=bool(_pick(override, "insecure_tls", base.insecure_tls)),
        browser_user_agent=bool(_pick(override, "browser_user_agent", base.browser_user_agent)),
        max_retries=int(_pick(override, "max_retries", base.max_retries) or 0),
        extra_body=dict(_pick(override, "extra_body", base.extra_body) or {}),
    )


def resolve_probe(extra: dict[str, Any]) -> ProbeSpec:
    """``preset.probe`` ← ``extra.probe`` 合并。基线同样取自预设。"""
    preset = get_preset(extra.get("preset"))
    base = preset.probe if preset is not None else ProbeSpec()
    override = extra.get("probe") if isinstance(extra.get("probe"), dict) else {}
    if not override:
        return base
    return replace(
        base,
        kind=str(_pick(override, "kind", base.kind)),
        path=str(_pick(override, "path", base.path)),
        scope=str(_pick(override, "scope", base.scope)),
        parser=str(_pick(override, "parser", base.parser)),
    )


def origin_of(base_url: str) -> str:
    """从 base_url 取 scheme://host[:port]。注册表类探测要挂站点根，不是路径前缀。"""
    from urllib.parse import urlsplit

    parts = urlsplit((base_url or "").strip())
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}"
