"""应用 manifest：JSON Schema、校验、plan 变更计划与 apply（设计文档 2 / 5 节）。

manifest 是应用的**声明文件**（agenticos.app.json），不是代码：数据模型、权限、
页面路由、平台能力申请全部声明式描述，平台按声明生成 API 与权限校验。

审批模型（5.2，借鉴 SimpleBase dev plan/apply）：

- ``generate_plan(old, new)`` 生成只读变更计划 —— ``~`` 字段修改 / ``+`` 新建 /
  ``-`` 删除 / ``!`` 权限或白名单风险升级（扩权必须人工细看）；
- ``apply_plan`` 把（管理员可逐项收紧后的）目标态落为生效态：对未批准的
  ``!`` 风险项回退到旧值，收紧后的版本才是实际生效版本（5.4「申请什么」
  与「批什么」分离）；
- apply 幂等：重复 apply 同一份目标态，diff 为空，重复执行无副作用。

schema 校验用自带的迷你校验器（type/properties/required/items/enum/pattern
子集）而不是引入 jsonschema 依赖 —— manifest schema 是我们自己定义的封闭
子集，mini-validator 约 40 行即可覆盖，且错误信息带路径更可读。
"""

from __future__ import annotations

import copy
import re
from typing import Any

# ── JSON Schema 定义（对齐设计文档 2 节字段结构）────────────────────────

#: 字段类型白名单（validate_record_data 按同表做值校验）
FIELD_TYPES: frozenset[str] = frozenset({"string", "text", "number", "boolean", "enum", "date", "datetime"})

#: 权限规则：通配 / 行级归属 owner / 角色（role: 前缀）
PERMISSION_RULE_PATTERN = r"^(\*|owner|role:[A-Za-z0-9_-]+)$"
#: 模型名：小写 slug（无点号 —— plan 的机器路径按 "." 分段依赖这一点）
MODEL_NAME_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
#: 角色名
ROLE_NAME_PATTERN = r"^[a-z][a-z0-9_-]{0,31}$"

_FIELD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string", "enum": sorted(FIELD_TYPES)},
        "required": {"type": "boolean"},
        "label": {"type": "string"},
        "description": {"type": "string"},
        # enum 类型必填的取值集合
        "options": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "default": {},
        # 引用完整性：ref="user" 指向应用终端用户（写入时平台校验存在性）
        "ref": {"type": "string", "enum": ["user"]},
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

_PERMISSIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # 缺省的动作 = 不授权（"只读数据"就是只写 read，见设计文档 7 节）
        "read": {"type": "array", "items": {"type": "string", "pattern": PERMISSION_RULE_PATTERN}},
        "create": {"type": "array", "items": {"type": "string", "pattern": PERMISSION_RULE_PATTERN}},
        "update": {"type": "array", "items": {"type": "string", "pattern": PERMISSION_RULE_PATTERN}},
        "delete": {"type": "array", "items": {"type": "string", "pattern": PERMISSION_RULE_PATTERN}},
    },
    "additionalProperties": False,
}

_MODEL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "pattern": MODEL_NAME_PATTERN},
        "fields": {"type": "array", "items": _FIELD_SCHEMA, "minItems": 1},
        "permissions": _PERMISSIONS_SCHEMA,
    },
    "required": ["name", "fields", "permissions"],
    "additionalProperties": False,
}

_AUTH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # none = 公开只读；builtin = 平台托管账号；oauth = 外部 IdP（第二步）
        "mode": {"type": "string", "enum": ["none", "builtin", "oauth"]},
        "loginMethods": {
            "type": "array",
            "items": {"type": "string", "enum": ["email", "sms", "sso"]},
        },
        "loginPath": {"type": "string"},
        "allowSignup": {"type": "boolean"},
        "roles": {"type": "array", "items": {"type": "string", "pattern": ROLE_NAME_PATTERN}},
    },
    "required": ["mode"],
    "additionalProperties": False,
}

_CAPABILITIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "storage": {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["platform", "external"]}},
            "additionalProperties": False,
        },
        "files": {
            "type": "object",
            "properties": {"maxSizeMb": {"type": "number", "minimum": 0}},
            "additionalProperties": False,
        },
        # 出站白名单：默认拒绝（能力申请默认拒绝，主要滥用面）
        "outbound": {
            "type": "object",
            "properties": {
                "allow": {"type": "array", "items": {"type": "string", "minLength": 1}},
                "mode": {"type": "string", "enum": ["deny", "allow"]},
            },
            "additionalProperties": False,
        },
        "email": {
            "type": "object",
            "properties": {"templates": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
        "realtime": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

_ROUTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "entry": {"type": "string", "minLength": 1},
        "requiresRole": {"type": "string", "pattern": ROLE_NAME_PATTERN},
    },
    "required": ["path", "entry"],
    "additionalProperties": False,
}

MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://agenticos.local/schemas/app-manifest.v1.json",
    "type": "object",
    "properties": {
        "$schema": {"type": "string"},
        "version": {"type": "integer", "enum": [1]},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "icon": {"type": "string"},
        "auth": _AUTH_SCHEMA,
        "models": {"type": "array", "items": _MODEL_SCHEMA},
        "capabilities": _CAPABILITIES_SCHEMA,
        "routes": {"type": "array", "items": _ROUTE_SCHEMA},
    },
    "required": ["version", "name", "auth", "models"],
    "additionalProperties": False,
}

# ── 迷你 schema 校验器（支持本 schema 用到的关键字子集）──────────────────

_TYPE_CHECKS: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "null": (type(None),),
}


def _check_type(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPE_CHECKS[expected])


