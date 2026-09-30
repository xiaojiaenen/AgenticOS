"""Website deploy API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_admin
from app.db.models import UserModel
from app.schemas.website import DeployDecisionRequest, DeployRequest
from app.services.website_deploy_service import WebsiteDeployService

router = APIRouter(prefix="/website", tags=["website"])

_service = WebsiteDeployService()


@router.post("/deploy")
def request_deploy(
    body: DeployRequest,
    user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User requests website deployment."""
    deploy = _service.request_deploy(
        session_id=body.session_id,
        project_slug=body.project_slug,
        stack=body.stack,
        requested_by=user.id,
        target_domain=body.target_domain,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deploy request not found")
    # 检查权限：只能查看自己的部署请求（管理员除外）
    if deploy.get("requested_by") != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return deploy


@router.get("/deploy/project/{project_slug}")
def get_deploy_by_project(
    project_slug: str,
    user: UserModel = Depends(get_current_user),
):
    """Get the latest deploy for a project."""
    deploy = _service.get_by_project(project_slug)
    if deploy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deploy request not found")
    # 检查权限：只能查看自己项目的部署请求（管理员除外），与 get_deploy 保持一致
    if deploy.get("requested_by") != user.id and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
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
    admin: UserModel = Depends(require_admin),
):
    """Admin: approve or reject a deploy request."""
    deploy = _service.decide(
        deploy_id=deploy_id,
        status=body.status,
        approved_by=admin.id,
        reason=body.reason,
    )
    return deploy
