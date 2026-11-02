"""Website deploy API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin, require_feature
from app.core.data_path import WEBSITES_DIR as _WEBSITES_DIR, _parse_dir_name
from app.db.models import UserModel
from app.schemas.website import DeployDecisionRequest, DeployRequest
from app.services import audit_service
from app.services.website_deploy_service import WebsiteDeployService

router = APIRouter(prefix="/website", tags=["website"])

_service = WebsiteDeployService()


def _assert_can_deploy_project(project_slug: str, user: UserModel) -> None:
    """项目目录名形如 u<uid>_s<session>_v<N>；非管理员只能部署自己的项目。

    project_slug 由请求方直接提交，不校验归属就能替他人项目发起部署审批。
    顺带挡掉路径穿越（slug 必须是单一目录名）。
    """
    if user.role == "admin":
        return
    parsed = _parse_dir_name(project_slug)
    if parsed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="项目标识不合法，应为 u<用户ID>_s<会话>_v<版本>",
        )
    if parsed[0] != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="没有权限部署他人的网站项目",
        )


@router.post("/deploy")
def request_deploy(
    body: DeployRequest,
    http_request: Request,
    user: UserModel = Depends(require_feature("write", "deploy_website")),
    db: Session = Depends(get_db),
):
    """User requests website deployment.

    鉴权分两层：功能级（这个角色能不能用「部署网站」这个功能）+
    行级（只能部署自己的项目）。前者由策略表决定，后者由目录名归属决定。
    """
    _assert_can_deploy_project(body.project_slug, user)
    deploy = _service.request_deploy(
        session_id=body.session_id,
        project_slug=body.project_slug,
        stack=body.stack,
        requested_by=user.id,
        target_domain=body.target_domain,
    )
    audit_service.record_request(
        db, http_request, action="website.deploy_request", actor=user,
        resource_type="website_deploy",
        resource_id=deploy.get("id") if isinstance(deploy, dict) else None,
        detail={"project_slug": body.project_slug, "stack": body.stack,
                "target_domain": body.target_domain},
    )
    return deploy


@router.get("/deploys")
def list_my_deploys(
    user: UserModel = Depends(get_current_user),
):
    """List deploy requests for the current user."""
    all_deploys = _service.list_all()
    return [d for d in all_deploys if d.get("requested_by") == user.id]


@router.get("/deploy/{deploy_id}")
def get_deploy(
    deploy_id: int,
    user: UserModel = Depends(get_current_user),
):
    """Get a deploy request by ID."""
    deploy = _service.get(deploy_id)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")
    # 检查权限：只能查看自己的部署请求（管理员除外）
    if deploy.get("requested_by") != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行该操作")
    return deploy


@router.get("/deploy/project/{project_slug}")
def get_deploy_by_project(
    project_slug: str,
    user: UserModel = Depends(get_current_user),
):
    """Get the latest deploy for a project."""
    deploy = _service.get_by_project(project_slug)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")
    # 检查权限：只能查看自己项目的部署请求（管理员除外），与 get_deploy 保持一致
    if deploy.get("requested_by") != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="没有权限执行该操作")
    return deploy


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
admin_router = APIRouter(prefix="/admin/website", tags=["admin-website"])


@admin_router.get("/deploys")
def list_pending_deploys(
    admin: UserModel = Depends(require_admin),
):
    """Admin: list all pending deploy requests."""
    return _service.list_pending()


@admin_router.get("/deploys/{deploy_id}/preview")
def preview_deploy(
    deploy_id: int,
    admin: UserModel = Depends(require_admin),
):
    """Admin: 审批前看这个待部署项目长什么样。

    审批不能只看项目名和文件数 —— 管理员需要判断「这是不是该上线的东西」。
    这里返回内联资源后的自包含 HTML（与用户侧预览同一套处理：Vite 产物
    的 /assets/ 引用在 iframe srcdoc 里解析不了，必须内联）。
    """
    deploy = _service.get(deploy_id)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部署申请不存在")

    slug = deploy.get("project_slug") or ""
    dist_dir = _WEBSITES_DIR / slug / "dist"
    index_html = dist_dir / "index.html"
    if not index_html.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该项目的 dist/index.html 不存在，可能尚未构建或已被清理",
        )

    from app.services.agent.artifacts import ArtifactFactory

    raw = index_html.read_text(encoding="utf-8")
    return {
        "deploy_id": deploy_id,
        "project_slug": slug,
        "stack": deploy.get("stack"),
        "preview_html": ArtifactFactory._inline_dist_assets(dist_dir, raw),
        "file_count": len([f for f in dist_dir.rglob("*") if f.is_file()]),
    }


@admin_router.get("/deploys/all")
def list_all_deploys(
    admin: UserModel = Depends(require_admin),
):
    """Admin: list all deploy requests."""
    return _service.list_all()


@admin_router.post("/deploys/{deploy_id}/decision")
def decide_deploy(
    deploy_id: int,
    body: DeployDecisionRequest,
    http_request: Request,
    admin: UserModel = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin: approve or reject a deploy request."""
    deploy = _service.decide(
        deploy_id=deploy_id,
        status=body.status,
        approved_by=admin.id,
        reason=body.reason,
    )
    # 审批是最需要留痕的动作之一：谁批的、批成什么、理由是什么
    audit_service.record_request(
        db, http_request, action="website.deploy_decision", actor=admin,
        resource_type="website_deploy", resource_id=deploy_id,
        result=audit_service.RESULT_ALLOW if body.status == "approved" else audit_service.RESULT_DENY,
        detail={"status": body.status, "reason": body.reason},
    )
    return deploy
