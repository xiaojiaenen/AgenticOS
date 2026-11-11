from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.timezone import app_now, isoformat_app_timezone
from app.db.models import (
    AgentProfileExternalSystemModel,
    AgentProfileModel,
    AgentProfileAudienceModel,
    AgentProfileSkillModel,
    AgentProfileToolModel,
    AgentProfileVersionModel,
    ExternalSystemModel,
    SkillModel,
    UserInstalledAgentModel,
    UserModel,
)
from app.db.session import create_db_session
import json as _json
from app.prompts import (BIGDATA_SYSTEM_PROMPT, EMAIL_SYSTEM_PROMPT, GENERAL_SYSTEM_PROMPT,
                          OFFICE_SYSTEM_PROMPT, PPT_SYSTEM_PROMPT, WEBSITE_ROUTER_PROMPT)
from app.schemas.agent_profiles import AgentProfileCreateRequest, AgentProfileTool, AgentProfileUpdateRequest
from app.services.session_storage import parse_approval_sub_tools, slugify
from app.services.skill_service import RuntimeSkill, SkillService
from app.services.tool_config_service import AGENT_MODES, DEFAULT_MODE_TOOLS, TOOL_CATALOG

import time as _time

_ensure_defaults_last_run: float = 0.0


AUDIENCE_MODE_ALL = "all"
AUDIENCE_MODE_SELECTED = "selected"

MODE_DEFAULT_PROMPTS: dict[str, str] = {
    "general": GENERAL_SYSTEM_PROMPT,
    "ppt": PPT_SYSTEM_PROMPT,
    "website": WEBSITE_ROUTER_PROMPT,
    "email": EMAIL_SYSTEM_PROMPT,
    "bigdata": BIGDATA_SYSTEM_PROMPT,
    "office": OFFICE_SYSTEM_PROMPT,
}

GENERIC_PROMPTS = {
    "你是 AgenticOS 的通用智能助手，请优先给出准确、清晰、可执行的回答。",
    "你是一个专注于特定任务的 AgenticOS 智能体。请根据用户目标主动拆解任务，必要时调用可用工具，并给出清晰可执行的结果。",
}


BUILTIN_AGENT_PROFILES = {
    "general": {
        "name": "通用助手",
        "description": "适合日常问答、资料整理、轻量工具调用和多轮协作。",
        "system_prompt": GENERAL_SYSTEM_PROMPT,
        "response_mode": "general",
        "avatar": "sparkles",
        "listed": True,
    },
    "ppt": {
        "name": "PPT 设计师",
        "description": "使用 SVG 原生图形生成演示文稿，支持导出原生 .pptx 文件，形状可编辑。",
        "system_prompt": PPT_SYSTEM_PROMPT,
        "response_mode": "ppt",
        "avatar": "presentation",
        "listed": True,
        "max_steps": 50,
    },
    "website": {
        "name": "网站工程师",
        "description": "用于页面方案、前端代码、交互原型和网站结构设计。",
        "system_prompt": WEBSITE_ROUTER_PROMPT,
        "response_mode": "website",
        "avatar": "globe",
        "listed": True,
    },
    "office": {
        "name": "办公助手",
        "description": "统一处理表格与文档：生成可编辑的电子表格（公式/多工作表）和文档（标题层级/正文）。",
        "system_prompt": OFFICE_SYSTEM_PROMPT,
        "response_mode": "office",
        "avatar": "table",
        "listed": True,
    },
    "email": {
        "name": "邮箱助手",
        "description": "帮助用户高效管理公司邮件，支持读取、搜索、发送和统计。",
        "system_prompt": EMAIL_SYSTEM_PROMPT,
        "response_mode": "email",
        "avatar": "mail",
        "listed": True,
    },
}


# 内置智能体默认绑定的 Skill（按 slug 匹配，装载时找不到就跳过）。
# 此前内置智能体一个 Skill 都没绑：PPT 设计师手里有生成工具，却拿不到
# ppt-design-guide / ppt-quality-budgets 这些方法论，等于把专家拆成半成品。
BUILTIN_AGENT_SKILLS: dict[str, tuple[str, ...]] = {
    "ppt": (
        "ppt-workflow",
        "ppt-design-guide",
        "ppt-design-philosophies",
        "ppt-template-library",
        "ppt-quality-budgets",
        "ppt-visual-review",
        "ppt-expert-review",
        "ppt-chart-validator",
    ),
    "website": ("website-design-taste",),
    "email": ("email-skill", "email-design"),
    "bigdata": (
        "bigdata-operations",
        "bigdata-troubleshooting",
        "dinky-sql-skill",
        "doris-ads-skill",
        "ds-workflow-skill",
        "paimon-model-skill",
        "intranet-automation",
    ),
}


@dataclass(frozen=True)
class RuntimeAgentProfile:
    profile_id: int | None
    name: str
    slug: str
    response_mode: str
    system_prompt: str
    builtin_tools: tuple[str, ...]
    approval_tools: frozenset[str]
    signature: tuple[tuple[str, bool, bool], ...]
    skills: tuple[RuntimeSkill, ...]
    external_system_ids: tuple[int, ...] = ()
    max_steps: int | None = None
    # 会话级审批模式：ask（逐次确认）/ auto（只读自动放行）/ full（全放行，仅管理员）
    approval_mode: str = "auto"
    # 计划模式：只下发只读工具，产出计划待用户批准后再执行
    plan_mode: bool = False
    # 触发本轮的用户是否为管理员（决定 full 档是否生效）
    is_admin_actor: bool = False
    # 该 profile 允许的**具体工具名**白名单（含子工具，如 write_text_file）。
    #
    # 为什么需要它：注册表里有两类工具来源，来源不同、管控也不同 ——
    #   1. builtin 插件类（calc/time/file/python/...）：受 profile 的 enabled
    #      开关控制，已经通过 builtin_tools 下发；
    #   2. 模式注册类（website_tools / sheet_tools / doc_tools / email_tools
    #      / website_file_tools）：**按 response_mode 整体注册**，此前完全
    #      绕过了 profile 配置 —— 管理员在界面里关掉「文件工具」或
    #      「部署网站」，工具照样可用。
    #
    # 这个集合把两类统一到同一个白名单：注册表构建后按它裁剪，
    # 管理员的开关才真正说了算。
    allowed_tools: frozenset[str] = frozenset()


