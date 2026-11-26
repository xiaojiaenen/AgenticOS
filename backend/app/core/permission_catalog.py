"""权限点目录（Permission Catalog）—— 前后端共用的单一事实来源。

## 设计

一个权限点 = ``资源:动作``（如 ``user:create`` / ``kb:delete`` / ``ppt:export``）。
它比旧的粗粒度 ``capability``（如 ``user:manage``）更细，用来做：
- 后端端点的细粒度门禁（``require_permission("user:create")``）
- 前端按钮/菜单的显示控制（``usePermission("user:create")``）

## 与 capability 的关系

``capability`` 是权限点的**分组**（粗粒度），权限点是它的**细化**：
- 一个 capability 下可挂多个权限点（``user:manage`` → user:create/update/delete/role）
- 保留 capability 是为了兼容现有 ``require_admin`` / ``require_capability`` 端点，
  新增代码一律用权限点。

## 内置角色的默认权限点

由 ``roles.py`` 的 capability 集合自动展开：某角色有 capability X，
就自动拥有 X 分组下的全部权限点。这样内置角色不需要单独维护一份映射，
且管理员在 UI 上改矩阵后，以矩阵为准（存 RoleModel.permissions_json）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.core.roles import (
    CAP_AGENT_MANAGE, CAP_AGENT_USE, CAP_ANNOUNCEMENT_MANAGE, CAP_APIKEY_MANAGE,
    CAP_APPROVAL_REVIEW, CAP_AUDIT_VIEW, CAP_CONVERSATION_OWN, CAP_CONVERSATION_READ_ANY,
    CAP_DANGEROUS, CAP_GALLERY_MANAGE, CAP_KNOWLEDGE_MANAGE, CAP_PROVIDER_MANAGE,
    CAP_SYSTEM_SETTINGS, CAP_USER_MANAGE, capabilities_for,
)


@dataclass(frozen=True)
class PermissionPoint:
    """一个权限点。"""

    key: str            # 唯一键：资源:动作
    group: str          # 所属 capability（分组）
    label: str          # 中文名（矩阵 UI 用）
    description: str = ""


def _p(key: str, group: str, label: str, description: str = "") -> PermissionPoint:
    return PermissionPoint(key=key, group=group, label=label, description=description)


# ── 权限点目录 ─────────────────────────────────────────────────────────────
# 规则：key 用「资源:动作」，group 用现有 capability 常量。
# 新增功能 = 在这里加一行 + 后端端点加 require_permission + 前端按钮包 <Permission>。

PERMISSION_POINTS: tuple[PermissionPoint, ...] = (
    # 基础使用（所有用户）
    _p("agent:chat", CAP_AGENT_USE, "使用智能体对话"),
    _p("conversation:view_own", CAP_CONVERSATION_OWN, "查看自己的会话"),
    _p("conversation:delete_own", CAP_CONVERSATION_OWN, "删除自己的会话"),
    _p("conversation:export", CAP_CONVERSATION_OWN, "导出会话"),
    _p("artifact:download", CAP_CONVERSATION_OWN, "下载产物"),

    # 创作画布（图片创作，所有用户可用）
    _p("image:create", CAP_AGENT_USE, "AI 图片创作", "文生图 / 图生图 / AI 改图"),
    _p("image:process", CAP_AGENT_USE, "图片处理", "裁剪 / 压缩 / 缩放 / 旋转 / 水印 / 格式转换"),

    # 审计只读
    _p("audit:stats", CAP_AUDIT_VIEW, "查看用量统计"),
    _p("audit:logs", CAP_AUDIT_VIEW, "查看审计日志"),
    _p("audit:metrics", CAP_AUDIT_VIEW, "查看检索质量指标"),
    _p("audit:usage_routes", CAP_AUDIT_VIEW, "查看用量路由"),

    # 智能体与技能
    # 创建自己的智能体是所有用户的权利（与「管理任意智能体」不同）
    _p("agent:create", CAP_AGENT_USE, "创建智能体"),
    _p("agent:edit", CAP_AGENT_MANAGE, "编辑智能体"),
    # 删除自己的智能体是用户权利（与编辑同理，服务层有资源归属校验）
    _p("agent:delete", CAP_AGENT_USE, "删除智能体"),
    # 平台级上架审核：仅管理员（走 user:manage 分组），支持多角色并集
    _p("agent:publish", CAP_USER_MANAGE, "上架智能体到商店"),
    _p("skill:create", CAP_AGENT_MANAGE, "创建 Skill"),
    _p("skill:edit", CAP_AGENT_MANAGE, "编辑 Skill"),
    _p("skill:delete", CAP_AGENT_MANAGE, "删除 Skill"),
    _p("tool:configure", CAP_AGENT_MANAGE, "配置工具与审批策略"),

    # 知识库
    _p("kb:create", CAP_KNOWLEDGE_MANAGE, "创建知识库"),
    _p("kb:edit", CAP_KNOWLEDGE_MANAGE, "编辑知识库"),
    _p("kb:delete", CAP_KNOWLEDGE_MANAGE, "删除知识库"),
    _p("kb:upload", CAP_KNOWLEDGE_MANAGE, "上传文档"),
    _p("kb:reindex", CAP_KNOWLEDGE_MANAGE, "重建索引"),
    _p("kb:acl", CAP_KNOWLEDGE_MANAGE, "管理知识库共享"),

    # 公告
    _p("announcement:create", CAP_ANNOUNCEMENT_MANAGE, "创建公告"),
    _p("announcement:edit", CAP_ANNOUNCEMENT_MANAGE, "编辑公告"),
    _p("announcement:delete", CAP_ANNOUNCEMENT_MANAGE, "删除公告"),

    # 作品库 / 审批
    _p("gallery:approve", CAP_GALLERY_MANAGE, "审核作品发布"),
    _p("gallery:remove", CAP_GALLERY_MANAGE, "下架作品"),
    _p("approval:review", CAP_APPROVAL_REVIEW, "处理审批事项"),

    # 用户与权限
    _p("user:create", CAP_USER_MANAGE, "创建用户"),
    _p("user:edit", CAP_USER_MANAGE, "编辑用户"),
    _p("user:delete", CAP_USER_MANAGE, "删除用户"),
    _p("user:role", CAP_USER_MANAGE, "分配用户角色"),
    _p("role:manage", CAP_USER_MANAGE, "管理角色与权限矩阵"),

    # API Key / 提供商 / 系统设置
    _p("apikey:create", CAP_APIKEY_MANAGE, "创建平台 API Key"),
    _p("apikey:delete", CAP_APIKEY_MANAGE, "删除平台 API Key"),
    _p("provider:manage", CAP_PROVIDER_MANAGE, "管理 AI 提供商"),
    _p("settings:edit", CAP_SYSTEM_SETTINGS, "修改系统设置"),

    # 对话代查与高危
    _p("conversation:read_any", CAP_CONVERSATION_READ_ANY, "代查他人对话正文"),
    _p("system:dangerous", CAP_DANGEROUS, "高危操作"),
)

PERMISSION_KEYS: frozenset[str] = frozenset(p.key for p in PERMISSION_POINTS)

# 分组元数据（矩阵 UI 左侧分组标题）
GROUPS: tuple[dict[str, str], ...] = (
    {"key": CAP_AGENT_USE, "label": "基础使用"},
    {"key": CAP_CONVERSATION_OWN, "label": "会话与产物"},
    {"key": CAP_AUDIT_VIEW, "label": "审计与统计"},
    {"key": CAP_AGENT_MANAGE, "label": "智能体与能力"},
    {"key": CAP_KNOWLEDGE_MANAGE, "label": "知识库"},
    {"key": CAP_ANNOUNCEMENT_MANAGE, "label": "公告"},
    {"key": CAP_GALLERY_MANAGE, "label": "作品库"},
    {"key": CAP_APPROVAL_REVIEW, "label": "审批"},
    {"key": CAP_USER_MANAGE, "label": "用户与权限"},
    {"key": CAP_APIKEY_MANAGE, "label": "API Key"},
    {"key": CAP_PROVIDER_MANAGE, "label": "AI 提供商"},
    {"key": CAP_SYSTEM_SETTINGS, "label": "系统设置"},
    {"key": CAP_CONVERSATION_READ_ANY, "label": "对话代查"},
    {"key": CAP_DANGEROUS, "label": "高危操作"},
)


def points_for_capability(capability: str) -> frozenset[str]:
    """某 capability 分组下的全部权限点 key。"""
    return frozenset(p.key for p in PERMISSION_POINTS if p.group == capability)


def default_permissions_for_role(role: str | None) -> frozenset[str]:
    """内置角色的默认权限点（由 capability 展开）。"""
    caps = capabilities_for(role)
    return frozenset().union(*(points_for_capability(c) for c in caps)) if caps else frozenset()


def normalize_permissions(keys: Iterable[str]) -> frozenset[str]:
    """过滤掉未知权限点（防注入），返回合法集合。"""
    return frozenset(k for k in keys if k in PERMISSION_KEYS)


def catalog_payload() -> dict:
    """给前端的目录：分组 + 权限点（矩阵 UI 直接渲染）。"""
    return {
        "groups": [
            {**g, "points": [
                {"key": p.key, "label": p.label, "description": p.description}
                for p in PERMISSION_POINTS if p.group == g["key"]
            ]}
            for g in GROUPS
        ],
        "total": len(PERMISSION_POINTS),
    }


def all_points_payload() -> list[dict[str, str]]:
    return [
        {"key": p.key, "group": p.group, "label": p.label, "description": p.description}
        for p in PERMISSION_POINTS
    ]
