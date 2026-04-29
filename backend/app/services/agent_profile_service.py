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
    AgentProfileSkillModel,
    AgentProfileToolModel,
    SkillModel,
    UserInstalledAgentModel,
    UserModel,
)
from app.db.session import create_db_session
from app.prompts import GENERAL_SYSTEM_PROMPT, PPT_SYSTEM_PROMPT, WEBSITE_SYSTEM_PROMPT
from app.schemas.agent_profiles import AgentProfileCreateRequest, AgentProfileTool, AgentProfileUpdateRequest
from app.services.skill_service import RuntimeSkill
from app.services.tool_config_service import AGENT_MODES, DEFAULT_MODE_TOOLS, TOOL_CATALOG


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

            changed = self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS[slug]) or changed
            if slug == "website":
                changed = self._upgrade_website_profile_tools(db, profile) or changed
        for profile in db.scalars(select(AgentProfileModel)).all():
            if profile.slug not in BUILTIN_AGENT_PROFILES:
                changed = self._ensure_profile_tools(db, profile) or changed
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
            }
            for name, item in TOOL_CATALOG.items()
        ]

    def _serialize(self, db: Session, profile: AgentProfileModel, *, user_id: int | None = None) -> dict[str, object]:
        self._ensure_profile_tools(db, profile, DEFAULT_MODE_TOOLS.get(profile.response_mode))
        installed = profile.is_builtin
        if user_id is not None and not profile.is_builtin:
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
            "tools": [
                {
                    "tool_name": tool.tool_name,
                    "enabled": tool.enabled,
                    "requires_approval": tool.requires_approval,
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
            "tools": [
                {
                    "tool_name": tool.tool_name,
                    "enabled": tool.enabled,
                    "requires_approval": tool.requires_approval,
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
                installed=profile.is_builtin or profile.id in installed_ids if user_id is not None else profile.is_builtin,
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
            profiles = db.scalars(
                select(AgentProfileModel)
                .where(AgentProfileModel.enabled.is_(True), AgentProfileModel.listed.is_(True))
                .order_by(AgentProfileModel.is_builtin.desc(), AgentProfileModel.created_at.desc())
            ).all()
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
            profiles = db.scalars(
                select(AgentProfileModel)
                .where(
                    AgentProfileModel.enabled.is_(True),
                    (AgentProfileModel.is_builtin.is_(True)) | (AgentProfileModel.id.in_(installed_ids or {-1})),
                )
                .order_by(AgentProfileModel.is_builtin.desc(), AgentProfileModel.created_at.asc())
            ).all()
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

    def _apply_tools(self, db: Session, profile: AgentProfileModel, tools: list[AgentProfileTool]) -> None:
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

        if unique_skill_ids:
            skill_tool = db.scalar(
                select(AgentProfileToolModel).where(
                    AgentProfileToolModel.profile_id == profile.id,
                    AgentProfileToolModel.tool_name == "skill",
                )
            )
            if skill_tool is None:
                skill_tool = AgentProfileToolModel(
                    profile_id=profile.id,
                    tool_name="skill",
                    enabled=True,
                    requires_approval=True,
                )
                db.add(skill_tool)
            else:
                skill_tool.enabled = True
                if not skill_tool.requires_approval:
                    skill_tool.requires_approval = True

    def create(self, request: AgentProfileCreateRequest, creator: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = AgentProfileModel(
                name=request.name,
                slug=self._unique_slug(db, request.slug or request.name),
                description=request.description,
                system_prompt=request.system_prompt,
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
                profile.response_mode = request.response_mode
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
            db.execute(delete(AgentProfileSkillModel).where(AgentProfileSkillModel.profile_id == profile_id))
            db.execute(delete(AgentProfileToolModel).where(AgentProfileToolModel.profile_id == profile_id))
            db.delete(profile)
            db.commit()

    def install(self, profile_id: int, user: UserModel) -> dict[str, object]:
        with self.session_factory() as db:
            self.ensure_defaults(db)
            profile = db.get(AgentProfileModel, profile_id)
            if profile is None or not profile.enabled or not profile.listed:
                raise KeyError("Agent profile not found")
            if not profile.is_builtin:
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
            if profile is not None and profile.is_builtin:
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
            if profile is None or not profile.enabled:
                raise PermissionError("Agent profile is not available")
            if user.role != "admin" and not profile.is_builtin:
                installed = db.scalar(
                    select(func.count(UserInstalledAgentModel.id)).where(
                        UserInstalledAgentModel.user_id == user.id,
                        UserInstalledAgentModel.profile_id == profile.id,
                    )
                )
                if not installed:
                    raise PermissionError("Please install this agent before using it")

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
        scripts_dir = root_dir / "scripts"
        script_paths = (
            sorted(path.relative_to(root_dir).as_posix() for path in scripts_dir.rglob("*.py"))
            if scripts_dir.is_dir()
            else []
        )
        return {
            "id": skill.id,
            "name": skill.name,
            "slug": skill.slug,
            "description": skill.description,
            "enabled": skill.enabled,
            "has_python_scripts": bool(script_paths),
            "script_paths": script_paths,
        }


def seed_agent_profiles() -> None:
    with create_db_session() as db:
        AgentProfileService().ensure_defaults(db)
