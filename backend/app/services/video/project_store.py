"""
项目持久化存储
完整对标 html-video 原版 ProjectStore
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .types import Project, ProjectStatus
from .errors import HtmlVideoError, ErrorCode


class ProjectStore:
    """JSON 文件持久化: {project_root}/.html-video/projects/{id}/project.json"""

    def __init__(self, project_root: str):
        self._project_root = Path(project_root)
        self._projects_dir = self._project_root / ".html-video" / "projects"

    async def ensure_dir(self, project_id: str) -> str:
        """确保项目目录和 assets/ 子目录存在，返回绝对路径"""
        project_dir = self._projects_dir / project_id
        assets_dir = project_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        return str(project_dir)

    async def save(self, project: Project) -> None:
        """写入 project.json，自动更新 updated_at"""
        project_dir = await self.ensure_dir(project.id)
        project.updated_at = datetime.now(timezone.utc).isoformat()

        project_file = Path(project_dir) / "project.json"
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project.model_dump(by_alias=True), f, indent=2, ensure_ascii=False)

    async def load(self, project_id: str) -> Project:
        """加载项目，不存在抛出 HtmlVideoError"""
        project_file = self._projects_dir / project_id / "project.json"
        if not project_file.exists():
            raise HtmlVideoError(
                code=ErrorCode.PROJECT_NOT_FOUND,
                message=f"Project not found: {project_id}",
                context={"project_id": project_id},
            )

        with open(project_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return Project(**data)

    async def list_all(self) -> list[Project]:
        """列出所有项目，按 updated_at 降序"""
        projects: list[Project] = []

        if not self._projects_dir.exists():
            return projects

        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            project_file = project_dir / "project.json"
            if not project_file.exists():
                continue

            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                projects.append(Project(**data))
            except Exception:
                continue

        # 按 updated_at 降序排序
        projects.sort(key=lambda p: p.updated_at or "", reverse=True)
        return projects

    async def remove(self, project_id: str) -> None:
        """删除项目目录"""
        project_dir = self._projects_dir / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
