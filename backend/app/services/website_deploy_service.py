"""Website deploy service — handle deploy requests, admin approval, and nginx deployment."""

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.db.models import WebsiteDeployModel
from app.db.session import create_db_session

_logger = logging.getLogger("website_deploy")

from app.core.data_path import WEBSITES_DIR, NGINX_SERVE_DIR

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_WEBSITES_DIR = WEBSITES_DIR
NGINX_SERVE_ROOT = NGINX_SERVE_DIR


class WebsiteDeployService:
    def __init__(self, session_factory=create_db_session) -> None:
        self.session_factory = session_factory

    def request_deploy(
        self,
        session_id: str,
        project_slug: str,
        stack: str,
        requested_by: int,
        target_domain: str | None = None,
        visibility: str = "private",
    ) -> dict[str, Any]:
        """Create a deploy request. Returns the deploy record dict.

        ``visibility``：public = 审批通过后发布到 /sites/ 对外可见；
        private = 仅部署者（和管理员）在作品库可见，走带签名的私有端点。
        保守默认 private —— 没明确说要公开的东西不该被公开。
        """
        if visibility not in ("public", "private"):
            raise ValueError("visibility 必须是 public 或 private")
        # 纵深防御：slug 必须是单一目录名，挡掉 ../ 之类的路径穿越
        if (
            not project_slug
            or Path(project_slug).name != project_slug
            or project_slug in {".", ".."}
        ):
            raise ValueError(f"非法的项目标识: {project_slug}")

        dist_path = _WEBSITES_DIR / project_slug / "dist"
        if not dist_path.exists():
            raise FileNotFoundError(f"dist/ not found for project '{project_slug}'. Build the project first.")

        with self.session_factory() as db:
            # 幂等：同一会话 + 同一项目已有 pending 请求时复用，不重复建单。
            # 用户反复点「部署」或在对话里多次说"部署"时，之前每次都会插一条
            # 新的 pending 记录 —— 管理后台审批队列里堆出一串重复项，管理员
            # 点完一个又来一个，以为系统在反复提交。
            existing = db.scalars(
                select(WebsiteDeployModel)
                .where(
                    WebsiteDeployModel.session_id == session_id,
                    WebsiteDeployModel.project_slug == project_slug,
                    WebsiteDeployModel.status == "pending",
                )
                .order_by(WebsiteDeployModel.created_at.desc())
            ).first()
            # 幂等升级：pending 记录存在但可见性变了 → 就地更新（用户改主意
            # 从公开转私密或反之），而不是复用旧的可见性让用户困惑
            if existing is not None:
                if existing.visibility != visibility:
                    existing.visibility = visibility
                    db.commit()
                    db.refresh(existing)
                _logger.info(
                    "deploy request reused: id=%s slug=%s session=%s visibility=%s",
                    existing.id, project_slug, session_id, visibility,
                )
                return self._serialize(existing)

            deploy = WebsiteDeployModel(
                session_id=session_id,
                project_slug=project_slug,
                stack=stack,
                target_domain=target_domain,
                status="pending",
                visibility=visibility,
                requested_by=requested_by,
                # 落库相对路径：机器或容器换目录后，审批阶段仍能找到 dist/
                dist_path=str(Path(project_slug) / "dist"),
            )
            db.add(deploy)
            db.commit()
            db.refresh(deploy)
            return self._serialize(deploy)

    def list_pending(self) -> list[dict[str, Any]]:
        """List all pending deploy requests (for admin review)."""
        with self.session_factory() as db:
            rows = db.scalars(
                select(WebsiteDeployModel)
                .where(WebsiteDeployModel.status == "pending")
                .order_by(WebsiteDeployModel.created_at.desc())
            ).all()
            return [self._serialize(r) for r in rows]

    def list_all(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all deploy requests."""
        with self.session_factory() as db:
            rows = db.scalars(
                select(WebsiteDeployModel)
                .order_by(WebsiteDeployModel.created_at.desc())
                .limit(limit)
            ).all()
            return [self._serialize(r) for r in rows]

    def decide(self, deploy_id: int, status: str, approved_by: int, reason: str | None = None) -> dict[str, Any]:
        """Admin approves or rejects a deploy request."""
        if status not in ("approved", "rejected"):
            raise ValueError("status must be 'approved' or 'rejected'")

        with self.session_factory() as db:
            deploy = db.get(WebsiteDeployModel, deploy_id)
            if deploy is None:
                raise LookupError(f"Deploy {deploy_id} not found")
            if deploy.status != "pending":
                raise ValueError(f"部署申请 {deploy_id} 当前状态为 {deploy.status}，无法重复处理")

            deploy.status = status
            deploy.approved_by = approved_by
            deploy.reason = reason
            deploy.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(deploy)

            if status == "approved":
                try:
                    self._execute_deploy(deploy)
                    # _execute_deploy mutates status/deploy_url in memory; persist it
                    db.commit()
                    db.refresh(deploy)
                except Exception:
                    _logger.exception("Deploy execution failed: id=%s", deploy_id)
                    deploy.status = "failed"
                    deploy.reason = (deploy.reason or "") + "; deploy execution failed"
                    deploy.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    db.refresh(deploy)

            return self._serialize(deploy)

    def get(self, deploy_id: int) -> dict[str, Any] | None:
        with self.session_factory() as db:
            deploy = db.get(WebsiteDeployModel, deploy_id)
            if deploy is None:
                return None
            return self._serialize(deploy)

    def get_by_project(self, project_slug: str) -> dict[str, Any] | None:
        with self.session_factory() as db:
            deploy = db.scalar(
                select(WebsiteDeployModel)
                .where(WebsiteDeployModel.project_slug == project_slug)
                .order_by(WebsiteDeployModel.created_at.desc())
                .limit(1)
            )
            if deploy is None:
                return None
            return self._serialize(deploy)

    def _resolve_dist_path(self, deploy: WebsiteDeployModel) -> Path:
        """把库里存的 dist 路径还原成本机的绝对路径。

        新数据以 data/websites/ 相对路径落库：仓库换目录、容器重建或
        AGENT_DATA_DIR 变化后，绝对路径会在审批的拷贝阶段才炸。
        历史数据仍是绝对路径 —— 原样能用就用，不能用就按 <slug>/dist 重新定位。
        """
        raw = Path(deploy.dist_path)
        if not raw.is_absolute():
            return _WEBSITES_DIR / raw
        if raw.exists():
            return raw
        return _WEBSITES_DIR / deploy.project_slug / "dist"

    def _execute_deploy(self, deploy: WebsiteDeployModel) -> None:
        """发布：public → nginx /sites/（公开路径）；private → 私有目录。

        私密站点**绝不**落到公开的 /sites/ —— 那会让「私密」形同虚设。
        私密站点放在独立目录，访问走后端带签名的私有端点。
        """
        dist_path = self._resolve_dist_path(deploy)
        if not dist_path.exists():
            raise FileNotFoundError(f"dist/ not found: {dist_path}")

        is_public = (deploy.visibility or "private") == "public"
        if is_public:
            target_dir = NGINX_SERVE_ROOT / deploy.project_slug
            deploy.deploy_url = f"/sites/{deploy.project_slug}/"
        else:
            target_dir = NGINX_SERVE_ROOT / "_private" / deploy.project_slug
            # nginx 配置必须显式 deny /sites/_private/（见 nginx.conf 注释）；
            # 访问统一走后端 /website/site/ 端点（带 30 天签名）
            deploy.deploy_url = f"/api/v1/website/site/{deploy.project_slug}/"

        target_dir.mkdir(parents=True, exist_ok=True)

        # Remove old files
        for item in target_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy new files
        for item in dist_path.iterdir():
            dest = target_dir / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)

        deploy.status = "deployed"
        deploy.updated_at = datetime.now(timezone.utc)

        # 私密站点：部署完成即签发 30 天访问令牌（作品库可随时重置）
        if not is_public:
            deploy.access_token = self._issue_access_token(deploy)

        _logger.info(
            "deployed: project=%s visibility=%s → %s",
            deploy.project_slug, deploy.visibility, target_dir,
        )

        # Try nginx reload (non-fatal if it fails — nginx may not be running in dev)
        try:
            result = subprocess.run(
                ["nginx", "-t"], capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                subprocess.run(
                    ["nginx", "-s", "reload"], capture_output=True, timeout=10,
                )
                _logger.info("nginx reloaded successfully")
        except Exception:
            _logger.warning("nginx reload skipped (nginx may not be running)")

    @staticmethod
    def _issue_access_token(deploy: WebsiteDeployModel, *, days: int = 30) -> str:
        """为私密站点签发长期访问令牌（作品库里可随时重置）。"""
        import time as _time

        from app.core.config import get_settings
        from app.core.security import create_access_token

        settings = get_settings()
        return create_access_token(
            {"sub": str(deploy.requested_by or 0), "scope": "website_private",
             "slug": deploy.project_slug, "deploy_id": deploy.id,
             "iat": int(_time.time())},
            secret=settings.auth_secret_key,
            expires_in_seconds=days * 86400,
        )

    def reset_access_token(self, deploy_id: int, requested_by: int, is_admin: bool) -> dict[str, Any] | None:
        """重置私密站点的访问令牌（旧链接立即失效）。仅部署者或管理员。"""
        with self.session_factory() as db:
            deploy = db.get(WebsiteDeployModel, deploy_id)
            if deploy is None:
                return None
            if deploy.requested_by != requested_by and not is_admin:
                raise PermissionError("只有部署者或管理员可以重置访问链接")
            token = self._issue_access_token(deploy)
            deploy.access_token = token
            db.commit()
            return {"id": deploy.id, "access_url": f"/api/v1/website/site/{deploy.project_slug}/?t={token}"}

    def list_gallery(self, viewer_id: int, is_admin: bool = False) -> list[dict[str, Any]]:
        """作品库：deployed 状态的网站。

        - public：所有人可见（deploy_url 直接指向 /sites/ 公开路径）；
        - private：仅部署者（和管理员）可见，附当前有效的访问链接。
        """
        with self.session_factory() as db:
            rows = db.scalars(
                select(WebsiteDeployModel)
                .where(WebsiteDeployModel.status == "deployed")
                .order_by(WebsiteDeployModel.updated_at.desc())
                .limit(200)
            ).all()

        items: list[dict[str, Any]] = []
        for row in rows:
            visibility = row.visibility or "private"
            is_owner = row.requested_by == viewer_id
            if visibility == "private" and not (is_owner or is_admin):
                continue
            item = self._serialize(row)
            if visibility == "private":
                # 令牌过期/丢失时现场补签（30 天滚动）
                token = row.access_token or self._issue_access_token(row)
                if token != row.access_token:
                    with self.session_factory() as db2:
                        r2 = db2.get(WebsiteDeployModel, row.id)
                        r2.access_token = token
                        db2.commit()
                item["access_url"] = f"/api/v1/website/site/{row.project_slug}/?t={token}"
            items.append(item)
        return items

    @staticmethod
    def _serialize(deploy: WebsiteDeployModel) -> dict[str, Any]:
        return {
            "id": deploy.id,
            "session_id": deploy.session_id,
            "project_slug": deploy.project_slug,
            "stack": deploy.stack,
            "dist_path": deploy.dist_path,
            "target_domain": deploy.target_domain,
            "deploy_url": deploy.deploy_url,
            "visibility": deploy.visibility or "private",
            "status": deploy.status,
            "requested_by": deploy.requested_by,
            "approved_by": deploy.approved_by,
            "reason": deploy.reason,
            "created_at": deploy.created_at.isoformat() if deploy.created_at else None,
            "updated_at": deploy.updated_at.isoformat() if deploy.updated_at else None,
        }
