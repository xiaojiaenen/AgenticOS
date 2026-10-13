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
    ) -> dict[str, Any]:
        """Create a deploy request. Returns the deploy record dict."""
        dist_path = _WEBSITES_DIR / project_slug / "dist"
        if not dist_path.exists():
            raise FileNotFoundError(f"dist/ not found for project '{project_slug}'. Build the project first.")

        with self.session_factory() as db:
            deploy = WebsiteDeployModel(
                session_id=session_id,
                project_slug=project_slug,
                stack=stack,
                target_domain=target_domain,
                status="pending",
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
        """Copy dist/ to nginx serve directory."""
        dist_path = self._resolve_dist_path(deploy)
        if not dist_path.exists():
            raise FileNotFoundError(f"dist/ not found: {dist_path}")

        target_dir = NGINX_SERVE_ROOT / deploy.project_slug
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
        deploy.deploy_url = f"/sites/{deploy.project_slug}/"
        deploy.updated_at = datetime.now(timezone.utc)

        _logger.info(
            "deployed: project=%s → %s",
            deploy.project_slug, target_dir,
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
    def _serialize(deploy: WebsiteDeployModel) -> dict[str, Any]:
        return {
            "id": deploy.id,
            "session_id": deploy.session_id,
            "project_slug": deploy.project_slug,
            "stack": deploy.stack,
            "dist_path": deploy.dist_path,
            "target_domain": deploy.target_domain,
            "deploy_url": deploy.deploy_url,
            "status": deploy.status,
            "requested_by": deploy.requested_by,
            "approved_by": deploy.approved_by,
            "reason": deploy.reason,
            "created_at": deploy.created_at.isoformat() if deploy.created_at else None,
            "updated_at": deploy.updated_at.isoformat() if deploy.updated_at else None,
        }
