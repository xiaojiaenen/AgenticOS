from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.tool_config import ModeToolConfigUpdateRequest, ToolConfigResponse
from app.services import audit_service
from app.services.agent_service import get_agent_service
from app.services.tool_config_service import ToolConfigService

router = APIRouter(prefix="/tool-config", tags=["Tool Config"])


@router.get("", response_model=ToolConfigResponse)
def get_tool_config(_: UserModel = Depends(require_admin)) -> dict[str, object]:
    return ToolConfigService().list_configs()


@router.get("/catalog/labels")
def get_tool_labels(_: UserModel = Depends(get_current_user)) -> dict[str, str]:
    """工具名 → 中文标签。

    对话页的工具块只能拿到内部工具名（``write_text_file``、``calc``），
    直接展示给用户等于暴露实现细节。这里一次性把目录里的 label 发下去，
    前端缓存后本地翻译，不必为每个工具块再查一次目录。
    """
    from app.services.tool_config_service import TOOL_CATALOG

    return {name: str(item.get("label") or name) for name, item in TOOL_CATALOG.items()}


@router.put("/modes/{mode}", response_model=ToolConfigResponse)
def update_mode_tool_config(
    mode: str,
    payload: ModeToolConfigUpdateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    try:
        result = ToolConfigService().update_mode(mode, [item.model_dump() for item in payload.tools])
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    get_agent_service().clear_agent_cache()
    # 工具开关直接影响智能体能做哪些危险操作，必须留痕
    audit_service.record_request(
        db, http_request, action="tool_config.update", actor=current_user,
        resource_type="tool_config", resource_id=mode,
        detail={"mode": mode, "tools": [
            {"name": item.get("name"), "enabled": item.get("enabled")}
            for item in (payload.model_dump().get("tools") or [])
        ]},
    )
    return result


# ---------------------------------------------------------------------------
# 用户自建智能体的工具/Skill 限制（管理员平台级收口）
# ---------------------------------------------------------------------------


@router.get("/policy")
def get_agent_tool_policy(
    db: Session = Depends(get_db),
    _: UserModel = Depends(require_admin),
) -> dict[str, object]:
    """当前生效的限制名单 + 全部可选工具（后台勾选界面用）。

    `restricted_tools` 里的工具**只对管理员拥有的智能体与平台内置可用**；
    普通用户自建的智能体即使勾上也拿不到。
    """
    from app.services import agent_tool_policy
    from app.services.tool_config_service import TOOL_CATALOG

    policy = agent_tool_policy.load_policy(db)
    return {
        "restricted_tools": sorted(policy.restricted_tools),
        "restricted_skills": sorted(policy.restricted_skills),
        "default_restricted_tools": sorted(agent_tool_policy.DEFAULT_RESTRICTED_TOOLS),
        # 供前端渲染可勾选清单（工具名 + 中文名）
        "available_tools": [
            {"name": name, "label": str(item.get("label") or name)}
            for name, item in sorted(TOOL_CATALOG.items())
        ],
        # 可选 Skill 清单（受限名单是按 slug 匹配的，前端要能看到有哪些）
        "available_skills": _available_skills_for_policy(db),
    }


def _available_skills_for_policy(db: Session) -> list[dict[str, object]]:
    """全部 Skill 的 slug + 名称（含停用的，方便管理员统一设策略）。"""
    try:
        from app.db.models import SkillModel

        rows = db.scalars(select(SkillModel).order_by(SkillModel.name.asc())).all()
        return [
            {
                "slug": row.slug,
                "name": row.name,
                "enabled": bool(getattr(row, "enabled", True)),
            }
            for row in rows
        ]
    except Exception:  # noqa: BLE001 —— 读不到技能表时给出空清单，不阻断页面
        return []


@router.put("/policy")
def update_agent_tool_policy(
    payload: dict,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(require_admin),
) -> dict[str, object]:
    """保存限制名单。

    只接受两个可选字段：`restricted_tools` / `restricted_skills`（字符串数组）。
    未传的字段保持不变。
    """
    from app.services import agent_tool_policy

    tools = payload.get("restricted_tools")
    skills = payload.get("restricted_skills")
    for value, name in ((tools, "restricted_tools"), (skills, "restricted_skills")):
        if value is not None and not (
            isinstance(value, list) and all(isinstance(x, str) for x in value)
        ):
            raise HTTPException(status_code=400, detail=f"{name} 必须是字符串数组")
    try:
        policy = agent_tool_policy.save_policy(
            db, restricted_tools=tools, restricted_skills=skills
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 策略立刻生效：缓存的 Agent 里嵌着旧的白名单
    get_agent_service().clear_agent_cache()
    audit_service.record_request(
        db, http_request, action="tool_policy.update", actor=current_user,
        resource_type="tool_policy", resource_id="agent_tool_policy",
        detail={
            "restricted_tools": sorted(policy.restricted_tools),
            "restricted_skills": sorted(policy.restricted_skills),
        },
    )
    return {
        "restricted_tools": sorted(policy.restricted_tools),
        "restricted_skills": sorted(policy.restricted_skills),
    }
