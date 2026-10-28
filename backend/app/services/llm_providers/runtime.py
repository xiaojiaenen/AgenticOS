"""把 :class:`ProviderSpec` 变成可用的 LLM 网关，以及分阶段连通性诊断。

两种认证方式在这里汇合：

- **API Key**：走标准 Bearer，交给 wuwei 现有的 ``OpenAIAdapter``；
- **Cookie**：继承 ``OpenAIAdapter``，只替换 ``client``。继承是刻意的 ——
  请求组装、工具调用、流式解析都不需要重写，也不会因为上游 sdk 升级就失效。

需要处理的企业网关差异只有两类，其余全部走标准路径：

1. **TLS**：内网自签证书必须显式放行，否则报错只有一句 SSL handshake，
   完全看不出是证书问题；
2. **请求体**：``enable_thinking`` 这类字段只能走 ``extra_body``。openai SDK
   2.x 的 ``create()`` 没有 ``**kwargs``，平铺成关键字参数会抛 ``TypeError``；
3. **路径前缀**：企业网关把 OpenAI 接口挂在 ``/agents/gateway`` 下而不是 ``/v1``，
   由 ``base_url`` 吸收即可 —— SDK 会自己拼出 ``{base_url}/chat/completions``，
   实测打到的就是 ``/agents/gateway/chat/completions``，响应体是标准 OpenAI
   形态（``reasoning_content`` / ``tool_calls`` 都按标准解析），因此解析层
   不需要任何适配。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.llm_providers import credentials
from app.services.llm_providers.presets import (
    TransportOptions,
    origin_of,
    resolve_probe,
    resolve_transport,
)
from app.services.llm_providers.spec import (
    PROVIDER_TYPE_ENTERPRISE_COOKIE,
    ProviderSpec,
    env_provider_spec,
)

logger = logging.getLogger("agenticos.llm.runtime")

# Cookie 认证时 SDK 仍要求一个 api_key。用固定占位符而非随机串，
# 便于在上游日志里一眼认出「这是本系统发的请求」。
COOKIE_PLACEHOLDER_API_KEY = "agenticos-cookie-auth"

# 企业网关普遍有 UA 层面的防护（有些网关甚至有反调试脚本），用浏览器 UA 比
# "AgenticOS/1.0" 这种自报家门的串通过率高得多。
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 连通性测试超时（比对话超时短得多：测试要在界面上等得起来）
_TEST_TIMEOUT_SECONDS = 15.0
# 深度检测里发一条真实对话，给足首字时间但不无限等
_CHAT_TIMEOUT_SECONDS = 60.0

# wuwei 的三处缺陷（usage 收尾帧被吞 / 工具调用在非标 finish_reason 下丢失 /
# 非流式缺 usage 崩）与流式重试，统一在 adapter 模块里补，这里只负责装配。


class ProviderUnavailable(RuntimeError):
    """当前提供商无法构建可用网关（缺 Key / Cookie 失效 / 未装浏览器）。"""


def _request_headers(transport: TransportOptions, *, cookie: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {}
    headers["User-Agent"] = BROWSER_USER_AGENT if transport.browser_user_agent else "AgenticOS/1.0"
    if cookie:
        headers["Cookie"] = cookie
    return headers


def build_http_client(transport: TransportOptions, *, timeout: float) -> httpx.AsyncClient:
    """按预设构造 httpx 客户端。

    单独抽出来是因为 SDK 客户端与裸 httpx 探测都要用同一套 TLS 策略 ——
    两处不一致会出现「探测通过、真实调用失败」这种最难排查的组合。
    """
    return httpx.AsyncClient(
        timeout=timeout,
        verify=not transport.insecure_tls,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )


def _build_cookie_adapter(
    *,
    cookie: str,
    model: str,
    base_url: str,
    transport: TransportOptions,
    timeout: float,
    **default_params: Any,
):
    """带 Cookie 头的 OpenAI 适配器。

    继承 ``HardenedOpenAIAdapter`` 而不是裸 ``OpenAIAdapter``：Cookie 类网关
    往往是「响应标准、周边不标准」的形态，三处容错对它同样必要。

    **必须走父类的 ``__init__``**（用 ``client=`` 注入点传入自建客户端），
    不要手写字段赋值。曾经图省事直接写 ``self.client = ...``，
    结果父类 ``__init__`` 里设置的字段（``supports_reasoning_content`` /
    ``output_token_parameter`` / ``owns_client`` 等）全部缺失 ——
    wuwei 3.0.2 的 ``build_request`` 不读这些字段所以一直没暴露，
    升到 3.2.1 后第一行就 ``AttributeError``。

    父类的字段清单会随上游版本变，手写一份必然会漏。走 ``client=`` 注入点，
    上游新增什么字段都不用我们管。
    """
    from openai import AsyncOpenAI

    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    client = AsyncOpenAI(
        api_key=COOKIE_PLACEHOLDER_API_KEY,
        base_url=base_url,
        default_headers=_request_headers(transport, cookie=cookie),
        http_client=build_http_client(transport, timeout=timeout),
        max_retries=transport.max_retries,
        timeout=timeout,
    )

    class CookieAuthAdapter(HardenedOpenAIAdapter):
        """Cookie 类网关：只换认证方式，其余行为完全继承标准适配器。"""

    return CookieAuthAdapter(
        api_key=COOKIE_PLACEHOLDER_API_KEY,
        model=model,
        base_url=base_url,
        client=client,
        owns_client=True,
        **default_params,
    )


def _new_gateway(config: dict[str, Any]) -> Any:
    """构造带流式重试的网关（适配器仍是 wuwei 默认的）。"""
    from app.services.llm_providers.adapter import RetryingGateway

    return RetryingGateway(config, stream_attempts=get_settings().llm_stream_retry_attempts)


def _build_gateway(config: dict[str, Any], *, max_retries: int = 0) -> Any:
    """构造网关并换上加固适配器。

    ``LLMGateway`` 内部把适配器硬编码成 ``OpenAIAdapter``（没有注入点），所以在
    构造后替换 —— 用的是公开属性 ``adapter``，不是私有成员。被替换掉的那个
    适配器没有发过请求，不会建立连接，直接丢弃即可。

    ``max_retries`` 默认 0：**重试统一交给网关/加固层**。让 SDK 自己也重试一遍，
    实际次数会变成两层相乘，既不可预期，4xx 时还会白烧配额。
    """
    from app.services.llm_providers.adapter import HardenedOpenAIAdapter

    gateway = _new_gateway(config)
    gateway.adapter = HardenedOpenAIAdapter(
        api_key=config["api_key"],
        model=config.get("model", ""),
        base_url=config.get("base_url"),
        temperature=config.get("temperature", 0.2),
        max_tokens=config.get("max_tokens", 4096),
        max_retries=max(0, max_retries),
        **(
            {"extra_body": config["extra_body"]}
            if config.get("extra_body")
            else {}
        ),
        **{
            key: config[key]
            for key in ("top_p", "presence_penalty", "frequency_penalty", "seed")
            if key in config
        },
        **(
            {"output_token_parameter": config["output_token_parameter"]}
            if config.get("output_token_parameter")
            else {}
        ),
    )
    return gateway


def _attach_route(
    gateway: Any,
    *,
    spec: ProviderSpec,
    model: str,
    lease: Any | None,
) -> None:
    """把「这次实际走了哪条路由」挂到网关，供用量记账落审计列。

    环境变量兜底路径没有 ``provider_id``（库里没有对应记录），此时只记
    ``slug`` 与模型 —— 界面要能看出「这条用量其实没走提供商配置」。
    """
    from app.services.llm_providers.route import attach_route

    attach_route(
        gateway,
        provider_id=spec.provider_id,
        provider_slug=spec.slug,
        provider_name=spec.name,
        model=model,
        credential_id=getattr(lease, "credential_id", None) if lease else None,
        account_label=getattr(lease, "label", None) if lease else None,
    )


def build_gateway(
    spec: ProviderSpec,
    *,
    max_tokens: int,
    timeout: int,
    model: str | None = None,
):
    """按提供商构建 wuwei ``LLMGateway``。

    ``model`` 留空表示用提供商自己配置的模型 —— 调用方不该拿全局默认模型
    去覆盖提供商配置，否则「切换提供商」会变成「切换地址但模型还是旧的」。
    """

    transport = resolve_transport(spec.extra)
    resolved_model = (model or spec.model or get_settings().openai_model).strip()
    effective_max_tokens = spec.max_tokens or max_tokens
    effective_timeout = spec.timeout_seconds or timeout

    config: dict[str, Any] = {
        "provider": "openai",
        "model": resolved_model,
        "base_url": spec.base_url,
        "max_tokens": effective_max_tokens,
        "timeout": effective_timeout,
        # 与 transport.max_retries 对齐：SDK 的默认 2 次重试对 Cookie 认证
        # 是纯浪费（401 只会再撞一次），但 API Key 类保留一次重试更稳。
        "retry": {"max_attempts": max(1, transport.max_retries + 1)},
    }
    if transport.extra_body:
        config["extra_body"] = dict(transport.extra_body)

    # 采样参数是「提供商级默认值」，只接受 OpenAI 认识的键；其余键放行会
    # 在 create() 处炸成 TypeError，所以统一在 spec 层做白名单校验。
    for key in ("temperature", "top_p", "presence_penalty", "frequency_penalty", "seed"):
        if key in spec.extra:
            config[key] = spec.extra[key]
    # o1 / o3 / gpt-5 这类推理模型只认 max_completion_tokens，给 max_tokens 会 400。
    # wuwei 3.2.1 的适配器会 pop 掉它并据此改写请求体。
    if "output_token_parameter" in spec.extra:
        config["output_token_parameter"] = spec.extra["output_token_parameter"]

    if spec.provider_type == PROVIDER_TYPE_ENTERPRISE_COOKIE:
        lease = credentials.acquire(spec.provider_id or 0)
        if lease is None:
            raise ProviderUnavailable(
                f"提供商「{spec.name}」的登录态不可用（账号池里没有可用账号）"
            )
        gateway = _new_gateway({**config, "api_key": COOKIE_PLACEHOLDER_API_KEY})
        # 适配器整体替换，而不是改它的内部属性
        gateway.adapter = _build_cookie_adapter(
            cookie=lease.cookie,
            model=resolved_model,
            base_url=spec.base_url,
            transport=transport,
            timeout=float(effective_timeout),
            max_tokens=effective_max_tokens,
            # 采样参数要与 API Key 路径一致：LLMGateway 给标准适配器的默认
            # temperature 是 0.2，这里自己造适配器，不显式传就会变成「同一条
            # 提供商配置，换认证方式后生成风格变了」。
            temperature=config.get("temperature", 0.2),
            **({"extra_body": dict(transport.extra_body)} if transport.extra_body else {}),
            **{
                key: value
                for key, value in config.items()
                if key in ("top_p", "presence_penalty", "frequency_penalty", "seed")
            },
            **(
                {"output_token_parameter": config["output_token_parameter"]}
                if "output_token_parameter" in config
                else {}
            ),
        )
        # 路由快照：提供商 / 实际模型 / 选中账号。上层记账时读它落审计列，
        # 但**不**用它来归属用量（归属永远是发起请求的用户）。
        _attach_route(
            gateway,
            spec=spec,
            model=resolved_model,
            lease=lease,
        )
        return gateway

    if not spec.api_key:
        raise ProviderUnavailable(f"提供商「{spec.name}」未配置 API Key")
    config["api_key"] = spec.api_key
    gateway = _build_gateway(config)
    # API Key 型没有账号池，凭据维度恒为空
    _attach_route(gateway, spec=spec, model=resolved_model, lease=None)
    return gateway


def build_gateway_for_active_provider(
    *,
    max_tokens: int,
    timeout: int,
    model: str | None = None,
    spec: ProviderSpec | None = None,
):
    """解析当前提供商并构建网关，必要时回落环境变量。

    回落是有意的容错：Cookie 过期时全站对话直接不可用是很糟的体验，而且
    定时任务可能还没跑到。回落会打 WARNING 并把原因写进日志，便于发现
    「配置早就烂了但一直没人管」。要求严格走企业网关的部署可以把
    ``LLM_PROVIDER_FALLBACK_TO_ENV`` 关掉，此时直接抛错。
    """
    from app.services.llm_providers.spec import resolve_active_provider

    active = spec or resolve_active_provider()
    try:
        return build_gateway(active, max_tokens=max_tokens, timeout=timeout, model=model)
    except ProviderUnavailable as exc:
        if not get_settings().llm_provider_fallback_to_env:
            raise
        logger.warning("提供商「%s」不可用（%s），回落环境变量配置", active.name, exc)
        fallback = env_provider_spec()
        if not fallback.api_key:
            raise ProviderUnavailable(
                f"提供商「{active.name}」不可用（{exc}），且环境变量未配置兜底 Key"
            ) from exc
        return build_gateway(fallback, max_tokens=max_tokens, timeout=timeout, model=model)


# ---------------------------------------------------------------------------
# 分阶段连通性诊断
# ---------------------------------------------------------------------------


def _stage(name: str, ok: bool, started: float, **detail: Any) -> dict[str, Any]:
    return {
        "stage": name,
        "ok": ok,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **{k: v for k, v in detail.items() if v is not None},
    }


def _probe_url(spec: ProviderSpec) -> str:
    from app.services.llm_providers.presets import resolve_probe

    probe = resolve_probe(spec.extra)
    base = spec.base_url.rstrip("/")
    if probe.scope == "origin":
        base = origin_of(spec.base_url) or base
    return f"{base}{probe.path}"


def _chat_url(spec: ProviderSpec) -> str:
    return f"{spec.base_url.rstrip('/')}/chat/completions"


async def _probe_network(spec: ProviderSpec, transport: TransportOptions) -> dict[str, Any]:
    """只验证 TCP + TLS 能通。

    4xx 也算通过：很多网关对根路径返回 404，那说明 HTTP 已经活着。
    """
    started = time.monotonic()
    url = origin_of(spec.base_url) or spec.base_url
    try:
        async with build_http_client(transport, timeout=_TEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=_request_headers(transport))
        return _stage("network", True, started, url=url, status_code=response.status_code)
    except Exception as exc:  # noqa: BLE001
        hint = ""
        text = str(exc).lower()
        if "certificate" in text or "ssl" in text or "verify" in text:
            hint = "看起来是证书校验失败：该站点用自签证书，需要开启「跳过 TLS 校验」"
        elif "name or service not known" in text or "nodename" in text:
            hint = "域名无法解析：检查 DNS 或是否在正确的内网环境中"
        elif "connection refused" in text:
            hint = "连接被拒绝：地址或端口不对"
        return _stage(
            "network", False, started, url=url,
            message=f"{exc}"[:300], hint=hint or None,
        )


def _key_shape_hint(spec: ProviderSpec, *, cookie: str | None) -> str | None:
    """Key 形态自检：把「认证被拒」最常见的三种低级错误直接说出来。

    这一条是实测踩出来的 —— 有人把网关名字（``magpie``，6 个字符）当成 Key
    填了进去，界面上只显示「认证被拒绝：Cookie 可能已失效」，完全指不到问题。
    """
    if cookie:
        return None
    key = spec.api_key or ""
    if not key:
        return None
    if key != key.strip() or "\n" in key or "\r" in key:
        return "Key 首尾带空白或换行：复制时多选了字符，重新粘贴一次"
    if len(key) < 16:
        return f"Key 只有 {len(key)} 个字符，明显短于常见网关 Key（sk- 开头通常 40+ 字符）：很可能填成了网关名称或占位符"
    if key.lower().startswith("bearer "):
        return "Key 里带上了 'Bearer ' 前缀：只填密钥本身，系统会自己加 Authorization 头"
    return None


def _auth_rejection(
    spec: ProviderSpec,
    *,
    url: str,
    started: float,
    status_code: int,
    body: str,
    cookie: str | None,
) -> dict[str, Any]:
    """把 401/403 翻译成「谁的错、下一步改什么」。

    401 与 403 的语义完全不同，不能共用一句话：
    - 401 = 这份凭据不被接受（Key 错 / 过期 / Cookie 失效）；
    - 403 = 凭据被接受了，但这条接口不给它用（企业网关的 ``/models``
      常常只对管理员开放），这时判「认证失败」是误杀。
    """
    body_snippet = (body or "").strip()[:600]
    if status_code == 401:
        if cookie:
            message = "认证被拒绝（HTTP 401）：登录态 Cookie 已失效或不被接受"
            hint = "点「立即登录」刷新 Cookie；若刚登录过仍 401，检查 Cookie 是否取自同一站点域"
        else:
            message = "认证被拒绝（HTTP 401）：上游不认这个 API Key"
            hint = _key_shape_hint(spec, cookie=cookie) or (
                "核对 Key 是否属于这个网关（不是别家的）、是否已过期或被禁用；"
                "base_url 要包含接口前缀（多数网关是 /v1）"
            )
    else:
        if cookie:
            message = "接口拒绝访问（HTTP 403）：Cookie 有效但该账号没有这个接口的权限"
            hint = "403 通常只是权限问题，不代表登录态失效；改用对话接口验证更准"
        else:
            message = "接口拒绝访问（HTTP 403）：Key 已被接受，但无权访问探测端点"
            hint = "很多 OpenAI 兼容网关只对管理员开放 /models，这不影响对话；将自动改测 /chat/completions"
    return _stage(
        "auth", False, started, url=url, status_code=status_code,
        # 结论与原文分开：``message`` 是给人看的一句话，``detail`` 是上游原文。
        # 混在一起写进正文会让同一段 JSON 在摘要、阶段、对话复核里重复三遍，
        # 把真正有用的提示（例如「Key 只有 6 个字符」）挤到看不见。
        message=message,
        hint=hint,
        detail=body_snippet or None,
        auth_kind="cookie" if cookie else "bearer",
    )


async def _probe_registry(
    spec: ProviderSpec,
    transport: TransportOptions,
    headers: dict[str, str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """验证认证是否通过，并顺手把模型清单拉回来。

    「用的是 Cookie 还是 Bearer」由 ``spec.provider_type`` 判定，不从调用方
    额外传参：探测函数保持三参数签名，既有调用方与测试不必跟着改。
    """
    from app.services.llm_providers.discovery import parse_models_payload

    cookie = "cookie" if spec.provider_type == PROVIDER_TYPE_ENTERPRISE_COOKIE else None
    probe = resolve_probe(spec.extra)
    url = _probe_url(spec)
    started = time.monotonic()
    try:
        async with build_http_client(transport, timeout=_TEST_TIMEOUT_SECONDS) as client:
            response = await client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001
        return _stage("auth", False, started, url=url, message=str(exc)[:300]), []

    if response.status_code in (401, 403):
        return (
            _auth_rejection(
                spec, url=url, started=started,
                status_code=response.status_code,
                body=response.text[:400],
                cookie=cookie,
            ),
            [],
        )
    if response.status_code >= 400:
        return (
            _stage(
                "auth", False, started, url=url, status_code=response.status_code,
                message=f"探测端点返回 HTTP {response.status_code}",
                detail=response.text[:600] or None,
            ),
            [],
        )

    models: list[dict[str, Any]] = []
    try:
        models = parse_models_payload(response.json(), parser=probe.parser)
    except Exception:  # noqa: BLE001 —— 非 JSON 不影响「认证通过」的结论
        logger.debug("提供商 %s 的探测端点返回非 JSON", spec.slug)

    return (
        _stage(
            "auth", True, started, url=url, status_code=response.status_code,
            model_count=len(models),
        ),
        models,
    )


async def _probe_chat(
    spec: ProviderSpec,
    transport: TransportOptions,
    headers: dict[str, str],
    *,
    model: str,
    with_tools: bool,
) -> dict[str, Any]:
    """发一条真实的最小对话。

    这是唯一能回答「到底能不能用」的检查：认证通过、模型清单也拿到了，但
    模型名填错、请求体字段被网关拒绝、工具调用不透传，都只有真打一次才知道。
    """
    label = "tools" if with_tools else "chat"
    started = time.monotonic()
    url = _chat_url(spec)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "回复 ok 两个字符即可"}],
        "stream": False,
    }
    payload.update(transport.extra_body or {})
    if with_tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "占位工具，仅用于验证网关是否透传 function calling",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        payload["tool_choice"] = "auto"

    try:
        async with build_http_client(transport, timeout=_CHAT_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers={**headers, "Content-Type": "application/json"}, json=payload)
    except Exception as exc:  # noqa: BLE001
        return _stage(label, False, started, url=url, message=str(exc)[:300])

    if response.status_code >= 400:
        text = response.text[:600]
        # 结论一句话 + 原文进 detail：对话阶段的失败原因（模型名、鉴权、字段被拒）
        # 各不相同，正文只给结论，排查时再展开原文。
        if "Model Not Exist" in text or "model_not_found" in text or "knows no model" in text:
            message = "模型名不被上游接受"
            hint = "模型名不对：请填上游注册表里的 name（不是 model ID）"
        elif response.status_code in (401, 403):
            message = "对话接口也拒绝了这份凭据"
            hint = (
                "认证在这一步被拒绝：对话接口也拒了这份凭据，"
                "说明 Key 或 Cookie 本身无效，不是 /models 的权限问题"
            )
        else:
            message = f"对话请求被拒绝（HTTP {response.status_code}）"
            hint = None
        return _stage(
            label, False, started, url=url, status_code=response.status_code,
            message=message, hint=hint, detail=text or None,
        )

    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        return _stage(
            label, False, started, url=url, status_code=response.status_code,
            message="响应不是 JSON（很可能打到了 SPA 的 catch-all 页面，检查 base_url 前缀）",
        )

    choices = body.get("choices") or []
    message = (choices[0] or {}).get("message") or {} if choices else {}
    tool_calls = message.get("tool_calls") or []
    content = (message.get("content") or "")[:120]
    usage = body.get("usage") or {}

    if with_tools:
        # 不强制要求模型真的调工具（它可能判断不需要），但必须能看到响应的
        # 结构是 OpenAI 兼容的；若 finish_reason 是 stop 且无 tool_calls，
        # 只能证明「tools 字段被接受」，不能证明「工具调用链路可用」。
        return _stage(
            "tools", True, started, url=url, status_code=response.status_code,
            accepted=True,
            returned_tool_calls=bool(tool_calls),
            message="网关接受 tools 字段" + ("，并返回了 tool_calls" if tool_calls else "（本次未触发工具调用）"),
        )

    return _stage(
        "chat", True, started, url=url, status_code=response.status_code,
        content=content,
        total_tokens=usage.get("total_tokens"),
        has_reasoning=bool(message.get("reasoning_content") or message.get("reasoning")),
    )


async def _probe_stream(
    spec: ProviderSpec,
    transport: TransportOptions,
    headers: dict[str, str],
    *,
    model: str,
) -> dict[str, Any]:
    """验证 SSE 流式可用。

    非流式通过不等于流式通过：站点把 ``/chat/completions`` 兜底成 HTML 200
    时，非流式会报「响应不是 JSON」，而流式会拿到一堆 HTML 文本；反过来某些
    网关只对 ``stream_options`` 报 400。界面用的是流式，所以这一阶段不能省。
    """
    started = time.monotonic()
    url = _chat_url(spec)
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "回复 ok"}],
        "stream": True,
    }
    payload.update(transport.extra_body or {})

    frames = 0
    text: list[str] = []
    content_type = ""
    try:
        async with build_http_client(transport, timeout=_CHAT_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST",
                url,
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            ) as response:
                content_type = response.headers.get("content-type", "")
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")[:600]
                    if "Model Not Exist" in body or "model_not_found" in body:
                        message = "流式请求：模型名不被上游接受"
                        hint = "模型名不对：请填上游注册表里的 name（不是 model ID）"
                    else:
                        message = f"流式请求被拒绝（HTTP {response.status_code}）"
                        hint = None
                    return _stage(
                        "stream", False, started, url=url,
                        status_code=response.status_code,
                        message=message, hint=hint, detail=body or None,
                    )
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    frames += 1
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text.append(str(delta["content"]))
    except Exception as exc:  # noqa: BLE001
        return _stage("stream", False, started, url=url, message=str(exc)[:300])

    if frames == 0:
        return _stage(
            "stream", False, started, url=url,
            message=f"没有收到任何 SSE 帧（content-type={content_type or '空'}）",
            hint="很可能打到了 SPA 的 catch-all 页面，检查 base_url 是否少了接口前缀",
        )
    return _stage(
        "stream", True, started, url=url,
        frames=frames, content="".join(text)[:40], content_type=content_type,
    )


def _summarize(spec: ProviderSpec, stages: list[dict[str, Any]], models: list[dict[str, Any]]) -> dict[str, Any]:
    failed = next((item for item in stages if not item["ok"]), None)
    names = [item["model_name"] for item in models if item.get("model_name")]
    configured = spec.model or ""
    # 阶段里带的补充说明（例如「/models 受限但对话通过」）要在总结果里露出来，
    # 否则全部通过时只剩一句「全部检查通过」，管理员看不到那个差异。
    note = next((item.get("note") for item in stages if item.get("note")), None)
    return {
        "ok": failed is None,
        "stage": (failed or stages[-1])["stage"],
        "message": (failed or {}).get("message") or "全部检查通过",
        "hint": (failed or {}).get("hint"),
        "note": note,
        "stages": stages,
        "url": (failed or stages[-1]).get("url"),
        "status_code": (failed or stages[-1]).get("status_code"),
        "elapsed_ms": sum(item["elapsed_ms"] for item in stages),
        "models": [item["model_key"] for item in models][:50] or None,
        "model_names": names[:50] or None,
        "model_count": len(models),
        "configured_model_available": (configured in names) if (configured and names) else None,
    }


async def test_provider(spec: ProviderSpec, *, deep: bool = False) -> dict[str, Any]:
    """分阶段连通性测试。

    ``deep=False`` 只做 网络 → 认证 → 模型清单；``deep=True`` 再发一条真实
    对话、一次流式、一次带 ``tools`` 的请求。分成两档是因为后者会真实消耗
    上游额度，不该在每次点开设置页时自动跑。

    关键约束：**只有认证阶段失败才标记账号失效**。旧实现拿 ``/models`` 的
    403 当认证失败，而 403 在企业网关上常常只是「这个接口要 admin 权限」，
    结果是点一次测试按钮就把一份完全有效的 Cookie 判死。

    对 API Key 类提供商还多一层补救：``/models`` 被 401/403 拒掉时，直接用
    配置的模型打一次对话。很多 OpenAI 兼容网关（含本地代理）只把模型清单
    留给管理员，对话接口却是通的 —— 只凭 ``/models`` 判「认证失败」会让人
    去改一个本来正确的 Key。
    """
    transport = resolve_transport(spec.extra)
    stages: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []

    cookie: str | None = None
    lease = None
    if spec.provider_type == PROVIDER_TYPE_ENTERPRISE_COOKIE:
        lease = credentials.acquire(spec.provider_id or 0)
        if lease is None:
            return {
                "ok": False,
                "stage": "auth",
                "message": "账号池里没有可用账号：请先自动登录或手动填写 Cookie",
                "hint": "若账号显示 expired，点「立即登录」；若显示 failed，先看 last_error",
                "stages": [],
                "elapsed_ms": 0,
            }
        cookie = lease.cookie
    elif not spec.api_key:
        return {"ok": False, "stage": "auth", "message": "未配置 API Key", "stages": [], "elapsed_ms": 0}

    headers = _request_headers(transport, cookie=cookie)
    if spec.api_key and not cookie:
        headers["Authorization"] = f"Bearer {spec.api_key}"

    network = await _probe_network(spec, transport)
    stages.append(network)

    auth_ok = False
    if network["ok"]:
        auth_stage, models = await _probe_registry(spec, transport, headers)
        auth_ok = auth_stage["ok"]

        # /models 被拒但 Key 可能是好的：用真实对话接口复核一次。
        # 先占住认证阶段的位置，复核通过后再原地改写成「认证有效」——
        # 摘要取「第一个失败阶段」，不能让一条被推翻的结论留在列表最前面。
        auth_index = len(stages)
        stages.append(auth_stage)
        if (
            not auth_ok
            and cookie is None
            and spec.model
            and auth_stage.get("status_code") in (401, 403)
        ):
            chat_check = await _probe_chat(
                spec, transport, headers, model=spec.model, with_tools=False
            )
            stages.append(chat_check)
            if chat_check["ok"]:
                stages[auth_index] = {
                    **auth_stage,
                    "ok": True,
                    "message": (
                        f"探测端点返回 HTTP {auth_stage.get('status_code')}，"
                        "但对话接口通过 —— 认证本身有效，仅模型清单接口受限"
                    ),
                    "note": (
                        f"模型清单接口返回 HTTP {auth_stage.get('status_code')}（通常是权限限制），"
                        "对话接口已验证可用，无需修改 Key"
                    ),
                    "hint": "无需改 Key；主对话模型已能调用，模型清单可留空",
                }
                auth_ok = True

        if not auth_ok and auth_stage.get("status_code") in (401, 403) and lease is not None:
            credentials.mark_cookie_invalid(
                lease.credential_id, f"连通性测试认证失败 HTTP {auth_stage['status_code']}"
            )

    if deep and auth_ok:
        model_name = spec.model or next(
            (item["model_name"] for item in models if item.get("task_type") == "text-generation"),
            "",
        )
        if not model_name:
            stages.append(
                {
                    "stage": "chat",
                    "ok": False,
                    "elapsed_ms": 0,
                    "message": "未配置模型名，且模型清单里没有文本生成模型",
                    "hint": "先在「模型」里发现一次，再指定主对话模型",
                }
            )
        else:
            # 上面对话复核已经跑过 chat 了，这里不重复消耗额度
            already_chatted = any(item["stage"] == "chat" and item["ok"] for item in stages)
            chat_stage = next(
                (item for item in stages if item["stage"] == "chat" and item["ok"]), None
            ) if already_chatted else None
            if chat_stage is None:
                chat_stage = await _probe_chat(
                    spec, transport, headers, model=model_name, with_tools=False
                )
                stages.append(chat_stage)
            if chat_stage["ok"]:
                # 顺序放在 tools 之前：界面实际走流式，先把流式确认掉
                stream_stage = await _probe_stream(
                    spec, transport, headers, model=model_name
                )
                stages.append(stream_stage)
                if stream_stage["ok"]:
                    stages.append(
                        await _probe_chat(spec, transport, headers, model=model_name, with_tools=True)
                    )
            elif chat_stage.get("status_code") in (401, 403) and lease is not None:
                credentials.mark_cookie_invalid(
                    lease.credential_id, "对话阶段认证失败 HTTP 401/403"
                )

    return _summarize(spec, stages, models)