class AgentProfileService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    def ensure_defaults(self, db: Session) -> None:
        global _ensure_defaults_last_run
        if _time.time() - _ensure_defaults_last_run < 300:  # 5 min cache
            return
        changed = False
        existing = {row.slug: row for row in db.scalars(select(AgentProfileModel)).all()}
        # 一次性迁移：sheet 模式已并入 office（办公助手）。
        # - 库里只有 sheet：原地改名，保留它的历史
        # - 两者并存：sheet 是指向已删除模式的孤儿，直接删掉。office 已由
        #   内置补装逻辑覆盖所有用户，删掉它不会让任何人丢失这个智能体。
        legacy_sheet = existing.pop("sheet", None)
        if legacy_sheet is not None and legacy_sheet.is_builtin:
            if "office" in existing:
                db.execute(
                    delete(UserInstalledAgentModel).where(
                        UserInstalledAgentModel.profile_id == legacy_sheet.id
                    )
                )
                db.delete(legacy_sheet)
            else:
                legacy_sheet.slug = "office"
                legacy_sheet.response_mode = "office"
            changed = True
        newly_created: list[int] = []
        for slug, defaults in BUILTIN_AGENT_PROFILES.items():
            profile = existing.get(slug)
            # 管理员改过的内置智能体：保留人工配置，只补不覆盖。
            customized = profile is not None and profile.customized_at is not None
            if profile is None:
                profile = AgentProfileModel(
                    name=defaults["name"],
                    slug=slug,
                    description=defaults["description"],
                    system_prompt=defaults["system_prompt"],
                    response_mode=defaults["response_mode"],
                    avatar=defaults["avatar"],
                    enabled=True,
                    listed=bool(defaults["listed"]),
                    max_steps=defaults.get("max_steps"),
                    is_builtin=True,
                )
                db.add(profile)
                db.flush()
                # 新内置智能体必须让所有老用户立刻可用：商店/安装列表只认
                # user_installed_agents，不自动装的话新加的内置 agent 对存量
                # 用户等于不存在（邮箱助手当初就踩了这个坑）。
                newly_created.append(profile.id)
                changed = True
            else:
                profile.is_builtin = True
                if slug == "website" and not customized:
                    current_prompt = profile.system_prompt or ""
                    if "copy_template(stack)" not in current_prompt:
                        profile.system_prompt = WEBSITE_ROUTER_PROMPT
                        changed = True
                if slug == "ppt" and not customized:
                    current_prompt = profile.system_prompt or ""
                    if "ppt-design-guide" not in current_prompt:
                        profile.system_prompt = PPT_SYSTEM_PROMPT
                        changed = True
                    if profile.response_mode != defaults["response_mode"]:
                        profile.response_mode = defaults["response_mode"]
                        changed = True
                    if profile.max_steps is None and defaults.get("max_steps"):
                        profile.max_steps = defaults["max_steps"]
                        changed = True

            if not customized:
                changed = self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS[defaults["response_mode"]]) or changed
                if slug == "website":
                    changed = self._upgrade_website_profile_tools(db, profile) or changed
            changed = self._ensure_profile_skills(db, profile) or changed

        # 一次性纠正（与 customized 无关）：deploy_website 不该走 HITL。
        # 放在循环外只跑一次，扫全表所有 profile。
        changed = self._upgrade_deploy_website_approval(db) or changed

        # Clean up old ppt-svg profile (merged into ppt)
        old_ppt_svg = db.scalar(select(AgentProfileModel).where(AgentProfileModel.slug == "ppt-svg"))
        if old_ppt_svg is not None:
            db.execute(delete(UserInstalledAgentModel).where(UserInstalledAgentModel.profile_id == old_ppt_svg.id))
            db.delete(old_ppt_svg)
            changed = True

        for profile in db.scalars(select(AgentProfileModel)).all():
            if profile.slug not in BUILTIN_AGENT_PROFILES:
                changed = self._ensure_profile_tools(db, profile) or changed

        general = db.scalar(select(AgentProfileModel).where(AgentProfileModel.slug == "general"))
        if general is not None:
            newly_created.append(general.id)

        # 一次性回填：内置、启用、已上架，却**从未被任何人安装过**的 profile，
        # 说明它在存量库里是「上线时没给老用户装」的遗漏，而不是谁主动卸载的。
        # 这类补装不违反「尊重用户卸载」的约定。
        builtin_ids = set(
            db.scalars(
                select(AgentProfileModel.id).where(
                    AgentProfileModel.is_builtin.is_(True),
                    AgentProfileModel.enabled.is_(True),
                    AgentProfileModel.listed.is_(True),
                )
            ).all()
        )
        installed_pairs = {
            (row.user_id, row.profile_id)
            for row in db.scalars(select(UserInstalledAgentModel)).all()
        }
        all_user_ids = set(db.scalars(select(UserModel.id)).all())

        # 只补「本次新建的」+「从没人装过的」这两类；已存在且有人装过的内置
        # profile 一律不碰，用户主动卸载过的不会被塞回来。
        backfill_ids = set(dict.fromkeys(newly_created)) | (builtin_ids - {
            profile_id for _user_id, profile_id in installed_pairs
        })
        for user_id in all_user_ids:
            for profile_id in sorted(backfill_ids):
                if (user_id, profile_id) not in installed_pairs:
                    db.add(UserInstalledAgentModel(user_id=user_id, profile_id=profile_id))
                    changed = True

        if changed:
            db.commit()
        _ensure_defaults_last_run = _time.time()

    @staticmethod
    def _upgrade_website_profile_tools(db: Session, profile: AgentProfileModel) -> bool:
        npm_tool = db.scalar(
            select(AgentProfileToolModel).where(
                AgentProfileToolModel.profile_id == profile.id,
                AgentProfileToolModel.tool_name == "npm",
            )
        )
        if npm_tool is None:
            return False
        if npm_tool.enabled is False and npm_tool.requires_approval is True:
            npm_tool.enabled = True
            db.add(npm_tool)
            return True
        return False

    @staticmethod
    def _upgrade_deploy_website_approval(db: Session) -> bool:
        """一次性纠正：deploy_website 不再需要 HITL 审批。

        它执行时会自己创建部署审批单（website_deploys.status=pending），
        再套一层工具审批就是同一个动作批两次 —— 用户点一次「部署」，管理
        后台冒出两个待审批项。

        默认值改了不够：已存库的行不会自动跟随。这里扫一遍把残留的
        requires_approval=True 清掉。只动这一行、只清这个开关，不碰其它配置。
        """
        rows = db.scalars(
            select(AgentProfileToolModel).where(
                AgentProfileToolModel.tool_name == "deploy_website",
                AgentProfileToolModel.requires_approval.is_(True),
            )
        ).all()
        if not rows:
            return False
        for row in rows:
            row.requires_approval = False
            db.add(row)
        return True

    @staticmethod
    def _resolve_system_prompt(requested: str, response_mode: str) -> str:
        stripped = requested.strip()
        if stripped in GENERIC_PROMPTS:
            return MODE_DEFAULT_PROMPTS.get(response_mode, GENERAL_SYSTEM_PROMPT)
        return requested

    def _ensure_profile_skills(self, db: Session, profile: AgentProfileModel) -> bool:
        """把内置智能体的默认 Skill 绑定补齐（只补不删）。

        只对 ``BUILTIN_AGENT_SKILLS`` 里登记的内置智能体生效，且只在尚未绑定
        时补——管理员手动改过的绑定不会被覆盖。Skill 表里找不到的 slug 直接
        跳过：Skill 是按目录导入的，某些部署可能没导入某个 skill。
        """
        slugs = BUILTIN_AGENT_SKILLS.get(profile.slug or "")
        if not slugs:
            return False
        skill_ids = {
            row.slug: row.id
            for row in db.scalars(select(SkillModel).where(SkillModel.slug.in_(slugs))).all()
        }
        if not skill_ids:
            return False
        bound = {
            row.skill_id
            for row in db.scalars(
                select(AgentProfileSkillModel).where(
                    AgentProfileSkillModel.profile_id == profile.id
                )
            ).all()
        }
        changed = False
        for slug in slugs:
            skill_id = skill_ids.get(slug)
            if skill_id is None or skill_id in bound:
                continue
            db.add(
                AgentProfileSkillModel(
                    profile_id=profile.id,
                    skill_id=skill_id,
                    enabled=True,
                )
            )
            changed = True
        return changed

    def _ensure_profile_tools(
        self,
        db: Session,
        profile: AgentProfileModel,
        defaults: dict[str, dict[str, bool]] | None = None,
        force: bool = False,
    ) -> bool:
        """确保每个工具都有配置行。

        ``force=True`` 时把已有行也改回 ``defaults``（一键还原默认用）；
        否则只在"从未配置过"时补行。注意内置 profile 被管理员改过
        （``customized_at`` 非空）时调用方不会传 defaults，避免启动回写。
        """
        changed = False
        existing = {
            row.tool_name: row
            for row in db.scalars(
                select(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id)
            ).all()
        }
        defaults = defaults or {}
        # 遍历 catalog **和** defaults 的并集：
        # create_document / create_workbook / set_range 这些办公工具是靠
        # _discover_all_mode_tools 自动发现进 DEFAULT_MODE_TOOLS 的，从不手工
        # 登记 TOOL_CATALOG。只遍历 TOOL_CATALOG 的话，这些工具永远不会有行，
        # 于是办公助手「有文档工具但一个都没启用」——用户让它写 Word 只能得到
        # 一句「文档工具不可用」。catalog 里的工具保留 catalog 顺序在前。
        tool_names = list(TOOL_CATALOG) + [n for n in defaults if n not in TOOL_CATALOG]
        for tool_name in tool_names:
            if tool_name in existing:
                # 已有行不再无条件跳过：早期版本种子把新工具以 enabled=False 补进来，
                # 之后再怎么升级都不会被打开。内置 profile 的开关以默认值为准；
                # 用户自建 profile 走 defaults 为空的分支，行为不变。
                row = existing[tool_name]
                settings = defaults.get(tool_name)
                # **只校正内置 profile**：内置的开关是平台默认值的一部分，
                # 用户不能改，所以跟随代码升级是安全的。
                # 自建 profile 的开关是用户自己配的（比如他明确关掉了 file），
                # 按默认值改写会把用户的配置吞掉。
                if settings and row.enabled != settings["enabled"]:
                    # force=True（一键还原默认）时无视 customized_at，
                    # 把开关按默认值写回；常规启动只在没被管理员改过时校正。
                    if force or (profile.is_builtin and profile.customized_at is None):
                        row.enabled = settings["enabled"]
                        db.add(row)
                        changed = True
                if settings and force and row.requires_approval != settings["requires_approval"]:
                    row.requires_approval = settings["requires_approval"]
                    db.add(row)
                    changed = True
                continue
            settings = defaults.get(tool_name, {"enabled": False, "requires_approval": False})
            db.add(
                AgentProfileToolModel(
                    profile_id=profile.id,
                    tool_name=tool_name,
                    enabled=settings["enabled"],
                    requires_approval=settings["requires_approval"],
                )
            )
            changed = True
        return changed

    def _catalog(self) -> list[dict[str, object]]:
        return [
            {
                "name": name,
                "label": item["label"],
                "description": item["description"],
                "approval_scope": item["approval_scope"],
                "sub_tools": [
                    {"name": st_name, "label": st_info["label"], "description": st_info["description"]}
                    for st_name, st_info in item.get("sub_tools", {}).items()
                ],
            }
            for name, item in TOOL_CATALOG.items()
        ]

    @staticmethod
    def _audience_mode_for_users(audience_users: list[UserModel]) -> str:
        return AUDIENCE_MODE_SELECTED if audience_users else AUDIENCE_MODE_ALL

    @staticmethod
    def _serialize_audience_user(user: UserModel) -> dict[str, object]:
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
        }

    def _load_audience_users(self, db: Session, profile_id: int) -> list[UserModel]:
        return db.scalars(
            select(UserModel)
            .join(AgentProfileAudienceModel, AgentProfileAudienceModel.user_id == UserModel.id)
            .where(AgentProfileAudienceModel.profile_id == profile_id)
            .order_by(UserModel.name.asc(), UserModel.email.asc())
        ).all()

    def _load_profile_external_systems(self, db: Session, profile_id: int) -> list[dict[str, object]]:
        rows = db.scalars(
            select(AgentProfileExternalSystemModel).where(
                AgentProfileExternalSystemModel.profile_id == profile_id
            )
        ).all()
        result = []
        for row in rows:
            sys = db.get(ExternalSystemModel, row.system_id)
            if sys:
                result.append({
                    "system_id": row.system_id,
                    "system_name": sys.name,
                    "enabled": row.enabled,
                })
        return result

    def _apply_external_systems(self, db: Session, profile: AgentProfileModel, system_refs: list) -> None:
        """Replace profile-external-system associations."""
        db.execute(delete(AgentProfileExternalSystemModel).where(
            AgentProfileExternalSystemModel.profile_id == profile.id
        ))
        for ref in system_refs:
            if isinstance(ref, dict):
                system_id = ref["system_id"]
                enabled = ref.get("enabled", True)
            else:
                system_id = ref.system_id
                enabled = ref.enabled
            db.add(AgentProfileExternalSystemModel(
                profile_id=profile.id,
                system_id=system_id,
                enabled=enabled,
            ))

    def _apply_audience(
        self,
        db: Session,
        profile: AgentProfileModel,
        *,
        audience_mode: str,
        audience_user_ids: list[int],
    ) -> None:
        if audience_mode not in {AUDIENCE_MODE_ALL, AUDIENCE_MODE_SELECTED}:
            raise ValueError("Unsupported audience mode")

        unique_user_ids = tuple(dict.fromkeys(audience_user_ids))
        if audience_mode == AUDIENCE_MODE_SELECTED:
            if not unique_user_ids:
                raise ValueError("Selected audience mode requires at least one user")
            rows = db.scalars(
                select(UserModel).where(UserModel.id.in_(unique_user_ids), UserModel.is_active.is_(True))
            ).all()
            found_ids = {row.id for row in rows}
            missing = [user_id for user_id in unique_user_ids if user_id not in found_ids]
            if missing:
                raise KeyError(f"Unknown or inactive audience user ids: {missing}")

        db.execute(delete(AgentProfileAudienceModel).where(AgentProfileAudienceModel.profile_id == profile.id))
        if audience_mode == AUDIENCE_MODE_SELECTED:
            for user_id in unique_user_ids:
                db.add(AgentProfileAudienceModel(profile_id=profile.id, user_id=user_id))

    def _is_profile_available_to_user(self, db: Session, profile: AgentProfileModel, user: UserModel) -> bool:
        if not profile.enabled:
            return False
        if user.role == "admin":
            return True
        if profile.is_builtin:
            audience_count = db.scalar(
                select(func.count(AgentProfileAudienceModel.id)).where(
                    AgentProfileAudienceModel.profile_id == profile.id
                )
            ) or 0
            if audience_count == 0:
                return True
            return bool(
                db.scalar(
                    select(AgentProfileAudienceModel.id).where(
                        AgentProfileAudienceModel.profile_id == profile.id,
                        AgentProfileAudienceModel.user_id == user.id,
                    )
                )
            )

        audience_count = db.scalar(
            select(func.count(AgentProfileAudienceModel.id)).where(
                AgentProfileAudienceModel.profile_id == profile.id
            )
        ) or 0
        if audience_count == 0:
            return True
        return bool(
            db.scalar(
                select(AgentProfileAudienceModel.id).where(
                    AgentProfileAudienceModel.profile_id == profile.id,
                    AgentProfileAudienceModel.user_id == user.id,
                )
            )
        )

    def _serialize(self, db: Session, profile: AgentProfileModel, *, user_id: int | None = None) -> dict[str, object]:
        self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(profile.response_mode))
        # 自己创建 / 平台内置的智能体天然可用，无需再"安装"
        is_owner = bool(user_id is not None and profile.owner_id == user_id)
        installed = is_owner or profile.is_builtin
        if user_id is not None and not installed:
            installed = db.scalar(
                select(UserInstalledAgentModel.id).where(
                    UserInstalledAgentModel.user_id == user_id,
                    UserInstalledAgentModel.profile_id == profile.id,
                )
            ) is not None

        tools = db.scalars(
            select(AgentProfileToolModel)
            .where(AgentProfileToolModel.profile_id == profile.id)
            .order_by(AgentProfileToolModel.tool_name.asc())
        ).all()
        skills = self._load_profile_skill_rows(db, profile.id)
        audience_users = self._load_audience_users(db, profile.id)
        ext_systems = self._load_profile_external_systems(db, profile.id)
        return {
            "id": profile.id,
            "name": profile.name,
            "slug": profile.slug,
            "description": profile.description,
            "system_prompt": profile.system_prompt,
            "response_mode": profile.response_mode,
            "avatar": profile.avatar,
            "enabled": profile.enabled,
            "listed": profile.listed,
            "is_builtin": profile.is_builtin,
            # 内置智能体是否已被管理员改过（前端据此显示「已自定义 / 还原」）
            "customized": profile.customized_at is not None,
            "installed": installed,
            "owner_id": profile.owner_id,
            "is_owner": bool(user_id is not None and profile.owner_id == user_id),
            "visibility": profile.visibility or "private",
            "audience_mode": self._audience_mode_for_users(audience_users),
            "audience_users": [self._serialize_audience_user(user) for user in audience_users],
            "tools": self._merge_tools_with_catalog(tools),
            "skills": [self._serialize_skill_reference(skill) for skill in skills],
            "external_systems": ext_systems,
            "max_steps": profile.max_steps,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    @staticmethod
    def _merge_tools_with_catalog(
        stored_tools: list[AgentProfileToolModel],
    ) -> list[dict[str, object]]:
        """Merge stored profile tools with all catalog entries.

        Tools present in TOOL_CATALOG but missing from *stored_tools* are
        appended with ``enabled=False`` and ``requires_approval=False`` so
        that newly-added tools automatically appear in the admin UI without
        breaking existing configurations.

        注意：**不能把「不在手工 catalog 里」的工具丢掉。**
        create_document / create_workbook / set_range 这些办公工具是靠
        _discover_all_mode_tools 自动发现进来的，从来不登记 TOOL_CATALOG。
        早先这里对它们 `continue`，于是数据库里明明有 16 个启用工具，接口
        只回 catalog 里那 5 个 —— 办公助手因此在运行时拿不到文档/表格工具，
        用户让它写 Word 只会得到「文档工具不可用」。
        """
        # 自动发现的工具用最小的占位信息，保证接口能把它们透出去，
        # 同时不改变 catalog 里有完整元数据的那些条目。
        from app.services.tool_config_service import DEFAULT_MODE_TOOLS

        known_via_discovery: set[str] = set()
        for _mode, mapping in DEFAULT_MODE_TOOLS.items():
            known_via_discovery.update(mapping)

        seen: set[str] = set()
        merged: list[dict[str, object]] = []
        for tool in stored_tools:
            if tool.tool_name not in TOOL_CATALOG and tool.tool_name not in known_via_discovery:
                continue
            seen.add(tool.tool_name)
            merged.append({
                "tool_name": tool.tool_name,
                "enabled": tool.enabled,
                "requires_approval": tool.requires_approval,
                "approval_sub_tools": parse_approval_sub_tools(tool.approval_sub_tools_json),
            })
        for name in TOOL_CATALOG:
            if name not in seen:
                merged.append({
                    "tool_name": name,
                    "enabled": False,
                    "requires_approval": False,
                    "approval_sub_tools": [],
                })
        merged.sort(key=lambda t: t["tool_name"])  # type: ignore[index]
        return merged

    def _serialize_prefetched(
        self,
        profile: AgentProfileModel,
        *,
        tools: list[AgentProfileToolModel],
        skills: list[SkillModel],
        audience_users: list[UserModel],
        installed: bool,
        external_systems: list[dict[str, object]] | None = None,
        user_id: int | None = None,
    ) -> dict[str, object]:
        return {
            "id": profile.id,
            "name": profile.name,
            "slug": profile.slug,
            "description": profile.description,
            "system_prompt": profile.system_prompt,
            "response_mode": profile.response_mode,
            "avatar": profile.avatar,
            "enabled": profile.enabled,
            "listed": profile.listed,
            "is_builtin": profile.is_builtin,
            # 内置智能体是否已被管理员改过（前端据此显示「已自定义 / 还原」）
            "customized": profile.customized_at is not None,
            "installed": installed,
            "owner_id": profile.owner_id,
            "is_owner": bool(user_id is not None and profile.owner_id == user_id),
            "visibility": profile.visibility or "private",
            "audience_mode": self._audience_mode_for_users(audience_users),
            "audience_users": [self._serialize_audience_user(user) for user in audience_users],
            "tools": self._merge_tools_with_catalog(tools),
            "skills": [self._serialize_skill_reference(skill) for skill in skills],
            "external_systems": external_systems or [],
            "max_steps": profile.max_steps,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def _serialize_profiles(
        self,
        db: Session,
        profiles: list[AgentProfileModel],
        *,
        user_id: int | None = None,
    ) -> list[dict[str, object]]:
        if not profiles:
            return []

        changed = False
        for profile in profiles:
            changed = self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(profile.response_mode)) or changed
        if changed:
            db.commit()

        profile_ids = [profile.id for profile in profiles]
        tools_by_profile: dict[int, list[AgentProfileToolModel]] = defaultdict(list)
        for row in db.scalars(
            select(AgentProfileToolModel)
            .where(AgentProfileToolModel.profile_id.in_(profile_ids))
            .order_by(AgentProfileToolModel.profile_id.asc(), AgentProfileToolModel.tool_name.asc())
        ).all():
            tools_by_profile[row.profile_id].append(row)

        skills_by_profile: dict[int, list[SkillModel]] = defaultdict(list)
        for profile_id, skill in db.execute(
            select(AgentProfileSkillModel.profile_id, SkillModel)
            .join(SkillModel, SkillModel.id == AgentProfileSkillModel.skill_id)
            .where(AgentProfileSkillModel.profile_id.in_(profile_ids))
            .order_by(AgentProfileSkillModel.profile_id.asc(), SkillModel.name.asc())
        ).all():
            skills_by_profile[int(profile_id)].append(skill)

        audience_by_profile: dict[int, list[UserModel]] = defaultdict(list)
        for profile_id, user in db.execute(
            select(AgentProfileAudienceModel.profile_id, UserModel)
            .join(UserModel, UserModel.id == AgentProfileAudienceModel.user_id)
            .where(AgentProfileAudienceModel.profile_id.in_(profile_ids))
            .order_by(AgentProfileAudienceModel.profile_id.asc(), UserModel.name.asc(), UserModel.email.asc())
        ).all():
            audience_by_profile[int(profile_id)].append(user)

        installed_ids: set[int] = set()
        if user_id is not None:
            installed_ids = {
                int(profile_id)
                for profile_id in db.scalars(
                    select(UserInstalledAgentModel.profile_id).where(
                        UserInstalledAgentModel.user_id == user_id,
                        UserInstalledAgentModel.profile_id.in_(profile_ids),
                    )
                ).all()
            }
            # 自己创建 / 平台内置的智能体天然可用，无需"安装"
            installed_ids.update(
                int(p.id)
                for p in profiles
                if (p.owner_id == user_id or p.is_builtin) and int(p.id) not in installed_ids
            )

        # Prefetch external systems for all profiles
        ext_systems_by_profile: dict[int, list[dict[str, object]]] = defaultdict(list)
        for row in db.scalars(
            select(AgentProfileExternalSystemModel).where(
                AgentProfileExternalSystemModel.profile_id.in_(profile_ids)
            )
        ).all():
            sys = db.get(ExternalSystemModel, row.system_id)
            if sys:
                ext_systems_by_profile[row.profile_id].append({
                    "system_id": row.system_id,
                    "system_name": sys.name,
                    "enabled": row.enabled,
                })

        return [
            self._serialize_prefetched(
                profile,
                tools=tools_by_profile.get(profile.id, []),
                skills=skills_by_profile.get(profile.id, []),
                audience_users=audience_by_profile.get(profile.id, []),
                installed=profile.id in installed_ids if user_id is not None else False,
                external_systems=ext_systems_by_profile.get(profile.id, []),
                user_id=user_id,
            )
            for profile in profiles
        ]

    @staticmethod
    def _can_manage(profile: AgentProfileModel, user: UserModel) -> bool:
        """平台内置（owner_id 为空）只有管理员能改；其余仅所有者或管理员。"""
        if user.role == "admin":
            return True
        return profile.owner_id is not None and profile.owner_id == user.id

    def _assert_can_manage(self, profile: AgentProfileModel, user: UserModel) -> None:
        """权限判定统一走 _can_manage：内置智能体允许管理员改写，其余角色禁止。

        内置智能体不可**删除**（会连累所有用户已安装的记录），删除路径单独拦。
        """
        if not self._can_manage(profile, user):
            raise PermissionError("内置智能体仅管理员可修改" if profile.is_builtin else "只能管理自己创建的智能体")

    def _assert_can_delete(self, profile: AgentProfileModel, user: UserModel) -> None:
        if profile.is_builtin:
            raise PermissionError("内置智能体不可删除，如需停用请关闭「启用」开关")
        self._assert_can_manage(profile, user)

    def list_admin(self) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profiles = db.scalars(select(AgentProfileModel).order_by(AgentProfileModel.created_at.asc())).all()
            return {
                "catalog": self._catalog(),
                "available_skills": self._list_available_skills(db, include_disabled=True),
                "items": self._serialize_profiles(db, profiles),
            }

    def list_store(self, user: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profiles = [
                profile
                for profile in db.scalars(
                    select(AgentProfileModel)
                    .where(
                        AgentProfileModel.enabled.is_(True),
                        # 商店可见条件：管理员上架 listed ∪ 自己创建的 ∪ 用户公开发布的
                        (
                            AgentProfileModel.listed.is_(True)
                            | (AgentProfileModel.owner_id == user.id)
                            | (AgentProfileModel.visibility == "public")
                        ),
                    )
                    .order_by(AgentProfileModel.is_builtin.desc(), AgentProfileModel.created_at.desc())
                ).all()
                if self._is_profile_available_to_user(db, profile, user)
            ]
            return {
                "catalog": self._catalog(),
                "available_skills": self._list_available_skills(db, include_disabled=False),
                "items": self._serialize_profiles(db, profiles, user_id=user.id),
            }

    def list_user_agents(self, user: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            installed_ids = {
                row.profile_id
                for row in db.scalars(
                    select(UserInstalledAgentModel).where(UserInstalledAgentModel.user_id == user.id)
                ).all()
            }
            profiles = [
                profile
                for profile in db.scalars(
                    select(AgentProfileModel)
                    .where(
                        AgentProfileModel.enabled.is_(True),
                        # 内置 ∪ 已安装 ∪ 自己创建的（自建天然可用）
                        #
                        # 内置智能体**不需要安装**：它们是平台自带能力，装上
                        # 才出现的话，用户卸载过一次就再也找不到入口（对话
                        # 页选择器为空）。可见性由 enabled + 可见范围
                        # （_is_profile_available_to_user）决定，与安装记录无关。
                        (
                            AgentProfileModel.is_builtin.is_(True)
                            | AgentProfileModel.id.in_(installed_ids or {-1})
                            | (AgentProfileModel.owner_id == user.id)
                        ),
                    )
                    .order_by(AgentProfileModel.is_builtin.desc(), AgentProfileModel.created_at.asc())
                ).all()
                if self._is_profile_available_to_user(db, profile, user)
            ]
            return {
                "catalog": self._catalog(),
                "available_skills": self._list_available_skills(db, include_disabled=False),
                "items": self._serialize_profiles(db, profiles, user_id=user.id),
            }

    def _unique_slug(self, db: Session, base: str, *, ignore_id: int | None = None) -> str:
        base = slugify(base)
        slug = base
        index = 2
        while True:
            statement = select(AgentProfileModel).where(AgentProfileModel.slug == slug)
            existing = db.scalar(statement)
            if existing is None or existing.id == ignore_id:
                return slug
            slug = f"{base}-{index}"
            index += 1

    def _apply_tools(self, db: Session, profile: AgentProfileModel, tools: list[AgentProfileTool]) -> None:
        """写入 profile 的工具开关。

        **校验集合必须与 `_merge_tools_with_catalog` 的输出一致。**
        那个方法返回的是 ``TOOL_CATALOG ∪ DEFAULT_MODE_TOOLS 里自动发现的工具``
        （read_text_file / append_text_file / send_email 这些子工具靠
        ``_discover_all_mode_tools`` 发现，从不手工登记 TOOL_CATALOG）。
        管理界面把这份列表原样回传，早先这里只认 ``TOOL_CATALOG``，于是
        任何「编辑并保存」都会撞上 ``Unknown tool: append_text_file`` ——
        网站 / 邮箱 / 办公助手全都保存不了。

        宽松一侧是对的：这些工具在运行时确实存在（注册表里真有），
        拒绝它们只会让用户的配置写不进去。
        """
        import json

        allowed = set(TOOL_CATALOG)
        for mapping in DEFAULT_MODE_TOOLS.values():
            allowed.update(mapping)

        existing = {
            row.tool_name: row
            for row in db.scalars(
                select(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id)
            ).all()
        }
        for item in tools:
            if item.tool_name not in allowed:
                raise KeyError(f"Unknown tool: {item.tool_name}")
            row = existing.get(item.tool_name)
            if row is None:
                row = AgentProfileToolModel(profile_id=profile.id, tool_name=item.tool_name)
                db.add(row)
            row.enabled = item.enabled
            row.requires_approval = item.requires_approval
            row.approval_sub_tools_json = json.dumps(item.approval_sub_tools, ensure_ascii=False)

    def _apply_skill_ids(self, db: Session, profile: AgentProfileModel, skill_ids: list[int]) -> None:
        unique_skill_ids = tuple(dict.fromkeys(skill_ids))
        if unique_skill_ids:
            rows = db.scalars(select(SkillModel).where(SkillModel.id.in_(unique_skill_ids))).all()
            found_ids = {row.id for row in rows}
            missing = [skill_id for skill_id in unique_skill_ids if skill_id not in found_ids]
            if missing:
                raise KeyError(f"Unknown skill ids: {missing}")

        db.execute(delete(AgentProfileSkillModel).where(AgentProfileSkillModel.profile_id == profile.id))
        for skill_id in unique_skill_ids:
            db.add(
                AgentProfileSkillModel(
                    profile_id=profile.id,
                    skill_id=skill_id,
                    enabled=True,
                )
            )

    def _default_skill_ids(self, db: Session, slug: str) -> list[int]:
        """按 slug 查出该内置智能体默认应绑定的 Skill id。

        Skill 表由 skill_service 从 data/skills/ 扫描同步，slug 稳定；这里
        查不到的（未同步/已删除）静默跳过，不让启动流程因为缺 Skill 失败。
        """
        wanted = BUILTIN_AGENT_SKILLS.get(slug)
        if not wanted:
            return []
        rows = db.scalars(select(SkillModel).where(SkillModel.slug.in_(tuple(wanted)))).all()
        by_slug = {row.slug: row.id for row in rows}
        return [by_slug[key] for key in wanted if key in by_slug]

    def _bind_default_skills(self, db: Session, profile: AgentProfileModel, slug: str) -> bool:
        """给内置智能体补齐默认 Skill 绑定（不覆盖管理员手工调整过的）。"""
        wanted_ids = self._default_skill_ids(db, slug)
        if not wanted_ids:
            return False
        existing = {
            row.skill_id
            for row in db.scalars(
                select(AgentProfileSkillModel).where(AgentProfileSkillModel.profile_id == profile.id)
            ).all()
        }
        missing = [skill_id for skill_id in wanted_ids if skill_id not in existing]
        for skill_id in missing:
            db.add(AgentProfileSkillModel(profile_id=profile.id, skill_id=skill_id, enabled=True))
        return bool(missing)

    def _reset_profile_tools(self, db: Session, profile: AgentProfileModel) -> None:
        """把工具行恢复成响应模式的默认开关/审批配置（还原默认、或沙盒库补齐时用）。"""
        defaults = DEFAULT_MODE_TOOLS.get(profile.response_mode) or {}
        db.execute(delete(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id))
        db.flush()
        self._ensure_profile_tools(
            db, profile, defaults, force=True
        )

    def create(self, request: AgentProfileCreateRequest, creator: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = AgentProfileModel(
                name=request.name,
                slug=self._unique_slug(db, request.slug or request.name),
                description=request.description,
                system_prompt=self._resolve_system_prompt(request.system_prompt, request.response_mode),
                response_mode=request.response_mode,
                avatar=request.avatar,
                enabled=request.enabled,
                listed=request.listed,
                max_steps=request.max_steps,
                is_builtin=False,
                created_by=creator.id,
                owner_id=creator.id,
                visibility=request.visibility,
            )
            db.add(profile)
            db.flush()
            self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(request.response_mode))
            db.flush()
            if request.tools:
                self._apply_tools(db, profile, request.tools)
            if request.skill_ids:
                self._apply_skill_ids(db, profile, request.skill_ids)
            if request.external_systems:
                self._apply_external_systems(db, profile, request.external_systems)
            self._apply_audience(
                db,
                profile,
                audience_mode=request.audience_mode,
                audience_user_ids=request.audience_user_ids,
            )
            db.commit()
            db.refresh(profile)
            return self._serialize(db, profile, user_id=creator.id)

    def update(
        self,
        profile_id: int,
        request: AgentProfileUpdateRequest,
        user: UserModel | None = None,
    ) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                raise KeyError("Agent profile not found")
            if user is not None:
                self._assert_can_manage(profile, user)

            if request.name is not None:
                profile.name = request.name
            if request.slug is not None:
                profile.slug = self._unique_slug(db, request.slug, ignore_id=profile.id)
            if request.description is not None:
                profile.description = request.description
            if request.system_prompt is not None:
                profile.system_prompt = request.system_prompt
            if request.response_mode is not None:
                old_mode = profile.response_mode
                profile.response_mode = request.response_mode
                if request.response_mode != old_mode and profile.system_prompt.strip() in GENERIC_PROMPTS:
                    profile.system_prompt = MODE_DEFAULT_PROMPTS.get(
                        request.response_mode, GENERAL_SYSTEM_PROMPT
                    )
                elif request.system_prompt is None and profile.system_prompt.strip() in GENERIC_PROMPTS:
                    profile.system_prompt = MODE_DEFAULT_PROMPTS.get(
                        request.response_mode, GENERAL_SYSTEM_PROMPT
                    )
            if request.avatar is not None:
                profile.avatar = request.avatar
            if request.enabled is not None:
                profile.enabled = request.enabled
            if request.listed is not None:
                profile.listed = request.listed
            if request.max_steps is not None:
                profile.max_steps = request.max_steps
            if request.visibility is not None:
                profile.visibility = request.visibility
            if request.tools is not None:
                self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(profile.response_mode))
                db.flush()
                self._apply_tools(db, profile, request.tools)
            if request.skill_ids is not None:
                self._apply_skill_ids(db, profile, request.skill_ids)
            if request.external_systems is not None:
                self._apply_external_systems(db, profile, request.external_systems)
            if request.audience_mode is not None or request.audience_user_ids is not None:
                current_audience_users = self._load_audience_users(db, profile.id)
                current_audience_ids = [user.id for user in current_audience_users]
                self._apply_audience(
                    db,
                    profile,
                    audience_mode=request.audience_mode or self._audience_mode_for_users(current_audience_users),
                    audience_user_ids=(
                        request.audience_user_ids
                        if request.audience_user_ids is not None
                        else current_audience_ids
                    ),
                )

            # 内置智能体被人工改过就落标记：ensure_defaults 之后不再回写
            # 代码里的默认 prompt / 工具开关，否则管理员改完刷新一下就被覆盖。
            if profile.is_builtin:
                profile.customized_at = app_now()

            db.add(profile)
            db.commit()
            db.refresh(profile)
            return self._serialize(db, profile, user_id=user.id if user else None)

    def restore_defaults(self, profile_id: int, user: UserModel | None = None) -> dict[str, object]:
        """把内置智能体还原成代码中的出厂定义（名称/prompt/模式/工具/技能）。"""
        with self.session_factory() as db:
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                raise KeyError("Agent profile not found")
            if user is not None:
                self._assert_can_manage(profile, user)
            defaults = BUILTIN_AGENT_PROFILES.get(profile.slug)
            if not profile.is_builtin or defaults is None:
                raise ValueError("只有内置智能体支持还原默认配置")

            profile.name = defaults["name"]
            profile.description = defaults["description"]
            profile.system_prompt = defaults["system_prompt"]
            profile.response_mode = defaults["response_mode"]
            profile.avatar = defaults["avatar"]
            profile.listed = bool(defaults["listed"])
            profile.enabled = True
            profile.max_steps = defaults.get("max_steps")
            # 清掉标记 → 重新跟随内置定义
            profile.customized_at = None
            db.add(profile)
            db.flush()
            # 工具回出厂开关，多余的自定义行删掉
            self._reset_profile_tools(db, profile)
            # 技能回出厂绑定
            self._apply_skill_ids(db, profile, self._default_skill_ids(db, profile.slug))
            db.commit()
            db.refresh(profile)
            return self._serialize(db, profile, user_id=user.id if user else None)

    def delete(self, profile_id: int, user: UserModel | None = None) -> None:
        with self.session_factory() as db:
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                raise KeyError("Agent profile not found")
            if user is not None:
                self._assert_can_manage(profile, user)
            if profile.is_builtin:
                raise ValueError("内置智能体不可删除")

            db.execute(delete(UserInstalledAgentModel).where(UserInstalledAgentModel.profile_id == profile_id))
            db.execute(delete(AgentProfileAudienceModel).where(AgentProfileAudienceModel.profile_id == profile_id))
            db.execute(delete(AgentProfileSkillModel).where(AgentProfileSkillModel.profile_id == profile_id))
            db.execute(delete(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile_id))
            db.execute(delete(AgentProfileExternalSystemModel).where(AgentProfileExternalSystemModel.profile_id == profile_id))
            db.delete(profile)
            db.commit()

    def install(self, profile_id: int, user: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None or not profile.enabled or not profile.listed or not self._is_profile_available_to_user(db, profile, user):
                raise KeyError("Agent profile not found")
            existing = db.scalar(
                select(UserInstalledAgentModel).where(
                    UserInstalledAgentModel.user_id == user.id,
                    UserInstalledAgentModel.profile_id == profile_id,
                )
            )
            if existing is None:
                db.add(UserInstalledAgentModel(user_id=user.id, profile_id=profile_id))
                db.commit()
            return self._serialize(db, profile, user_id=user.id)

    def uninstall(self, profile_id: int, user: UserModel) -> None:
        with self.session_factory() as db:
            profile = db.get(AgentProfileModel, profile_id)
            if profile is not None and profile.slug == "general":
                return
            db.execute(
                delete(UserInstalledAgentModel).where(
                    UserInstalledAgentModel.user_id == user.id,
                    UserInstalledAgentModel.profile_id == profile_id,
                )
            )
            db.commit()

    def resolve_runtime(
        self,
        profile_id: int,
        user: UserModel,
        *,
        approval_mode: str = "auto",
        plan_mode: bool = False,
    ) -> RuntimeAgentProfile:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None or not self._is_profile_available_to_user(db, profile, user):
                raise PermissionError("Agent profile is not available")
            # 与 list_user_agents 保持同一口径：内置（平台自带）与自建
            # （自己就是所有者）都不需要安装记录，只有「别人发布、我要用」
            # 的商店智能体才要求先安装。
            if user.role != "admin" and not profile.is_builtin and profile.owner_id != user.id:
                installed = db.scalar(
                    select(func.count(UserInstalledAgentModel.id)).where(
                        UserInstalledAgentModel.user_id == user.id,
                        UserInstalledAgentModel.profile_id == profile.id,
                    )
                )
                if not installed:
                    raise PermissionError("请先安装该智能体再使用")

            return self._runtime_from_profile(
                db, profile, approval_mode=approval_mode,
                is_admin_actor=user.role == "admin", plan_mode=plan_mode,
            )

    def resolve_runtime_published(self, slug: str) -> RuntimeAgentProfile:
        """??????????????? slug ???

        ??? published=True ? profile??????? profile ??
        ?is_admin_actor=False??????????????????
        """
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.scalar(
                select(AgentProfileModel).where(
                    AgentProfileModel.publish_slug == slug,
                    AgentProfileModel.published.is_(True),
                    AgentProfileModel.enabled.is_(True),
                )
            )
            if profile is None:
                raise PermissionError("Published agent not found")
            return self._runtime_from_profile(
                db, profile, approval_mode="auto", is_admin_actor=False, plan_mode=False,
            )

    # -- Prompt ???? --

    def _snapshot_config(self, db, profile) -> dict:
        """???????????? + ??/?????"""
        tools = db.scalars(
            select(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id)
        ).all()
        skills = db.scalars(
            select(AgentProfileSkillModel).where(AgentProfileSkillModel.profile_id == profile.id)
        ).all()
        return {
            "name": profile.name,
            "description": profile.description,
            "system_prompt": profile.system_prompt,
            "response_mode": profile.response_mode,
            "avatar": profile.avatar,
            "max_steps": profile.max_steps,
            "tools": [
                {"tool_name": t.tool_name, "enabled": t.enabled, "requires_approval": t.requires_approval}
                for t in tools
            ],
            "skills": [s.slug for s in skills],
        }

    def save_profile_version(self, profile_id: int, *, created_by: int | None, note: str | None = None) -> int | None:
        """??????????????????profile ????? None?"""
        with self.session_factory() as db:
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                return None
            latest = db.scalar(
                select(func.max(AgentProfileVersionModel.version)).where(
                    AgentProfileVersionModel.profile_id == profile_id
                )
            )
            version = int(latest or 0) + 1
            db.add(
                AgentProfileVersionModel(
                    profile_id=profile_id,
                    version=version,
                    config_json=_json.dumps(
                        self._snapshot_config(db, profile), ensure_ascii=False
                    ),
                    note=note,
                    created_by=created_by,
                )
            )
            db.commit()
            return version

    def list_profile_versions(self, profile_id: int) -> list[dict]:
        """??????????config_json ?????????????"""
        with self.session_factory() as db:
            rows = db.scalars(
                select(AgentProfileVersionModel)
                .where(AgentProfileVersionModel.profile_id == profile_id)
                .order_by(AgentProfileVersionModel.version.desc())
                .limit(50)
            ).all()
            return [
                {
                    "id": r.id,
                    "version": r.version,
                    "note": r.note,
                    "created_by": r.created_by,
                    "created_at": isoformat_app_timezone(r.created_at),
                }
                for r in rows
            ]

    def get_profile_version(self, profile_id: int, version: int) -> dict | None:
        with self.session_factory() as db:
            row = db.scalar(
                select(AgentProfileVersionModel).where(
                    AgentProfileVersionModel.profile_id == profile_id,
                    AgentProfileVersionModel.version == version,
                )
            )
            if row is None:
                return None
            return {
                "id": row.id,
                "version": row.version,
                "note": row.note,
                "created_at": isoformat_app_timezone(row.created_at),
                "config": _json.loads(row.config_json),
            }

    def restore_profile_version(self, profile_id: int, version: int) -> bool:
        """?????????????????????????????"""
        snapshot = self.get_profile_version(profile_id, version)
        if snapshot is None:
            return False
        config = snapshot["config"]
        with self.session_factory() as db:
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                return False
            self.save_profile_version(profile_id, created_by=None, note=f"restore before v{version}")
            profile.name = config.get("name") or profile.name
            profile.description = config.get("description") or ""
            profile.system_prompt = config.get("system_prompt") or profile.system_prompt
            profile.response_mode = config.get("response_mode") or profile.response_mode
            profile.avatar = config.get("avatar")
            profile.max_steps = config.get("max_steps")
            db.execute(
                delete(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile_id)
            )
            for tool in config.get("tools", []):
                db.add(
                    AgentProfileToolModel(
                        profile_id=profile_id,
                        tool_name=tool["tool_name"],
                        enabled=bool(tool.get("enabled", False)),
                        requires_approval=bool(tool.get("requires_approval", False)),
                    )
                )
            db.commit()
        return True

    def resolve_runtime_by_mode(
        self,
        response_mode: str,
        user: UserModel,
        *,
        approval_mode: str = "auto",
        plan_mode: bool = False,
    ) -> RuntimeAgentProfile:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.scalar(
                select(AgentProfileModel).where(
                    AgentProfileModel.slug == response_mode,
                    AgentProfileModel.is_builtin.is_(True),
                )
            )
            if profile is None or not self._is_profile_available_to_user(db, profile, user):
                raise PermissionError("Agent profile is not available")
            return self._runtime_from_profile(
                db,
                profile,
                approval_mode=approval_mode,
                is_admin_actor=user.role == "admin",
                plan_mode=plan_mode,
            )

    def _runtime_from_profile(
        self,
        db: Session,
        profile: AgentProfileModel,
        *,
        approval_mode: str = "auto",
        is_admin_actor: bool = False,
        plan_mode: bool = False,
    ) -> RuntimeAgentProfile:
        self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(profile.response_mode))
        rows = db.scalars(
            select(AgentProfileToolModel)
            .where(AgentProfileToolModel.profile_id == profile.id)
            .order_by(AgentProfileToolModel.tool_name.asc())
        ).all()
        skills = tuple(
            RuntimeSkill(
                id=skill.id,
                name=skill.name,
                slug=skill.slug,
                root_dir=skill.root_dir,
                updated_at=isoformat_app_timezone(skill.updated_at) or "",
            )
            for skill in self._load_profile_skill_rows(db, profile.id, only_enabled=True)
        )
        builtin_tools: list[str] = []
        approval_tools: set[str] = set()
        signature: list[tuple[str, bool, bool]] = []
        # 具体工具名 → 归属的 catalog 条目名。用于把「管理员勾了哪个工具」
        # 翻译成「注册表里哪些具体工具名可以留下」。
        tool_name_to_catalog: dict[str, str] = {}
        for row in rows:
            catalog_item = TOOL_CATALOG.get(row.tool_name)
            if not catalog_item:
                continue
            signature.append((row.tool_name, row.enabled, row.requires_approval))
            if not row.enabled:
                continue
            if catalog_item.get("builtin_name"):
                builtin_tools.append(catalog_item["builtin_name"])
            if row.requires_approval:
                configured_sub_tools = parse_approval_sub_tools(row.approval_sub_tools_json)
                all_sub_tools = list(catalog_item["sub_tools"].keys())
                if configured_sub_tools:
                    approval_tools.update(
                        item for item in configured_sub_tools
                        if item in all_sub_tools
                    )
                else:
                    approval_tools.update(str(item) for item in catalog_item["approval_scope"])

        allowed_tools = self._compute_allowed_tools(
            profile.response_mode,
            enabled_catalog_names={
                name for name, enabled, _ in signature if enabled
            },
        )

        # Load enabled external system IDs for this profile
        ext_system_ids = tuple(
            db.scalars(
                select(AgentProfileExternalSystemModel.system_id).where(
                    AgentProfileExternalSystemModel.profile_id == profile.id,
                    AgentProfileExternalSystemModel.enabled.is_(True),
                )
            ).all()
        )

        # Add external API tool names that require approval
        # 集成工具的审批由工具内部按 API 级别控制（ApprovalBlocker），不在这里添加到 approval_tools

        return RuntimeAgentProfile(
            profile_id=profile.id,
            name=profile.name,
            slug=profile.slug,
            response_mode=profile.response_mode if profile.response_mode in AGENT_MODES else "general",
            system_prompt=profile.system_prompt,
            builtin_tools=tuple(dict.fromkeys(builtin_tools)),
            approval_tools=frozenset(approval_tools),
            signature=tuple(signature),
            skills=skills,
            external_system_ids=ext_system_ids,
            max_steps=profile.max_steps,
            approval_mode=approval_mode,
            is_admin_actor=is_admin_actor,
            plan_mode=plan_mode,
            allowed_tools=allowed_tools,
        )

    @staticmethod
    def _compute_allowed_tools(
        response_mode: str,
        *,
        enabled_catalog_names: set[str],
    ) -> frozenset[str]:
        """算出该 profile 允许使用的**具体工具名**白名单。

        注册表里有两类工具来源，管控方式原本不一致：

        1. **builtin 插件类**（calc / time / file / python / git / npm …）：
           由 profile 的 enabled 开关控制，通过 builtin_tools 下发。
        2. **模式注册类**（website_tools / sheet_tools / doc_tools /
           email_tools / website_file_tools）：按 response_mode **整体注册**，
           此前完全绕过 profile 配置 —— 管理员在界面里关掉「文件工具」或
           「部署网站」，工具照样能用（实测通用助手注册表里带着
           write_text_file / delete_file，而它的 builtin_tools 只有
           calc/file/time）。

        这里把两类统一到同一套规则：**一个具体工具能被下发，当且仅当它在
        某个已启用的 catalog 条目下**。

        归属关系从 catalog 条目正向反查（条目 → 它管的子工具名），
        而不是从工具名反查条目 —— 后者要靠模块名猜，既脆弱又难读。

        例：file 条目启用 → 放行 read_text_file / write_text_file /
        list_files / append_text_file / replace_text_in_file / delete_file；
        file 条目关闭 → 这些全部不放行。
        """
        allowed: set[str] = set()

        # 所有 catalog 条目管辖的具体工具名（无论是否启用）。
        # 用来区分「有归属的工具」与「纯模式级工具」——前者必须看开关，
        # 后者才随模式无条件放行。
        managed_by_catalog: set[str] = set()
        for entry in TOOL_CATALOG.values():
            managed_by_catalog.update(str(i) for i in entry.get("sub_tools", {}).keys())
            managed_by_catalog.update(str(i) for i in entry.get("approval_scope", []))

        # 1) 已启用的 catalog 条目 → 它管的具体工具名
        for entry_name in enabled_catalog_names:
            entry = TOOL_CATALOG.get(entry_name)
            if not entry:
                continue
            allowed.update(str(item) for item in entry.get("sub_tools", {}).keys())
            allowed.update(str(item) for item in entry.get("approval_scope", []))
            # builtin 插件本身也是一个工具名（calc / time / file …）
            builtin_name = entry.get("builtin_name")
            if builtin_name:
                allowed.add(str(builtin_name))

        # 2) 自动发现的模式级工具（create_workbook / build_website …）。
        #
        # **只放行没有 catalog 归属的**。有归属的（如 write_text_file 归 file
        # 条目、deploy_website 归同名条目）必须走上面的 enabled 检查 ——
        # 否则「关掉文件工具」形同虚设：website_file_tools 在所有模式无条件
        # 注册，又被模式发现列表兜进来，管理员怎么关都关不掉。
        from app.services.tool_config_service import _discover_all_mode_tools

        for tool_name in _discover_all_mode_tools().get(response_mode, set()):
            if tool_name in managed_by_catalog:
                continue
            allowed.add(tool_name)

        return frozenset(allowed)

    def _load_profile_skill_rows(
        self,
        db: Session,
        profile_id: int,
        *,
        only_enabled: bool = False,
    ) -> list[SkillModel]:
        statement = (
            select(SkillModel)
            .join(AgentProfileSkillModel, AgentProfileSkillModel.skill_id == SkillModel.id)
            .where(AgentProfileSkillModel.profile_id == profile_id)
            .order_by(SkillModel.name.asc())
        )
        if only_enabled:
            statement = statement.where(
                AgentProfileSkillModel.enabled.is_(True),
                SkillModel.enabled.is_(True),
            )
        return db.scalars(statement).all()

    def _list_available_skills(self, db: Session, *, include_disabled: bool) -> list[dict[str, object]]:
        statement = select(SkillModel).order_by(SkillModel.name.asc())
        if not include_disabled:
            statement = statement.where(SkillModel.enabled.is_(True))
        return [self._serialize_skill_reference(skill) for skill in db.scalars(statement).all()]

    @staticmethod
    def _serialize_skill_reference(skill: SkillModel) -> dict[str, object]:
        root_dir = Path(skill.root_dir)
        script_paths = SkillService._list_scripts(root_dir)
        reference_paths = SkillService._list_references(root_dir)
        return {
            "id": skill.id,
            "name": skill.name,
            "slug": skill.slug,
            "description": skill.description,
            "enabled": skill.enabled,
            "has_python_scripts": bool(script_paths),
            "script_paths": script_paths,
            "has_references": bool(reference_paths),
            "reference_paths": reference_paths,
        }


def seed_agent_profiles() -> None:
    with create_db_session() as db:
        AgentProfileService().ensure_defaults(db)
