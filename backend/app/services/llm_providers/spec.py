"""AI 提供商的解析与配置管理。

这里的核心职责只有一个：**回答「现在该用哪个大模型后端」**。

解析顺序（前者优先）：

1. 数据库里 ``enabled=true AND is_default=true`` 的提供商；
2. 数据库里第一个启用的提供商（管理员没显式指定默认时）；
3. **环境变量兜底**（``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` / ``OPENAI_MODEL``）。

第 3 步不是历史包袱，而是升级通道：存量部署只要不新建提供商，行为与
改造前完全一致，不会因为加了这张表就必须先配置才能开机。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.encryption import decrypt_safe, encrypt
from app.db.models import LlmProviderCredentialModel, LlmProviderModel
from app.db.session import create_db_session

logger = logging.getLogger("agenticos.llm.providers")

# 认证方式，不是厂商。绝大多数厂商都落在第一类，换厂商只改配置不改代码。
PROVIDER_TYPE_OPENAI = "openai_compatible"
PROVIDER_TYPE_ENTERPRISE_COOKIE = "enterprise_cookie"
PROVIDER_TYPES = (PROVIDER_TYPE_OPENAI, PROVIDER_TYPE_ENTERPRISE_COOKIE)

PROVIDER_TYPE_LABELS = {
    PROVIDER_TYPE_OPENAI: "OpenAI 兼容（API Key）",
    PROVIDER_TYPE_ENTERPRISE_COOKIE: "企业网关（Cookie）",
}

# 环境变量兜底规格的伪 slug：只用于对外展示「当前生效的是兜底配置」
ENV_PROVIDER_SLUG = "__env__"

# 解析结果进程内缓存。提供商切换频率极低，而 agent 构建是热路径，
# 每次对话都查一次库没有意义。写入侧调用 invalidate_cache() 立即失效。
_CACHE_TTL_SECONDS = 5.0
_cache: tuple[float, "ProviderSpec"] | None = None


@dataclass(frozen=True)
class ProviderSpec:
    """一份可直接用于构建 LLM 的提供商配置。

    与 ORM 模型刻意分开：``api_key`` 是**解密后的明文**，只应活在内存里，
    不应该有任何一个函数把 ``LlmProviderModel`` 直接传给调用方。
    """

    name: str
    slug: str
    provider_type: str
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: int = 300
    max_tokens: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    provider_id: int | None = None
    source: str = "database"

    @property
    def needs_cookie(self) -> bool:
        return self.provider_type == PROVIDER_TYPE_ENTERPRISE_COOKIE

    def describe(self) -> dict[str, Any]:
        """不含任何密钥的描述，可安全返回给前端或写入日志。"""
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "slug": self.slug,
            "provider_type": self.provider_type,
            "base_url": self.base_url,
            "model": self.model,
            "source": self.source,
            "needs_cookie": self.needs_cookie,
        }


def invalidate_cache() -> None:
    """配置或凭据变更后调用，让下一次解析立即读到新值。"""
    global _cache
    _cache = None


def parse_extra(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _spec_from_row(row: LlmProviderModel) -> ProviderSpec:
    return ProviderSpec(
        name=row.name,
        slug=row.slug,
        provider_type=row.provider_type,
        base_url=(row.base_url or "").rstrip("/"),
        model=row.model or "",
        api_key=decrypt_safe(row.api_key_encrypted or "", default="") or None,
        timeout_seconds=row.timeout_seconds or 300,
        max_tokens=row.max_tokens,
        extra=parse_extra(row.extra_json),
        provider_id=row.id,
        source="database",
    )


def spec_from_row(row: LlmProviderModel) -> ProviderSpec:
    """把 ORM 行转成可用的规格（解密 API Key）。

    对外暴露而不是让端点自己拼：解密逻辑只应该有一个入口，
    否则很容易在某个端点上忘了解密、或者忘了 rstrip 尾斜杠。
    """
    return _spec_from_row(row)


def env_provider_spec() -> ProviderSpec:
    """环境变量兜底规格。

    ``api_key`` 为空也允许返回 —— 判定「能不能用」是调用方的事，这里只
    负责如实反映配置。否则没配 Key 的部署会连报错信息都拿不到。
    """
    settings = get_settings()
    return ProviderSpec(
        name="环境变量配置",
        slug=ENV_PROVIDER_SLUG,
        provider_type=PROVIDER_TYPE_OPENAI,
        base_url=(settings.openai_base_url or "").rstrip("/"),
        model=settings.openai_model or "",
        api_key=(settings.openai_api_key or "").strip() or None,
        timeout_seconds=settings.llm_timeout,
        source="env",
    )


def resolve_active_provider() -> ProviderSpec:
    """解析当前生效的提供商（带 5 秒进程内缓存）。"""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

    spec = _load_active_provider()
    _cache = (now, spec)
    return spec


def _load_active_provider() -> ProviderSpec:
    try:
        with create_db_session() as db:
            row = db.scalar(
                select(LlmProviderModel)
                .where(
                    LlmProviderModel.enabled.is_(True),
                    LlmProviderModel.is_default.is_(True),
                )
                .order_by(LlmProviderModel.id)
            )
            if row is None:
                # 没有显式默认时，取第一个启用的：总比一个都不认要好
                row = db.scalar(
                    select(LlmProviderModel)
                    .where(LlmProviderModel.enabled.is_(True))
                    .order_by(LlmProviderModel.id)
                )
            if row is not None:
                return _spec_from_row(row)
    except Exception as exc:  # noqa: BLE001 —— 读配置失败不能让对话整体不可用
        logger.warning("读取提供商配置失败，回落环境变量: %s", exc)
    return env_provider_spec()


# ---------------------------------------------------------------------------
# 配置管理（由管理端点调用，全部显式传 session，便于与端点同事务）
# ---------------------------------------------------------------------------


class ProviderConfigError(ValueError):
    """提供商配置非法（由端点转换成 400）。"""


# ``extra`` 允许出现的顶层键。白名单而不是黑名单的理由：这些键会被送进
# 请求构造与登录流程，一个拼错的键（``enable_thinking`` 写在顶层）会被
# 原样带进 ``chat.completions.create()``，而 openai SDK 2.x 没有 **kwargs，
# 结果是每次对话都 TypeError —— 在保存时就拒绝，比运行时崩好得多。
ALLOWED_EXTRA_KEYS = {
    "preset",
    "roles",
    "transport",
    "probe",
    "login",
    # 采样参数：会并入 LLMGateway 的 config，必须是 OpenAI 认识的键
    "temperature",
    "top_p",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    # 输出 token 上限的参数名。o1 / o3 / gpt-5 这类推理模型只认
    # ``max_completion_tokens``，给 ``max_tokens`` 会直接 400。
    # wuwei 3.2.1 的 OpenAIAdapter 会 pop 掉这个键并据此改写请求体，
    # 所以它不会漏进上游请求。
    "output_token_parameter",
}

# ``output_token_parameter`` 的合法取值 —— 只这两个，上游明确拒绝其他值
_OUTPUT_TOKEN_PARAMETERS = {"max_tokens", "max_completion_tokens"}

_SAMPLING_RANGE = {
    "temperature": (0.0, 2.0),
    "top_p": (0.0, 1.0),
    "presence_penalty": (-2.0, 2.0),
    "frequency_penalty": (-2.0, 2.0),
}


def validate_extra(extra: dict[str, Any] | None) -> None:
    """校验 ``extra`` 的结构。

    只做「结构对不对」，不做「值合不合理」—— 上游参数语义各家的差异太大，
    服务端硬校验只会逼运维绕过界面直接改库。
    """
    if extra is None:
        return
    if not isinstance(extra, dict):
        raise ProviderConfigError("extra 必须是对象")

    unknown = set(extra) - ALLOWED_EXTRA_KEYS
    if unknown:
        raise ProviderConfigError(
            "extra 含不支持的键: "
            + "、".join(sorted(unknown))
            + "。需要往请求体塞非标字段请放进 transport.extra_body"
        )

    for key in ("transport", "probe", "login", "roles"):
        if key in extra and not isinstance(extra[key], dict):
            raise ProviderConfigError(f"extra.{key} 必须是对象")

    transport = extra.get("transport")
    if isinstance(transport, dict):
        body = transport.get("extra_body")
        if body is not None and not isinstance(body, dict):
            raise ProviderConfigError("extra.transport.extra_body 必须是对象")

    roles = extra.get("roles")
    if isinstance(roles, dict):
        from app.services.llm_providers.presets import MODEL_ROLES

        unknown_roles = set(roles) - set(MODEL_ROLES)
        if unknown_roles:
            raise ProviderConfigError(
                "extra.roles 含未知用途: " + "、".join(sorted(unknown_roles))
            )

    for key, (low, high) in _SAMPLING_RANGE.items():
        if key not in extra:
            continue
        try:
            value = float(extra[key])
        except (TypeError, ValueError) as exc:
            raise ProviderConfigError(f"extra.{key} 必须是数字") from exc
        if not (low <= value <= high):
            raise ProviderConfigError(f"extra.{key} 必须在 {low}~{high} 之间")

    token_parameter = extra.get("output_token_parameter")
    if token_parameter is not None and token_parameter not in _OUTPUT_TOKEN_PARAMETERS:
        raise ProviderConfigError(
            "extra.output_token_parameter 只支持 "
            + "、".join(sorted(_OUTPUT_TOKEN_PARAMETERS))
            + f"，收到: {token_parameter}"
        )


def resolve_model_for_role(spec: ProviderSpec, role: str | None = None) -> str:
    """按用途取模型名。

    解析顺序：``roles[role]`` → ``roles[chat]`` → 提供商配置的 ``model``。

    退回 ``chat`` 而不是直接报错是刻意的：大多数部署只有一个模型，要求
    为每个用途都显式绑定，会让「刚接上就能用」变成一堆必填项。
    """
    roles = spec.extra.get("roles") if isinstance(spec.extra.get("roles"), dict) else {}
    for key in (role, "chat"):
        if key:
            value = str(roles.get(key) or "").strip()
            if value:
                return value
    return (spec.model or "").strip()


def get_provider(db: Session, provider_id: int) -> LlmProviderModel | None:
    return db.get(LlmProviderModel, provider_id)


def list_providers(db: Session) -> list[LlmProviderModel]:
    return list(
        db.scalars(select(LlmProviderModel).order_by(LlmProviderModel.id)).all()
    )


def _normalize_slug(slug: str) -> str:
    cleaned = (slug or "").strip().lower().replace(" ", "-")
    if not cleaned:
        raise ProviderConfigError("slug 不能为空")
    if len(cleaned) > 64:
        raise ProviderConfigError("slug 最长 64 个字符")
    return cleaned


def validate_provider_payload(
    *,
    provider_type: str,
    base_url: str,
    model: str,
    slug: str,
    name: str,
) -> None:
    if provider_type not in PROVIDER_TYPES:
        raise ProviderConfigError(f"不支持的提供商类型: {provider_type}")
    if not (name or "").strip():
        raise ProviderConfigError("名称不能为空")
    _normalize_slug(slug)
    if not (base_url or "").strip():
        raise ProviderConfigError("base_url 不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise ProviderConfigError("base_url 必须以 http:// 或 https:// 开头")
    # 企业网关的模型名可以留空（由网关决定默认模型），API Key 类型必须给
    if provider_type == PROVIDER_TYPE_OPENAI and not (model or "").strip():
        raise ProviderConfigError("OpenAI 兼容提供商必须指定模型")


def create_provider(
    db: Session,
    *,
    name: str,
    slug: str,
    provider_type: str,
    base_url: str,
    model: str = "",
    api_key: str | None = None,
    timeout_seconds: int = 300,
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
    description: str = "",
    enabled: bool = True,
    is_default: bool = False,
    created_by: int | None = None,
    preset_slug: str | None = None,
) -> LlmProviderModel:
    """新建提供商。

    ``preset_slug`` 给定时用厂商预设补全空缺字段（地址、模型、登录动作、
    传输选项、用途绑定），显式传入的值优先。这样接一家新企业网关时，
    管理员只需要填账号密码，不用照着文档抄六七个路径。
    """
    from app.services.llm_providers.presets import get_preset, merge_preset_into_extra

    preset = get_preset(preset_slug)
    if preset is not None:
        if not (provider_type or "").strip() or (
            provider_type == PROVIDER_TYPE_OPENAI and preset.provider_type != PROVIDER_TYPE_OPENAI
        ):
            # 端点的默认值不能盖住预设：这类企业网关必须走 Cookie 认证
            provider_type = preset.provider_type
        base_url = (base_url or "").strip() or preset.base_url
        model = (model or "").strip() or preset.model
        extra = {**merge_preset_into_extra(preset), **(extra or {})}

    validate_provider_payload(
        provider_type=provider_type, base_url=base_url, model=model, slug=slug, name=name
    )
    validate_extra(extra)
    normalized = _normalize_slug(slug)
    exists = db.scalar(select(LlmProviderModel).where(LlmProviderModel.slug == normalized))
    if exists is not None:
        raise ProviderConfigError(f"slug 已存在: {normalized}")

    row = LlmProviderModel(
        name=name.strip(),
        slug=normalized,
        provider_type=provider_type,
        base_url=base_url.strip().rstrip("/"),
        model=(model or "").strip(),
        api_key_encrypted=encrypt(api_key) if api_key else None,
        timeout_seconds=max(1, int(timeout_seconds or 300)),
        max_tokens=max_tokens,
        extra_json=json.dumps(extra or {}, ensure_ascii=False),
        description=description or "",
        enabled=enabled,
        is_default=False,
        created_by=created_by,
    )
    db.add(row)
    db.flush()

    if is_default:
        set_default_provider(db, row.id)
    elif enabled and not db.scalar(
        select(LlmProviderModel).where(LlmProviderModel.is_default.is_(True))
    ):
        # 第一个提供商自动成为默认，避免「建了但没人用」的困惑。
        # 但停用的提供商不能自动接管：``set_default_provider`` 会拒绝停用项，
        # 那样「先建一个备用提供商且暂不启用」会直接抛错。
        set_default_provider(db, row.id)

    invalidate_cache()
    return row


def update_provider(
    db: Session,
    row: LlmProviderModel,
    *,
    fields: dict[str, Any],
) -> LlmProviderModel:
    """局部更新。``api_key`` 传空字符串表示「清空」，不传表示「保持不变」。

    这个区分是必须的：前端编辑表单永远不回显真实 Key，如果按「空 = 不变」
    处理，管理员就永远无法删掉一把泄露的 Key。
    """
    if "name" in fields:
        name = (fields["name"] or "").strip()
        if not name:
            raise ProviderConfigError("名称不能为空")
        row.name = name
    if "provider_type" in fields:
        if fields["provider_type"] not in PROVIDER_TYPES:
            raise ProviderConfigError(f"不支持的提供商类型: {fields['provider_type']}")
        row.provider_type = fields["provider_type"]
    if "base_url" in fields:
        base_url = (fields["base_url"] or "").strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ProviderConfigError("base_url 必须以 http:// 或 https:// 开头")
        row.base_url = base_url
    if "model" in fields:
        row.model = (fields["model"] or "").strip()
    if "timeout_seconds" in fields and fields["timeout_seconds"] is not None:
        row.timeout_seconds = max(1, int(fields["timeout_seconds"]))
    if "max_tokens" in fields:
        row.max_tokens = fields["max_tokens"]
    if "extra" in fields:
        row.extra_json = json.dumps(fields["extra"] or {}, ensure_ascii=False)
    if "description" in fields:
        row.description = fields["description"] or ""
    if "enabled" in fields and fields["enabled"] is not None:
        row.enabled = bool(fields["enabled"])
    if "api_key" in fields:
        api_key = fields["api_key"]
        row.api_key_encrypted = encrypt(api_key) if api_key else None

    validate_provider_payload(
        provider_type=row.provider_type,
        base_url=row.base_url,
        model=row.model,
        slug=row.slug,
        name=row.name,
    )
    validate_extra(parse_extra(row.extra_json))
    db.flush()
    invalidate_cache()
    return row


def set_default_provider(db: Session, provider_id: int) -> LlmProviderModel:
    row = db.get(LlmProviderModel, provider_id)
    if row is None:
        raise ProviderConfigError("提供商不存在")
    if not row.enabled:
        raise ProviderConfigError("停用的提供商不能设为默认")
    # 全局唯一由这里保证：先全部清零再置一，不依赖部分唯一索引
    for other in db.scalars(
        select(LlmProviderModel).where(LlmProviderModel.is_default.is_(True))
    ).all():
        other.is_default = False
    row.is_default = True
    db.flush()
    invalidate_cache()
    return row


def delete_provider(db: Session, row: LlmProviderModel) -> None:
    credential = db.scalar(
        select(LlmProviderCredentialModel).where(
            LlmProviderCredentialModel.provider_id == row.id
        )
    )
    if credential is not None:
        # 先删凭据：MySQL 会校验外键，SQLite 之外都不允许留下悬挂引用
        db.delete(credential)
        db.flush()
    db.delete(row)
    db.flush()
    invalidate_cache()


def to_public_dict(
    row: LlmProviderModel,
    *,
    credential: LlmProviderCredentialModel | None = None,
    is_active: bool = False,
    account_count: int | None = None,
) -> dict[str, Any]:
    """对外表示。**绝不返回 api_key / password / cookie 的任何片段。**"""
    extra = parse_extra(row.extra_json)
    roles = extra.get("roles") if isinstance(extra.get("roles"), dict) else {}
    payload: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "provider_type": row.provider_type,
        "provider_type_label": PROVIDER_TYPE_LABELS.get(row.provider_type, row.provider_type),
        "base_url": row.base_url,
        "model": row.model,
        "has_api_key": bool(row.api_key_encrypted),
        "timeout_seconds": row.timeout_seconds,
        "max_tokens": row.max_tokens,
        "extra": extra,
        "preset": extra.get("preset"),
        "roles": roles,
        "description": row.description,
        "enabled": row.enabled,
        "is_default": row.is_default,
        "is_active": is_active,
        "needs_cookie": row.provider_type == PROVIDER_TYPE_ENTERPRISE_COOKIE,
        "account_count": account_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if credential is not None:
        payload["credential"] = credential_status_dict(credential)
    elif row.provider_type == PROVIDER_TYPE_ENTERPRISE_COOKIE:
        payload["credential"] = None
    return payload


def credential_status_dict(row: LlmProviderCredentialModel) -> dict[str, Any]:
    """凭据状态。**不返回密码与 Cookie 内容**，只回答「有没有、还能不能用」。"""
    from app.core.timezone import app_now
    from app.services.llm_providers.credentials import MAX_CONSECUTIVE_FAILURES

    expire_at = row.expire_at
    expired = expire_at is not None and expire_at <= app_now()
    status = "expired" if expired and row.status == "active" else row.status
    if row.disabled:
        status = "disabled"
    return {
        "id": row.id,
        "label": row.label or row.username,
        "username": row.username,
        "has_password": bool(row.password_encrypted),
        "has_cookie": bool(row.cookie_encrypted),
        "login_url": row.login_url,
        "status": status,
        "auto_refresh": bool(row.auto_refresh),
        "priority": row.priority,
        "failure_count": row.failure_count,
        "disabled": bool(row.disabled),
        # 供界面提示「这个号已经连续失败到会被轮换排除」
        "excluded_from_rotation": row.failure_count >= MAX_CONSECUTIVE_FAILURES,
        "expire_at": expire_at.isoformat() if expire_at else None,
        "last_login_at": row.last_login_at.isoformat() if row.last_login_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "last_error": row.last_error,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
