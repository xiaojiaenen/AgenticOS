"""分段执行服务

支持长 PPT 分多个对话生成，通过检查点机制恢复状态。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

from app.core.data_path import PPT_SESSIONS_DIR

_logger = logging.getLogger("ppt.resume")


@dataclass
class Checkpoint:
    """检查点"""
    session_id: str
    slide_num: int
    spec_lock: str
    slide_plan: list[dict]
    completed_slides: list[int]
    timestamp: str
    theme: Optional[str] = None


class ResumeService:
    """分段执行服务"""

    def save_checkpoint(
        self,
        session_id: str,
        slide_num: int,
        spec_lock: str,
        slide_plan: list[dict],
        completed_slides: list[int],
        theme: Optional[str] = None,
    ):
        """保存检查点

        参数:
            session_id: 会话 ID
            slide_num: 当前页码
            spec_lock: 设计参数摘要
            slide_plan: 页面计划
            completed_slides: 已完成的页码列表
            theme: 主题名称
        """
        checkpoint = Checkpoint(
            session_id=session_id,
            slide_num=slide_num,
            spec_lock=spec_lock,
            slide_plan=slide_plan,
            completed_slides=completed_slides,
            timestamp=datetime.now().isoformat(),
            theme=theme,
        )

        # 查找会话目录
        slides_dir = self._find_session_dir(session_id)
        if not slides_dir:
            _logger.warning("Session directory not found for %s", session_id)
            return

        # 保存检查点
        checkpoint_file = slides_dir / "checkpoint.json"
        checkpoint_file.write_text(
            json.dumps(asdict(checkpoint), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _logger.info(
            "Checkpoint saved: session=%s, slide=%d, completed=%s",
            session_id, slide_num, completed_slides,
        )

    def load_checkpoint(self, session_id: str) -> Optional[Checkpoint]:
        """加载检查点

        参数:
            session_id: 会话 ID

        返回:
            检查点，如果不存在则返回 None
        """
        slides_dir = self._find_session_dir(session_id)
        if not slides_dir:
            return None

        checkpoint_file = slides_dir / "checkpoint.json"
        if not checkpoint_file.exists():
            return None

        try:
            data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
            return Checkpoint(**data)
        except Exception as e:
            _logger.warning("Failed to load checkpoint: %s", e)
            return None

    def get_resume_hint(self, session_id: str) -> str:
        """生成恢复提示

        参数:
            session_id: 会话 ID

        返回:
            恢复提示文本
        """
        checkpoint = self.load_checkpoint(session_id)
        if not checkpoint:
            return "未找到检查点，请开始新的 PPT 生成任务。"

        completed = checkpoint.completed_slides
        total = len(checkpoint.slide_plan)
        remaining = [
            s for s in checkpoint.slide_plan
            if s.get("slide_num") not in completed
        ]

        if not remaining:
            return "所有页面已生成完成！"

        lines = [
            f"上次生成进度：{len(completed)}/{total} 页",
            "",
            f"已生成：{', '.join(f'第{n}页' for n in sorted(completed))}",
            f"剩余：{', '.join(f'第{n["slide_num"]}页({n.get("layout", "unknown")})' for n in remaining)}",
            "",
            f"spec_lock 已恢复，可继续生成剩余页面。",
        ]

        return "\n".join(lines)

    def get_next_slide(self, session_id: str) -> Optional[int]:
        """获取下一个需要生成的页码

        参数:
            session_id: 会话 ID

        返回:
            下一个页码，如果全部完成则返回 None
        """
        checkpoint = self.load_checkpoint(session_id)
        if not checkpoint:
            return None

        completed = set(checkpoint.completed_slides)
        for slide in checkpoint.slide_plan:
            slide_num = slide.get("slide_num")
            if slide_num and slide_num not in completed:
                return slide_num

        return None

    def mark_slide_completed(self, session_id: str, slide_num: int):
        """标记页码为已完成

        参数:
            session_id: 会话 ID
            slide_num: 完成的页码
        """
        checkpoint = self.load_checkpoint(session_id)
        if not checkpoint:
            return

        if slide_num not in checkpoint.completed_slides:
            checkpoint.completed_slides.append(slide_num)
            checkpoint.completed_slides.sort()

            # 重新保存
            self.save_checkpoint(
                session_id=session_id,
                slide_num=checkpoint.slide_num,
                spec_lock=checkpoint.spec_lock,
                slide_plan=checkpoint.slide_plan,
                completed_slides=checkpoint.completed_slides,
                theme=checkpoint.theme,
            )

    def clear_checkpoint(self, session_id: str):
        """清除检查点

        参数:
            session_id: 会话 ID
        """
        slides_dir = self._find_session_dir(session_id)
        if not slides_dir:
            return

        checkpoint_file = slides_dir / "checkpoint.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            _logger.info("Checkpoint cleared: session=%s", session_id)

    def _find_session_dir(self, session_id: str) -> Optional[Path]:
        """查找会话目录

        参数:
            session_id: 会话 ID

        返回:
            会话目录路径
        """
        if not PPT_SESSIONS_DIR.exists():
            return None

        # 查找匹配的目录
        for child in sorted(PPT_SESSIONS_DIR.iterdir()):
            if not child.is_dir():
                continue
            # 格式: u<user_id>_s<session_id>_v<N>
            if f"_s{session_id}_" in child.name or child.name.endswith(f"_s{session_id}"):
                return child

        return None


# 全局单例
_resume_service: Optional[ResumeService] = None


def get_resume_service() -> ResumeService:
    """获取分段执行服务单例"""
    global _resume_service
    if _resume_service is None:
        _resume_service = ResumeService()
    return _resume_service
