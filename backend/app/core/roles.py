"""用户角色与能力（RBAC）。

## 为什么要有这一层

原先到处写 `user.role == "admin"`，散落在 20+ 个端点里。想加"只读管理员"
或"运营"时，只能把每处判断都改一遍 —— 而且很容易漏，漏一处就是权限漏洞。

这里把角色收敛成一张**能力表**：
- 角色是能力的集合，端点只问能力，不问角色名
- 加角色只改这张表，不动端点
- 前端拿 `/auth/me` 里的 `capabilities` 决定显示什么，不靠硬编码角色名

## 角色设计

| 角色 | 定位 | 关键能力 |
|------|------|----------|
| `user` | 普通员工 | 用智能体、自己的会话与产物 |
| `auditor` | 审计员 | 只读：看用量/审计日志/发布记录，**不能**改配置、不能读他人对话正文 |
| `operator` | 运营 | 管智能体/技能/知识库/公告/作品库，**不碰**用户、密钥、提供商 |
| `admin` | 管理员 | 全部平台配置；但仍**不能**读他人对话正文（见下） |
| `superadmin` | 超级管理员 | 上述全部 + 用户与密钥管理 + 高危操作（删库式清理、改提供商密钥） |

`auditor` / `operator` 是这次新增的：很多部署里"谁都能进后台看一切"才是
真正的问题，缺的往往是一个**只能看**和一个**能管内容但碰不到钱和钥匙**的角色。

## 对话正文为什么连 admin 都不给

对话里有员工写给 AI 的私事、粘贴的密钥、未公开的方案。这是**个人通信**，
不是平台配置。管理员需要知道的是平台健康（用量、错误率、发布状态），
这些都不需要正文。真要排障应当让当事人自己导出，或加一次性的临时授权
（可审计），而不是让每个管理员默认能翻全部聊天记录。

`can_read_any_conversation` 这个能力**只留给 superadmin**，且当前代码里没有
任何端点消费它 —— 留着是为了将来加"授权代查"时有地方挂，而不是现在就放开。
"""

from __future__ import annotations

# ── 能力常量 ──────────────────────────────────────────────────────────────
# 命名用「动作_对象」，方便前端按前缀分组。

CAP_AGENT_USE = "agent:use"                       # 使用智能体对话
CAP_CONVERSATION_OWN = "conversation:own"         # 自己的会话（始终有）
CAP_CONVERSATION_READ_ANY = "conversation:read_any"   # 读他人会话正文（仅 superadmin）

CAP_AGENT_MANAGE = "agent:manage"                 # 建/改/删智能体与技能
CAP_KNOWLEDGE_MANAGE = "knowledge:manage"         # 知识库管理
CAP_ANNOUNCEMENT_MANAGE = "announcement:manage"   # 公告管理
CAP_GALLERY_MANAGE = "gallery:manage"             # 作品库审核/下架
# workflow 引擎已整体下线（2026-11-20），CAP_WORKFLOW_MANAGE 已移除。
CAP_APPROVAL_REVIEW = "approval:review"           # 审批发布/外接系统调用

CAP_USER_MANAGE = "user:manage"                   # 用户增删改、改角色
CAP_APIKEY_MANAGE = "apikey:manage"               # 平台级 API Key
CAP_PROVIDER_MANAGE = "provider:manage"           # AI 提供商与密钥
CAP_SYSTEM_SETTINGS = "system:settings"           # LDAP/邮箱/全局设置
CAP_AUDIT_VIEW = "audit:view"                     # 审计日志、用量统计（只读）
CAP_DANGEROUS = "system:dangerous"                # 高危：清理数据、重置凭据

BASE_USER_CAPS: frozenset[str] = frozenset({
    CAP_AGENT_USE,
    CAP_CONVERSATION_OWN,
})

# 只读审计能看到的东西
_AUDITOR = BASE_USER_CAPS | frozenset({
    CAP_AUDIT_VIEW,
})

# 运营：管内容，不碰人、钱、钥匙
_OPERATOR = BASE_USER_CAPS | frozenset({
    CAP_AGENT_MANAGE,
    CAP_KNOWLEDGE_MANAGE,
    CAP_ANNOUNCEMENT_MANAGE,
    CAP_GALLERY_MANAGE,
    CAP_APPROVAL_REVIEW,
    CAP_AUDIT_VIEW,
})

