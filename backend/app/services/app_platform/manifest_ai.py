"""AI 生成 manifest 草稿（网站应用化设计 2.0：业务描述 → 结构化声明）。

不让用户手写 JSON 是方案的关键修正 —— 用户在对话里说的是「业务语言」
（"收集客户反馈，作者能改自己的，管理员能删"），由 AI 翻译成 manifest 的
models/permissions 声明。生成的草稿**必须过 validate_manifest**（机器可判），
校验不过直接返回错误列表，不进入审批队列。

两步链路（需求文档 → manifest）合并为一次调用：输入业务描述，输出
{requirements_md, manifest}。管理员后续在 plan/apply 审批里收紧权限
（5.4「申请什么 ≠ 批什么」），这里只负责起草。
"""

from __future__ import annotations

import json
import logging

from app.services.agent.native.types import BaseMessage as Message
from app.services.app_platform.manifest import validate_manifest
from app.services.llm_factory import build_llm

logger = logging.getLogger("agenticos.app_platform.manifest_ai")

_PROMPT_TEMPLATE = """你要为 AgenticOS 应用平台把一段业务描述翻译成结构化声明。

## 输入（业务描述）
{brief}

## 输出格式（严格 JSON，不要 markdown 代码块）
{{
  "requirements_md": "产品需求文档（Markdown，≤500字）：谁产生数据、谁查看、是否需要登录、有哪些角色",
  "manifest": {{
    "version": 1,
    "name": "应用名（≤20字）",
    "description": "一句话描述",
    "icon": "单个 emoji",
    "auth": {{
      "mode": "builtin | none",
      "loginMethods": ["email"],
      "allowSignup": false,
      "roles": ["viewer", "editor", "admin"]
    }},
    "models": [
      {{
        "name": "模型名（snake_case）",
        "fields": [
          {{"name": "字段名", "type": "string|text|number|boolean|enum", "required": true,
            "options": ["枚举值…"], "default": "默认值", "ref": "user 或其它模型名"}}
        ],
        "permissions": {{
          "read":   ["owner", "role:viewer", "role:editor", "role:admin", "*"],
          "create": ["role:viewer", "role:editor", "role:admin"],
          "update": ["owner", "role:editor", "role:admin"],
          "delete": ["role:admin"]
        }}
      }}
    ],
    "capabilities": {{
      "storage": {{"mode": "platform"}},
      "outbound": {{"allow": [], "mode": "deny"}},
      "email": {{"templates": []}},
      "realtime": {{"enabled": false}}
    }},
    "routes": [{{"path": "/", "entry": "index.html"}}]
  }}
}}

## 翻译规则
1. 「只有作者能改自己的」→ update: ["owner", "role:editor", "role:admin"]；「所有人可看」→ read: ["*"]。
2. 权限**默认收窄**：没有明确说「所有人可写」就绝不给 create: ["*"]；outbound.allow 留空（默认拒绝出站）。
3. 涉及登录需求才用 mode=builtin；纯展示类用 none。
4. 字段类型只有 string/text/number/boolean/enum；引用用户身份用 "ref": "user"（如 ownerId）。
5. roles 只从 viewer/editor/admin 里选，够用即可。
"""


class ManifestAIService:
    """AI manifest 草稿生成（一次 LLM 调用产出需求文档 + 声明草稿）。"""

    async def generate_draft(self, brief: str) -> dict[str, object]:
        brief = (brief or "").strip()
        if not brief:
            raise ValueError("业务描述不能为空")
        if len(brief) > 4000:
            raise ValueError("业务描述过长（≤4000 字符）")

        gateway = build_llm(role="chat")
        messages = [
            Message(
                role="system",
                content=(
                    "你是 AgenticOS 应用平台的声明翻译助手：把业务描述翻译成 "
                    "manifest JSON 与产品需求文档。只输出合法 JSON，不要 markdown "
                    "代码块，不要额外解释。权限永远默认收窄。"
                ),
            ),
            Message(role="user", content=_PROMPT_TEMPLATE.format(brief=brief)),
        ]
        try:
            response = await gateway.generate(
                messages=messages,
                stream=False,
                temperature=0.4,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001 —— 网关层异常统一转可操作报错
            logger.warning("manifest AI 生成调用失败", exc_info=True)
            raise ValueError("AI 生成失败，请稍后重试") from exc

        content = (response.message.content or "").strip()
        if not content:
            raise ValueError("AI 返回内容为空，请重试")

        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("not a dict")
        except Exception as exc:
            raise ValueError("AI 返回格式异常（非 JSON 对象），请重试") from exc

        manifest = parsed.get("manifest")
        if not isinstance(manifest, dict):
            raise ValueError("AI 未返回 manifest 字段，请重试")
        # 描述与图标做轻量兜底（schema 校验前置的可用性补齐）
        manifest.setdefault("name", "未命名应用")
        manifest.setdefault("description", "")
        manifest.setdefault("icon", "📦")
        manifest.setdefault("version", 1)

        # 机器可判的硬校验（设计文档 2.0：校验不过不进入审批队列）
        errors = validate_manifest(manifest)
        if errors:
            raise ValueError(
                "AI 生成的 manifest 未通过 Schema 校验：" + "；".join(errors[:6])
            )

        requirements = str(parsed.get("requirements_md") or "").strip()
        return {
            "requirements_md": requirements,
            "manifest": manifest,
        }
