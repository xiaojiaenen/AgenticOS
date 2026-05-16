from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.timezone import isoformat_app_timezone
from app.db.models import (
    AgentProfileModel,
    AgentProfileAudienceModel,
    AgentProfileSkillModel,
    AgentProfileToolModel,
    SkillModel,
    UserInstalledAgentModel,
    UserModel,
)
from app.db.session import create_db_session
from app.prompts import GENERAL_SYSTEM_PROMPT, PPT_SYSTEM_PROMPT, WEBSITE_SYSTEM_PROMPT, EMAIL_SYSTEM_PROMPT
from app.schemas.agent_profiles import AgentProfileCreateRequest, AgentProfileTool, AgentProfileUpdateRequest
from app.services.skill_service import RuntimeSkill, SkillService
from app.services.tool_config_service import AGENT_MODES, DEFAULT_MODE_TOOLS, TOOL_CATALOG


AUDIENCE_MODE_ALL = "all"
AUDIENCE_MODE_SELECTED = "selected"

MODE_DEFAULT_PROMPTS: dict[str, str] = {
    "general": GENERAL_SYSTEM_PROMPT,
    "ppt": PPT_SYSTEM_PROMPT,
    "website": WEBSITE_SYSTEM_PROMPT,
    "email": EMAIL_SYSTEM_PROMPT,
}

GENERIC_PROMPTS = {
    "你是 AgenticOS 的通用智能助手，请优先给出准确、清晰、可执行的回答。",
    "你是一个专注于特定任务的 AgenticOS 智能体。请根据用户目标主动拆解任务，必要时调用可用工具，并给出清晰可执行的结果。",
    "",
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
        "description": "将想法整理为结构化演示文稿，自动生成可预览的 PPT 内容。",
        "system_prompt": PPT_SYSTEM_PROMPT,
        "response_mode": "ppt",
        "avatar": "presentation",
        "listed": True,
    },
    "website": {
        "name": "网站工程师",
        "description": "用于页面方案、前端代码、交互原型和网站结构设计。",
        "system_prompt": WEBSITE_SYSTEM_PROMPT,
        "response_mode": "website",
        "avatar": "globe",
        "listed": True,
    },
    "email": {
        "name": "邮件助手",
        "description": "帮助用户读取、搜索、发送公司邮件，支持抄送功能。",
        "system_prompt": EMAIL_SYSTEM_PROMPT,
        "response_mode": "general",
        "avatar": "mail",
        "listed": True,
    },
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


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower().replace("_", "-"))
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "agent"


