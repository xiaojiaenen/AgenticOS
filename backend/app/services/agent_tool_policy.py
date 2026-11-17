"""管理员对「用户自建智能体」的可用工具 / Skill 限制。

## 解决什么问题

用户可以自建智能体、自选工具与 Skill。平台里有几类能力不该由普通用户自由
启用 —— 典型的是能写文件、能访问内网、能发起外连的工具。管理员需要在
**平台层**统一收口，而不是指望每个用户自觉。

## 设计

- 管理员在「工具配置」里把某个工具标记为 **restricted**（受管）：它只对
  **管理员拥有的智能体**可用；普通用户自建的智能体即使勾上也拿不到。
- 限制是**黑名单**（默认什么都不限），因为平台绝大多工具是安全的，
  逐个放行会让新工具默认不可用、上线就"坏了"。
- 同样支持 Skill：标记 restricted 的 skill 不给普通用户的智能体用。
- 管理员自己的智能体（`owner_id` 指向管理员，或平台内置）**不受限**。

存储用现有 `system_settings` 表（键 `agent_tool_policy.restricted_tools` /
`agent_tool_policy.restricted_skills`），避免为一个小配置加表 + 迁移。

## 为什么限制落在 allowed_tools 上

`_compute_allowed_tools` 算出的白名单是注册表的**权威裁剪依据**
（`factory.py` 会按它裁掉多余工具）。限制在这里叠加一次，就能覆盖所有
来源（内置工具、MCP、动态注册的工作流工具），不用在每个注册点重复判断。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SystemSettingModel

logger = logging.getLogger("agenticos.tool_policy")

KEY_RESTRICTED_TOOLS = "agent_tool_policy.restricted_tools"
KEY_RESTRICTED_SKILLS = "agent_tool_policy.restricted_skills"

#: 默认受管（restricted）的工具。只放**危险写操作 / 越权面**的，其余默认放开。
#: 管理员可以在后台改这个名单（存 DB，覆盖默认值）。
DEFAULT_RESTRICTED_TOOLS: tuple[str, ...] = (
    # 写文件到工作区：能覆盖产物、也能当"落盘再执行"的一环
    "write_text_file",
    "write_file",
    # 任意命令 / 包管理：能力等价于代码执行
    "run_shell",
    "npm",
    "npm_install",
)


@dataclass(frozen=True)
class ToolPolicy:
    """当前生效的工具/Skill 限制。"""

    restricted_tools: frozenset[str] = field(default_factory=frozenset)
    restricted_skills: frozenset[str] = field(default_factory=frozenset)

    def allows_tool(self, tool_name: str) -> bool:
        return tool_name not in self.restricted_tools

    def allows_skill(self, skill_slug: str) -> bool:
        return skill_slug not in self.restricted_skills


def _load_list(db: Session, key: str, default: tuple[str, ...]) -> frozenset[str]:
    row = db.scalar(select(SystemSettingModel).where(SystemSettingModel.key == key))
    if row is None or not (row.value or "").strip():
        return frozenset(default)
    try:
        parsed = json.loads(row.value)
        if isinstance(parsed, list):
            return frozenset(str(item) for item in parsed if str(item).strip())
    except (ValueError, TypeError):
        logger.warning("工具策略 %s 不是合法 JSON 列表，回退默认值", key)
    return frozenset(default)


def load_policy(db: Session) -> ToolPolicy:
    """读当前生效的策略（DB 覆盖默认值）。"""
    try:
        return ToolPolicy(
            restricted_tools=_load_list(db, KEY_RESTRICTED_TOOLS, DEFAULT_RESTRICTED_TOOLS),
            restricted_skills=_load_list(db, KEY_RESTRICTED_SKILLS, ()),
        )
    except Exception:  # noqa: BLE001 —— 读策略失败不能让整轮对话挂掉
        logger.warning("读取工具策略失败，按默认值处理", exc_info=True)
        return ToolPolicy(restricted_tools=frozenset(DEFAULT_RESTRICTED_TOOLS))


def save_policy(
    db: Session,
    *,
    restricted_tools: list[str] | None = None,
    restricted_skills: list[str] | None = None,
) -> ToolPolicy:
    """保存策略（管理员操作）。只更新传入的字段。"""
    for key, values in (
        (KEY_RESTRICTED_TOOLS, restricted_tools),
        (KEY_RESTRICTED_SKILLS, restricted_skills),
    ):
        if values is None:
            continue
        payload = json.dumps(sorted({str(v).strip() for v in values if str(v).strip()}))
        # system_settings.value 是 String(1024)：名单超长时截断会写出坏 JSON，
        # 下次读就静默回退默认值 —— 宁可报错让管理员分批配置。
        if len(payload) > 1024:
            raise ValueError(
                f"限制名单过长（{len(payload)} 字符 > 1024）。请分批配置，"
                "或改用更少的工具名。"
            )
        row = db.scalar(select(SystemSettingModel).where(SystemSettingModel.key == key))
        if row is None:
            db.add(SystemSettingModel(key=key, value=payload))
        else:
            row.value = payload
    db.commit()
    return load_policy(db)


def apply_policy_to_tools(
    allowed_tools: frozenset[str],
    *,
    policy: ToolPolicy,
    is_privileged_owner: bool,
) -> frozenset[str]:
    """把策略叠加到白名单上。

    `is_privileged_owner=True`（管理员拥有的智能体 / 平台内置）时原样返回 ——
    限制只针对普通用户自建的智能体。
    """
    if is_privileged_owner:
        return allowed_tools
    return frozenset(name for name in allowed_tools if policy.allows_tool(name))


def filter_skills(
    skills: tuple,
    *,
    policy: ToolPolicy,
    is_privileged_owner: bool,
) -> tuple:
    """过滤掉受管 Skill（元素需有 `slug` 属性）。"""
    if is_privileged_owner:
        return skills
    return tuple(s for s in skills if policy.allows_skill(getattr(s, "slug", "")))
