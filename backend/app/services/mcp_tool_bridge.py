"""MCP 工具的平台侧包装层。

上游 ``wuwei.mcp.MCPToolAdapter`` 把 MCP 工具转成 wuwei ``Tool`` 时，
只做了一件事：把 ``inputSchema`` 搬到 ``ToolParameters``，handler 直接
``call_tool``。这带来三个平台侧缺口 —— 内网爬虫场景全都撞上：

1. **凭据注入**：MCP 工具的参数由模型填，但「内网站点的登录 Cookie」
   不能进模型上下文。需要平台在**调用前**把 ``$CREDENTIAL.<字段>``
   替换成用户自己配置的凭据（``external_user_credentials``，加密存储）。

2. **用户临时输入**：验证码、一次性口令这类值既不该落库也不该让模型
   编造。需要平台在调用前发现缺参 → 走 ``UserInputBlocker`` 阻塞等用户
   在前端表单里填 → 再带着真实值调用。

3. **凭据不出网**：替换后的凭据只应流向 MCP 服务，不该进日志/审计。

因此这里对 adapter 产出的 Tool 做一层包装：``wrap_mcp_tool`` 返回同名的
新 Tool，handler 换成平台版本。

**为什么不改 site-packages**：与 wuwei 补丁层同一条纪律 —— 只在平台侧
包装，不复制上游逻辑、不修改第三方包。上游改动时这层仍然成立。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger("mcp_service")

# 占位符：$CREDENTIAL.<字段> / $INPUT.<字段>
#
# 字段名只允许字母数字下划线 —— 不含连字符，否则
# "$CREDENTIAL.a-$CREDENTIAL.b" 会把第一个解析成字段 "a-"。
_PLACEHOLDER_RE = re.compile(r"\$(CREDENTIAL|INPUT)\.([A-Za-z0-9_]+)")

# MCP 服务名 → 对应的外部系统 id（用于取用户凭据）。
# 由 mcp_service 在连接时建立：MCP 服务器配置里新增 external_system_id
# 指向一个已配置的「集成」，凭据从那里取。
_CREDENTIAL_SCOPES: dict[str, int] = {}


def set_credential_scope(server_name: str, external_system_id: int | None) -> None:
    """登记「MCP 服务器 → 外部系统」的凭据映射。

    没有映射时，``$CREDENTIAL.x`` 视为缺失（不报错、不猜测）。
    """
    if external_system_id:
        _CREDENTIAL_SCOPES[server_name] = external_system_id
    else:
        _CREDENTIAL_SCOPES.pop(server_name, None)


def credential_scope(server_name: str) -> int | None:
    return _CREDENTIAL_SCOPES.get(server_name)


def _server_of(tool_name: str) -> str:
    """从 ``mcp__<server>__<tool>`` 反解服务器名。

    服务器名本身可能含 ``__``，所以从**右侧**切最后一次分隔符不对 ——
    正确做法是从左侧切第一个分隔符（服务器名按惯例不含前缀冲突，
    而工具名可以含 ``__``）。
    """
    parts = tool_name.split("__", 2)
    if len(parts) < 3 or parts[0] != "mcp":
        return ""
    return parts[1]


def _load_user_credentials(server_name: str, user_id: int) -> dict[str, str]:
    """取该用户在此 MCP 服务对应集成下配置的凭据（明文，仅内存）。"""
    system_id = credential_scope(server_name)
    if not system_id or not user_id:
        return {}
    try:
        from app.db.session import create_db_session
        from app.db.models import ExternalUserCredentialModel
        from app.services.external_system_service import ExternalSystemService

        db = create_db_session()
        try:
            row = db.query(ExternalUserCredentialModel).filter_by(
                user_id=user_id, system_id=system_id
            ).first()
            if row is None or row.connection_status != "connected":
                return {}
            return ExternalSystemService(db).decrypt_credential_data(row)
        finally:
            db.close()
    except Exception:  # noqa: BLE001 —— 取凭据失败不能拖垮工具调用
        logger.debug("加载 MCP 凭据失败 server=%s", server_name, exc_info=True)
        return {}


def _map_strings(
    value: Any,
    fn: Callable[[re.Match[str]], str | None],
    missing: list[str],
) -> Any:
    """递归遍历参数结构，对每个字符串应用 ``fn``。

    ``fn`` 接收一个占位符匹配，命中时返回**替换值**；缺值时返回 ``None``
    并把 ``"<SCOPE>.<字段>"`` 追加到 ``missing``。

    为什么要递归：爬虫工具的参数几乎都是嵌套结构 ——
    ``headers={"X-Token": "$CREDENTIAL.token"}``、
    ``fields=[{"name": "user", "value": "$CREDENTIAL.username"}]``。
    只处理顶层字符串的话，占位符会原样发给内网服务，等于没注入。
    """
    if isinstance(value, str):

        def _sub(match: re.Match[str]) -> str:
            replacement = fn(match)
            return match.group(0) if replacement is None else replacement

        return _PLACEHOLDER_RE.sub(_sub, value)
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            out[key] = _map_strings(item, fn, missing)
        return out
    if isinstance(value, list):
        return [_map_strings(item, fn, missing) for item in value]
    if isinstance(value, tuple):
        return tuple(_map_strings(item, fn, missing) for item in value)
    return value


def _resolve_placeholders(
    values: dict[str, Any],
    *,
    server_name: str,
    user_id: int,
    inputs: dict[str, str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """替换 ``$CREDENTIAL.x``（凭据）与 ``$INPUT.x``（用户输入）。

    返回 ``(替换后的值, 仍缺失的 "<SCOPE>.<字段>" 列表)``。

    - ``$CREDENTIAL.x`` 缺值 → 计入缺失（提示去集成页配置）。
    - ``$INPUT.x`` 缺值 → 计入缺失（需要问用户）；若 ``inputs`` 里已有答案
      （用户已经填过了）则直接替换。

    凭据值不写日志、不进审计 —— 它只流向 MCP 服务。
    """
    creds = _load_user_credentials(server_name, user_id)
    answers = inputs or {}
    missing: list[str] = []

    def _fn(match: re.Match[str]) -> str | None:
        scope, field = match.group(1), match.group(2)
        tag = f"{scope}.{field}"
        if scope == "CREDENTIAL":
            if field in creds:
                return str(creds[field])
            if tag not in missing:
                missing.append(tag)
            return None
        # $INPUT：用户已经给过答案就用答案
        if field in answers:
            return str(answers[field])
        if tag not in missing:
            missing.append(tag)
        return None

    resolved = _map_strings(values, _fn, missing)
    return resolved, missing


def _schema_placeholder_defaults(tool: Any) -> dict[str, Any]:
    """取工具 inputSchema 里**含占位符**的默认值。

    为什么需要：凭据通常声明成参数默认值（``token: str = "$CREDENTIAL.x"``）。
    模型不会主动填它 —— 参数根本不会出现在调用参数里。平台必须自己从
    schema 里把默认值取出来替换掉，否则内网服务收到的是字面量
    ``"$CREDENTIAL.x"``。

    只取**含占位符**的默认值 —— 普通默认值交给服务端自己套用，平台不插手。
    """
    params = getattr(tool, "parameters", None)
    props = getattr(params, "properties", None) or {}
    if not isinstance(props, dict):
        return {}
    out: dict[str, Any] = {}
    for key, spec in props.items():
        if not isinstance(spec, dict) or "default" not in spec:
            continue
        default = spec["default"]
        if _has_placeholder(default):
            out[key] = default
    return out


def _has_placeholder(value: Any) -> bool:
    """结构里是否含占位符（递归）。"""
    if isinstance(value, str):
        return bool(_PLACEHOLDER_RE.search(value))
    if isinstance(value, dict):
        return any(_has_placeholder(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_placeholder(v) for v in value)
    return False


def _needs_user_input(missing: list[str]) -> list[str]:
    return [m.split(".", 1)[1] for m in missing if m.startswith("INPUT.")]


def _needs_credential(missing: list[str]) -> list[str]:
    return [m.split(".", 1)[1] for m in missing if m.startswith("CREDENTIAL.")]


async def _ask_user(
    session_id: str,
    *,
    server_name: str,
    tool_name: str,
    fields: list[str],
    tool_description: str,
) -> dict[str, str]:
    """走 UserInputBlocker 阻塞，等前端表单提交。

    与外部系统的做法一致：payload 里带 fields 列表，前端渲染成表单。
    """
    from app.services.external_systems.coordinators import UserInputBlocker

    payload = {
        "type": "user_input_required",
        "api_name": tool_name,
        "api_display_name": tool_name,
        "system_name": server_name,
        "fields": [
            {
                "key": name,
                "label": name,
                "type": "text",
                "required": True,
                "description": tool_description or f"{server_name} 需要你提供 {name}",
            }
            for name in fields
        ],
        "message": f"调用 {server_name} → {tool_name} 需要你提供以下信息：",
    }
    logger.info("MCP 用户输入阻塞 server=%s tool=%s fields=%s", server_name, tool_name, fields)
    result = await UserInputBlocker.request_input(session_id, payload)
    return {k: str(v) for k, v in (result or {}).items()}


def wrap_mcp_tool(tool: Any) -> Any:
    """给 MCP 工具套上凭据注入 + 用户追问。

    返回**同名的新 Tool**（pydantic model，用 ``model_copy`` 换 handler）。
    原 Tool 保持不变，避免污染 adapter 的缓存对象。
    """
    tool_name = getattr(tool, "name", "") or ""
    server_name = _server_of(tool_name)
    if not server_name:
        # 不是 MCP 工具（理论上不会走到这），原样返回
        return tool

    original_handler: Callable[..., Any] = tool.handler
    description = getattr(tool, "description", "") or ""
    defaults = _schema_placeholder_defaults(tool)

    async def handler(**kwargs: Any) -> Any:
        from app.services.external_systems.context import get_ext_user_id

        user_id = get_ext_user_id()

        # ① 模型不会填「默认值为占位符」的参数（凭据就是这么声明的），
        #    所以先把 schema 里的占位符默认值补进来。
        merged: dict[str, Any] = dict(kwargs)
        for key, default in defaults.items():
            merged.setdefault(key, default)

        # ② 递归替换占位符（穿透 headers / fields 这类嵌套结构）
        resolved, missing = _resolve_placeholders(
            merged, server_name=server_name, user_id=user_id
        )

        if missing:
            # 凭据缺失：让调用方知道要去集成页配置
            cred_fields = _needs_credential(missing)
            if cred_fields:
                return json.dumps(
                    {
                        "error": (
                            f"缺少凭据：{', '.join(cred_fields)}。"
                            f"请先在「集成」页为 {server_name} 配置凭据后重试。"
                        ),
                        "missing_credentials": cred_fields,
                    },
                    ensure_ascii=False,
                )

            # 一次性输入：问用户
            input_fields = _needs_user_input(missing)
            if input_fields:
                from app.services.external_systems.context import _current_session_id

                session_id = _current_session_id.get()
                if not session_id:
                    return json.dumps(
                        {
                            "error": (
                                f"缺少参数：{', '.join(input_fields)}。"
                                "当前会话无法追问用户，请直接提供这些参数。"
                            ),
                            "missing_inputs": input_fields,
                        },
                        ensure_ascii=False,
                    )
                answers = await _ask_user(
                    session_id,
                    server_name=server_name,
                    tool_name=tool_name,
                    fields=input_fields,
                    tool_description=description,
                )
                # ③ 用户答完再替换一次（同样递归，兼容嵌在字符串中间的占位符）
                resolved, still = _resolve_placeholders(
                    resolved,
                    server_name=server_name,
                    user_id=user_id,
                    inputs=answers,
                )
                leftover = _needs_user_input(still)
                if leftover:
                    return json.dumps(
                        {
                            "error": (
                                f"缺少参数：{', '.join(leftover)}。"
                                "用户未提供完整信息，请重新发起调用。"
                            ),
                            "missing_inputs": leftover,
                        },
                        ensure_ascii=False,
                    )

        # ④ 调下游。异常统一转成结构化 JSON —— 让智能体看到的是
        #    「工具失败了，原因是什么」，而不是一条裸的 Python 异常。
        try:
            return await original_handler(**resolved)
        except Exception as exc:  # noqa: BLE001 —— 工具错误不应炸掉整轮对话
            logger.warning(
                "MCP 工具调用失败 server=%s tool=%s: %s",
                server_name,
                tool_name,
                exc,
            )
            return json.dumps(
                {
                    "error": f"MCP 工具 {tool_name} 调用失败：{exc}",
                    "server": server_name,
                    "tool": tool_name,
                },
                ensure_ascii=False,
            )

    return tool.model_copy(update={"handler": handler})