class AgentProfileService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    def ensure_defaults(self, db: Session) -> None:
        changed = False
        existing = {row.slug: row for row in db.scalars(select(AgentProfileModel)).all()}
        for slug, defaults in BUILTIN_AGENT_PROFILES.items():
            profile = existing.get(slug)
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
                    is_builtin=True,
                )
                db.add(profile)
                db.flush()
                changed = True
            else:
                profile.is_builtin = True
                if slug == "website":
                    current_prompt = profile.system_prompt or ""
                    if "data/websites/<project_slug>/" not in current_prompt:
                        profile.system_prompt = WEBSITE_SYSTEM_PROMPT
                        changed = True
                if slug == "ppt":
                    current_prompt = profile.system_prompt or ""
                    if "第0步：创作前必须确认" not in current_prompt:
                        profile.system_prompt = PPT_SYSTEM_PROMPT
                        changed = True

            changed = self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS[slug]) or changed
            if slug == "website":
                changed = self._upgrade_website_profile_tools(db, profile) or changed
        for profile in db.scalars(select(AgentProfileModel)).all():
            if profile.slug not in BUILTIN_AGENT_PROFILES:
                changed = self._ensure_profile_tools(db, profile) or changed

        general = db.scalar(select(AgentProfileModel).where(AgentProfileModel.slug == "general"))
        if general is not None:
            all_user_ids = set(db.scalars(select(UserModel.id)).all())
            installed_user_ids = {
                row.user_id
                for row in db.scalars(
                    select(UserInstalledAgentModel).where(
                        UserInstalledAgentModel.profile_id == general.id
                    )
                ).all()
            }
            for user_id in all_user_ids - installed_user_ids:
                db.add(UserInstalledAgentModel(user_id=user_id, profile_id=general.id))
                changed = True

        if changed:
            db.commit()

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
    def _resolve_system_prompt(requested: str, response_mode: str) -> str:
        stripped = requested.strip()
        if stripped in GENERIC_PROMPTS:
            return MODE_DEFAULT_PROMPTS.get(response_mode, GENERAL_SYSTEM_PROMPT)
        return requested

    def _ensure_profile_tools(
        self,
        db: Session,
        profile: AgentProfileModel,
        defaults: dict[str, dict[str, bool]] | None = None,
    ) -> bool:
        changed = False
        existing = {
            row.tool_name: row
            for row in db.scalars(
                select(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id)
            ).all()
        }
        defaults = defaults or {}
        for tool_name in TOOL_CATALOG:
            if tool_name in existing:
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
        installed = False
        if user_id is not None:
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
            "installed": installed,
            "audience_mode": self._audience_mode_for_users(audience_users),
            "audience_users": [self._serialize_audience_user(user) for user in audience_users],
            "tools": [
                {
                    "tool_name": tool.tool_name,
                    "enabled": tool.enabled,
                    "requires_approval": tool.requires_approval,
                    "approval_sub_tools": self._parse_approval_sub_tools(tool.approval_sub_tools_json),
                }
                for tool in tools
                if tool.tool_name in TOOL_CATALOG
            ],
            "skills": [self._serialize_skill_reference(skill) for skill in skills],
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def _serialize_prefetched(
        self,
        profile: AgentProfileModel,
        *,
        tools: list[AgentProfileToolModel],
        skills: list[SkillModel],
        audience_users: list[UserModel],
        installed: bool,
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
            "installed": installed,
            "audience_mode": self._audience_mode_for_users(audience_users),
            "audience_users": [self._serialize_audience_user(user) for user in audience_users],
            "tools": [
                {
                    "tool_name": tool.tool_name,
                    "enabled": tool.enabled,
                    "requires_approval": tool.requires_approval,
                    "approval_sub_tools": self._parse_approval_sub_tools(tool.approval_sub_tools_json),
                }
                for tool in tools
                if tool.tool_name in TOOL_CATALOG
            ],
            "skills": [self._serialize_skill_reference(skill) for skill in skills],
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

        return [
            self._serialize_prefetched(
                profile,
                tools=tools_by_profile.get(profile.id, []),
                skills=skills_by_profile.get(profile.id, []),
                audience_users=audience_by_profile.get(profile.id, []),
                installed=profile.id in installed_ids if user_id is not None else False,
            )
            for profile in profiles
        ]

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
                    .where(AgentProfileModel.enabled.is_(True), AgentProfileModel.listed.is_(True))
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
                        AgentProfileModel.id.in_(installed_ids or {-1}),
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
        base = _slugify(base)
        slug = base
        index = 2
        while True:
            statement = select(AgentProfileModel).where(AgentProfileModel.slug == slug)
            existing = db.scalar(statement)
            if existing is None or existing.id == ignore_id:
                return slug
            slug = f"{base}-{index}"
            index += 1

    @staticmethod
    def _parse_approval_sub_tools(json_str: str) -> list[str]:
        import json
        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    def _apply_tools(self, db: Session, profile: AgentProfileModel, tools: list[AgentProfileTool]) -> None:
        import json
        existing = {
            row.tool_name: row
            for row in db.scalars(
                select(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile.id)
            ).all()
        }
        for item in tools:
            if item.tool_name not in TOOL_CATALOG:
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
                is_builtin=False,
                created_by=creator.id,
            )
            db.add(profile)
            db.flush()
            self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(request.response_mode))
            db.flush()
            if request.tools:
                self._apply_tools(db, profile, request.tools)
            if request.skill_ids:
                self._apply_skill_ids(db, profile, request.skill_ids)
            self._apply_audience(
                db,
                profile,
                audience_mode=request.audience_mode,
                audience_user_ids=request.audience_user_ids,
            )
            db.commit()
            db.refresh(profile)
            return self._serialize(db, profile)

    def update(self, profile_id: int, request: AgentProfileUpdateRequest) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                raise KeyError("Agent profile not found")

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
            if request.tools is not None:
                self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(profile.response_mode))
                db.flush()
                self._apply_tools(db, profile, request.tools)
            if request.skill_ids is not None:
                self._apply_skill_ids(db, profile, request.skill_ids)
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

            db.add(profile)
            db.commit()
            db.refresh(profile)
            return self._serialize(db, profile)

    def delete(self, profile_id: int) -> None:
        with self.session_factory() as db:
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None:
                raise KeyError("Agent profile not found")
            if profile.is_builtin:
                raise ValueError("Built-in agent profiles cannot be deleted")

            db.execute(delete(UserInstalledAgentModel).where(UserInstalledAgentModel.profile_id == profile_id))
            db.execute(delete(AgentProfileAudienceModel).where(AgentProfileAudienceModel.profile_id == profile_id))
            db.execute(delete(AgentProfileSkillModel).where(AgentProfileSkillModel.profile_id == profile_id))
            db.execute(delete(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile_id))
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

    def resolve_runtime(self, profile_id: int, user: UserModel) -> RuntimeAgentProfile:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None or not self._is_profile_available_to_user(db, profile, user):
                raise PermissionError("Agent profile is not available")
            if user.role != "admin":
                installed = db.scalar(
                    select(func.count(UserInstalledAgentModel.id)).where(
                        UserInstalledAgentModel.user_id == user.id,
                        UserInstalledAgentModel.profile_id == profile.id,
                    )
                )
                if not installed:
                    raise PermissionError("Please install this agent before using it")

            return self._runtime_from_profile(db, profile)

    def resolve_runtime_by_mode(self, response_mode: str, user: UserModel) -> RuntimeAgentProfile:
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
            return self._runtime_from_profile(db, profile)

    def _runtime_from_profile(self, db: Session, profile: AgentProfileModel) -> RuntimeAgentProfile:
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
        for row in rows:
            catalog_item = TOOL_CATALOG.get(row.tool_name)
            if not catalog_item:
                continue
            signature.append((row.tool_name, row.enabled, row.requires_approval))
            if not row.enabled:
                continue
            builtin_tools.append(str(catalog_item["builtin_name"]))
            if row.requires_approval:
                configured_sub_tools = self._parse_approval_sub_tools(row.approval_sub_tools_json)
                all_sub_tools = list(catalog_item["sub_tools"].keys())
                if configured_sub_tools:
                    approval_tools.update(
                        item for item in configured_sub_tools
                        if item in all_sub_tools
                    )
                else:
                    approval_tools.update(str(item) for item in catalog_item["approval_scope"])

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
        )

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