def _walk_schema(value: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    """递归校验 value 是否满足 schema 子集；错误以「路径: 问题」追加进 errors。"""
    expected_type = schema.get("type")
    if expected_type and not _check_type(value, expected_type):
        errors.append(f"{path}: 应为 {expected_type}，实际为 {type(value).__name__}")
        return

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 取值 {value!r} 不在允许范围 {schema['enum']} 内")
        return

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if pattern and re.search(pattern, value) is None:
            errors.append(f"{path}: {value!r} 不匹配格式 {pattern}")
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            errors.append(f"{path}: 长度不能少于 {min_length}")
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            errors.append(f"{path}: 不能小于 {minimum}")
        return

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: 缺少必填字段 {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}: 未知字段 {key!r}")
        for key, sub_value in value.items():
            if key in properties:
                _walk_schema(sub_value, properties[key], f"{path}.{key}" if path != "(" else f"{key}", errors)
        return

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: 至少需要 {min_items} 项")
        item_schema = schema.get("items")
        if item_schema:
            for idx, item in enumerate(value):
                _walk_schema(item, item_schema, f"{path}[{idx}]" if path != "(" else f"[{idx}]", errors)


# ── 校验入口 ──────────────────────────────────────────────────────────


def validate_manifest(manifest: Any) -> list[str]:
    """校验 manifest，返回错误列表（空列表 = 通过）。不过校验不进审批队列。

    结构错误走 JSON Schema 迷你校验器；语义错误（重名、enum 缺 options、
    default 类型不符等）在这里补查。
    """
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest: 必须是 JSON 对象"]
    _walk_schema(manifest, MANIFEST_SCHEMA, "(", errors)

    models = manifest.get("models") or []
    seen_models: set[str] = set()
    for model in models:
        name = model.get("name", "?")
        if name in seen_models:
            errors.append(f"models.{name}: 模型名重复")
        seen_models.add(name)

        seen_fields: set[str] = set()
        for field in model.get("fields", []):
            fname = field.get("name", "?")
            if fname in seen_fields:
                errors.append(f"models.{name}.fields.{fname}: 字段名重复")
            seen_fields.add(fname)
            if field.get("type") == "enum" and not field.get("options"):
                errors.append(f"models.{name}.fields.{fname}: enum 类型必须提供 options")
            if field.get("type") in {"boolean", "number"} and field.get("ref"):
                errors.append(f"models.{name}.fields.{fname}: ref 引用只能用于字符串类字段")
            default = field.get("default")
            if default is not None and not _default_matches_type(default, field.get("type")):
                errors.append(
                    f"models.{name}.fields.{fname}: default 类型与字段类型 {field.get('type')} 不符"
                )
    return errors


def _default_matches_type(default: Any, field_type: str | None) -> bool:
    if field_type in {"string", "text", "date", "datetime"}:
        return isinstance(default, str)
    if field_type == "number":
        return isinstance(default, (int, float)) and not isinstance(default, bool)
    if field_type == "boolean":
        return isinstance(default, bool)
    if field_type == "enum":
        return isinstance(default, str)
    return True


# ── plan / apply（设计文档 5.2 / 5.4）──────────────────────────────────


def _rules_of(perms: dict[str, Any] | None, action: str) -> list[str] | None:
    if not isinstance(perms, dict):
        return None
    rules = perms.get(action)
    return rules if isinstance(rules, list) else None


def _plan_item(op: str, path: str, detail: str, *, risk: bool = False, old: Any = None, new: Any = None) -> dict[str, Any]:
    return {"op": op, "path": path, "detail": detail, "risk": risk, "old": old, "new": new}


def _diff_rules(path: str, old_rules: list[str] | None, new_rules: list[str] | None) -> dict[str, Any] | None:
    """单个权限动作的 diff：扩权 → ``!`` 风险项；收紧/调整 → ``~``；不变 → ``=``。

    扩权判定：新规则集合里有旧集合没有的成员（旧为缺省视为空集 ——
    「原来不许做，现在允许某些人做」同样是扩权）。
    """
    old_set = set(old_rules or [])
    new_set = set(new_rules or [])
    if old_set == new_set:
        if not old_set:
            return None  # 双方都缺省，不产生条目
        return _plan_item("=", path, "无变化", old=old_rules, new=new_rules)
    added = new_set - old_set
    detail = f"{_fmt_rules(old_rules)} → {_fmt_rules(new_rules)}"
    if added:
        return _plan_item("!", path, f"权限扩大 {detail}", risk=True, old=old_rules, new=new_rules)
    return _plan_item("~", path, f"权限收紧 {detail}", old=old_rules, new=new_rules)


def _fmt_rules(rules: list[str] | None) -> str:
    return "[" + ", ".join(rules or []) + "]" if rules else "[]"


def _diff_fields(model_name: str, old_model: dict[str, Any], new_model: dict[str, Any]) -> list[dict[str, Any]]:
    """字段级 diff（~ 新增/删除/修改），按字段名对齐。"""
    items: list[dict[str, Any]] = []
    old_fields = {f.get("name"): f for f in old_model.get("fields", []) if isinstance(f, dict)}
    new_fields = {f.get("name"): f for f in new_model.get("fields", []) if isinstance(f, dict)}
    comparable = ("type", "required", "options", "default", "ref")
    for fname, field in new_fields.items():
        path = f"models.{model_name}.fields.{fname}"
        if fname not in old_fields:
            items.append(_plan_item("~", path, f"新增字段 {field.get('type')}", old=None, new=field))
            continue
        old_field = old_fields[fname]
        changed = [key for key in comparable if old_field.get(key) != field.get(key)]
        if changed:
            summary = ", ".join(
                f"{key}: {_short(old_field.get(key))} → {_short(field.get(key))}" for key in changed
            )
            items.append(_plan_item("~", path, f"字段修改 {summary}", old=old_field, new=field))
    for fname, field in old_fields.items():
        if fname not in new_fields:
            items.append(_plan_item("~", f"models.{model_name}.fields.{fname}", "删除字段", old=field, new=None))
    return items


def _short(value: Any) -> str:
    text = repr(value) if isinstance(value, (list, dict)) else str(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _diff_capabilities(old_caps: dict[str, Any] | None, new_caps: dict[str, Any] | None) -> list[dict[str, Any]]:
    """能力申请 diff。高风险项：出站白名单扩容 / deny→allow、realtime 开启。"""
    items: list[dict[str, Any]] = []
    old_caps = old_caps or {}
    new_caps = new_caps or {}

    old_allow = list((old_caps.get("outbound") or {}).get("allow") or [])
    new_allow = list((new_caps.get("outbound") or {}).get("allow") or [])
    if set(new_allow) - set(old_allow):
        items.append(
            _plan_item(
                "!",
                "capabilities.outbound.allow",
                f"出站白名单扩大 {_fmt_rules(old_allow)} → {_fmt_rules(new_allow)}",
                risk=True,
                old=old_allow,
                new=new_allow,
            )
        )
    old_mode = (old_caps.get("outbound") or {}).get("mode", "deny")
    new_mode = (new_caps.get("outbound") or {}).get("mode", "deny")
    if old_mode == "deny" and new_mode == "allow":
        items.append(
            _plan_item("!", "capabilities.outbound.mode", "出站模式 deny → allow（放开默认拒绝）", risk=True, old=old_mode, new=new_mode)
        )

    old_rt = bool((old_caps.get("realtime") or {}).get("enabled"))
    new_rt = bool((new_caps.get("realtime") or {}).get("enabled"))
    if not old_rt and new_rt:
        items.append(_plan_item("!", "capabilities.realtime.enabled", "realtime 关闭 → 开启（新能力）", risk=True, old=old_rt, new=new_rt))

    old_max = (old_caps.get("files") or {}).get("maxSizeMb")
    new_max = (new_caps.get("files") or {}).get("maxSizeMb")
    if isinstance(old_max, (int, float)) and isinstance(new_max, (int, float)) and new_max > old_max:
        items.append(_plan_item("~", "capabilities.files.maxSizeMb", f"上传上限 {old_max} → {new_max} MB", old=old_max, new=new_max))
    return items


def generate_plan(old: dict[str, Any] | None, new: dict[str, Any]) -> list[dict[str, Any]]:
    """对比当前生效 manifest 与申请版本，生成只读变更计划（5.2）。

    条目操作符：``~`` 字段修改 / ``+`` 新建 / ``-`` 删除 / ``=`` 无变化 /
    ``!`` 权限或白名单风险升级（risk=True，apply 时未批准的会回退）。
    新建模型自带的通配权限（``*``）单独标 ``!`` —— 设计文档 5.1 要求
    「过宽的权限要能一眼看出来」。
    """
    plan: list[dict[str, Any]] = []
    old_models = {m.get("name"): m for m in ((old or {}).get("models") or []) if isinstance(m, dict)}
    new_models = {m.get("name"): m for m in (new.get("models") or []) if isinstance(m, dict)}

    for name in new_models:
        if name not in old_models:
            plan.append(_plan_item("+", f"models.{name}", "新建模型", old=None, new=new_models[name]))
            perms = new_models[name].get("permissions") or {}
            for action in ("read", "create", "update", "delete"):
                rules = _rules_of(perms, action)
                if rules and "*" in rules:
                    plan.append(
                        _plan_item(
                            "!",
                            f"models.{name}.permissions.{action}",
                            f"新建模型即含通配权限 {_fmt_rules(rules)}",
                            risk=True,
                            old=None,
                            new=rules,
                        )
                    )

    for name in old_models:
        if name not in new_models:
            plan.append(_plan_item("-", f"models.{name}", "删除模型", old=old_models[name], new=None))

    for name in sorted(set(old_models) & set(new_models)):
        old_model, new_model = old_models[name], new_models[name]
        plan.extend(_diff_fields(name, old_model, new_model))
        old_perms, new_perms = old_model.get("permissions"), new_model.get("permissions")
        for action in ("read", "create", "update", "delete"):
            item = _diff_rules(
                f"models.{name}.permissions.{action}",
                _rules_of(old_perms, action),
                _rules_of(new_perms, action),
            )
            if item is not None:
                plan.append(item)

    # auth：allowSignup 打开是扩权（任何人可注册）；其余属普通调整
    old_auth, new_auth = (old or {}).get("auth") or {}, new.get("auth") or {}
    if not old_auth.get("allowSignup") and new_auth.get("allowSignup"):
        plan.append(_plan_item("!", "auth.allowSignup", "allowSignup false → true（开放注册）", risk=True, old=False, new=True))
    for key in ("mode", "loginMethods", "loginPath", "roles"):
        if old_auth.get(key) != new_auth.get(key):
            plan.append(_plan_item("~", f"auth.{key}", f"{_short(old_auth.get(key))} → {_short(new_auth.get(key))}", old=old_auth.get(key), new=new_auth.get(key)))

    plan.extend(_diff_capabilities((old or {}).get("capabilities"), new.get("capabilities")))

    # routes：按显示路径文本对齐（route path 含符号，不参与机器回退路径）
    old_routes = {r.get("path"): r for r in ((old or {}).get("routes") or []) if isinstance(r, dict)}
    new_routes = {r.get("path"): r for r in (new.get("routes") or []) if isinstance(r, dict)}
    for path_, route in new_routes.items():
        if path_ not in old_routes:
            plan.append(_plan_item("+", f"route {path_}", "新增路由", old=None, new=route))
        elif old_routes[path_] != route:
            plan.append(_plan_item("~", f"route {path_}", "路由修改", old=old_routes[path_], new=route))
    for path_ in old_routes:
        if path_ not in new_routes:
            plan.append(_plan_item("-", f"route {path_}", "删除路由", old=old_routes[path_], new=None))

    return plan


def _set_path(manifest: dict[str, Any], path: str, value: Any) -> None:
    """把回退值写回 manifest 的机器路径（models.<name>.permissions.<action> 等）。

    ``models`` 段是数组，按模型名定位（一次消费 "models" + 模型名两段）；
    其余段都是 dict 键。模型名 schema 保证不含点号，路径按 "." 分段是安全的。
    回退目标是旧值/删除键，找不到目标时静默跳过（plan 与 manifest 不同步
    只发生在并发改写这种病态场景）。
    """
    segments = path.split(".")
    node: Any = manifest
    idx = 0
    while idx < len(segments) - 1:
        segment = segments[idx]
        if segment == "models" and isinstance(node, dict):
            models = node.get("models") or []
            name = segments[idx + 1] if idx + 1 < len(segments) else None
            node = next((m for m in models if isinstance(m, dict) and m.get("name") == name), None)
            if node is None:
                return
            idx += 2  # "models" 与模型名两段一起消费
            continue
        if not isinstance(node, dict) or segment not in node:
            return
        node = node[segment]
        idx += 1
    if isinstance(node, dict):
        last = segments[-1]
        if value is None:
            node.pop(last, None)
        else:
            node[last] = value


def apply_plan(
    old: dict[str, Any] | None,
    new: dict[str, Any],
    *,
    plan: list[dict[str, Any]] | None = None,
    approved_paths: set[str] | None = None,
) -> dict[str, Any]:
    """apply 变更计划，返回收紧后的生效 manifest（5.4）。

    - 以目标态 ``new`` 为底稿；``!`` 风险项若不在 ``approved_paths``（None =
      全部批准）则回退到旧值 —— 管理员「逐项收紧」后实际生效的是收紧版本；
    - 幂等：对已生效的目标态重复 apply，plan 为空，返回值不变；
    - 返回前重新过 schema 校验，防御 plan 与 manifest 不同步的病态输入。
    """
    effective = copy.deepcopy(new)
    plan = plan if plan is not None else generate_plan(old, new)
    for item in plan:
        # approved_paths 为 None = 全量批准（不收紧）；给了集合时，未批准的风险项回退旧值
        if item.get("op") == "!" and item.get("risk") and approved_paths is not None and item["path"] not in approved_paths:
            _set_path(effective, item["path"], copy.deepcopy(item.get("old")))
    errors = validate_manifest(effective)
    if errors:
        raise ValueError("apply 后的 manifest 校验失败: " + "; ".join(errors))
    return effective