# 管理员：平台配置全开，但**不含**读他人对话正文
_ADMIN = _OPERATOR | frozenset({
    CAP_USER_MANAGE,
    CAP_APIKEY_MANAGE,
    CAP_PROVIDER_MANAGE,
    CAP_SYSTEM_SETTINGS,
})

# 超级管理员：多一个「代查对话」与高危操作
_SUPERADMIN = _ADMIN | frozenset({
    CAP_CONVERSATION_READ_ANY,
    CAP_DANGEROUS,
})

ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "user": BASE_USER_CAPS,
    "auditor": _AUDITOR,
    "operator": _OPERATOR,
    "admin": _ADMIN,
    "superadmin": _SUPERADMIN,
}

#: 角色 → 中文名与一句话说明（后台下拉框直接用）
ROLE_META: tuple[dict[str, str], ...] = (
    {"value": "user", "label": "普通用户", "hint": "使用智能体，管理自己的会话与产物"},
    {"value": "auditor", "label": "审计员", "hint": "只读：看用量统计与审计日志，不能改配置"},
    {"value": "operator", "label": "运营", "hint": "管智能体/知识库/公告/作品库，不碰用户与密钥"},
    {"value": "admin", "label": "管理员", "hint": "平台配置全部可管（不含他人对话正文）"},
    {"value": "superadmin", "label": "超级管理员", "hint": "管理员 + 用户/密钥/高危操作与代查对话"},
)

#: 合法角色集合（写接口用它做白名单校验，别让任意字符串进库）
VALID_ROLES: frozenset[str] = frozenset(ROLE_CAPABILITIES)

#: 历史遗留：老数据里可能出现 "member" / 空串，统一按普通用户处理
_ALIASES = {"member": "user", "": "user", "none": "user"}


def normalize_role(role: str | None) -> str:
    """把库里的 role 归一成已知角色；未知值降级为 `user`（失败即收紧）。"""
    value = (role or "").strip().lower()
    value = _ALIASES.get(value, value)
    return value if value in ROLE_CAPABILITIES else "user"


def capabilities_for(role: str | None) -> frozenset[str]:
    """角色对应的能力集合。未知角色按普通用户处理（不会意外升权）。"""
    return ROLE_CAPABILITIES.get(normalize_role(role), BASE_USER_CAPS)


def has_capability(role: str | None, capability: str) -> bool:
    return capability in capabilities_for(role)


def is_admin_like(role: str | None) -> bool:
    """是否拥有**完整平台管理**能力（admin 或 superadmin）。

    注意这比"能进后台"更严格：operator（运营）能管内容但不算 admin_like。
    """
    return has_capability(role, CAP_USER_MANAGE)


def can_enter_admin(role: str | None) -> bool:
    """是否**能进后台页面**（有一项以上的管理类能力即可）。

    operator / auditor 都该能进后台 —— 他们进后台正是为了管内容/看审计。
    前端用 `/auth/me` 的 capabilities 判断显示哪些菜单，这里只做粗粒度放行。
    """
    caps = capabilities_for(role)
    return bool(caps & _MANAGEMENT_CAPS)


#: 「管理类」能力：拥有任意一项就能进后台。普通用户的 agent:use 不算。
_MANAGEMENT_CAPS: frozenset[str] = frozenset({
    CAP_AGENT_MANAGE,
    CAP_KNOWLEDGE_MANAGE,
    CAP_ANNOUNCEMENT_MANAGE,
    CAP_GALLERY_MANAGE,
    CAP_APPROVAL_REVIEW,
    CAP_AUDIT_VIEW,
    CAP_USER_MANAGE,
    CAP_APIKEY_MANAGE,
    CAP_PROVIDER_MANAGE,
    CAP_SYSTEM_SETTINGS,
    CAP_DANGEROUS,
})


def role_meta_payload() -> list[dict[str, object]]:
    """给前端的能力矩阵：角色选项 + 每个角色能做什么（不含具体能力位字符串）。"""
    return [
        {
            **meta,
            "capabilities": sorted(capabilities_for(meta["value"])),
        }
        for meta in ROLE_META
    ]
