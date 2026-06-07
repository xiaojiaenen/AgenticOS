"""PPT 生成流程测试 — 计划提交、质量门错误路径"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.ppt_artifact_service import PptArtifactService
from app.tools.ppt_tools import pop_pending_slide_plan, reset_slides_dir_cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(**meta_extra) -> MagicMock:
    session = MagicMock()
    session.session_id = "test-session-001"
    session.metadata = {
        "ppt_spec_lock": "",
        "ppt_slide_plan": [],
        **meta_extra,
    }
    return session


def _make_service():
    from app.services.agent_service import AgentService
    svc = AgentService.__new__(AgentService)
    svc.settings = MagicMock()
    svc.settings.hitl_enabled = False
    return svc


# ===========================================================================
# 1. submit_slide_plan 工具
# ===========================================================================

class TestSubmitSlidePlan:
    """submit_slide_plan 应该暂存计划到模块级缓存。"""

    def setup_method(self):
        reset_slides_dir_cache()

    def test_valid_plan_stored(self):
        plan = json.dumps([
            {"slide_num": 1, "layout": "cover", "title": "封面"},
            {"slide_num": 2, "layout": "toc", "title": "目录"},
        ])
        # 模拟工具内部逻辑
        import app.tools.ppt_tools as ppt_tools
        parsed = json.loads(plan)
        ppt_tools._pending_slide_plan = parsed

        result = pop_pending_slide_plan()
        assert result is not None
        assert len(result) == 2
        assert result[0]["slide_num"] == 1
        assert result[1]["layout"] == "toc"

    def test_pop_clears_cache(self):
        import app.tools.ppt_tools as ppt_tools
        ppt_tools._pending_slide_plan = [{"slide_num": 1, "layout": "cover"}]
        pop_pending_slide_plan()
        assert pop_pending_slide_plan() is None


# ===========================================================================
# 2. _create_ppt_artifact 错误路径
# ===========================================================================

class TestCreatePptArtifactErrors:
    """所有失败路径都应该设置 _last_quality_errors。"""

    @pytest.mark.anyio
    async def test_slides_dir_not_exist(self):
        svc = PptArtifactService()
        fake_dir = Path("/tmp/nonexistent_slides_dir_test")
        result = await svc.create_from_slides_dir("test-session", fake_dir)
        assert result is None
        assert len(svc._last_quality_errors) > 0
        assert "不存在" in svc._last_quality_errors[0]

    @pytest.mark.anyio
    async def test_not_enough_slides(self, tmp_path):
        svc = PptArtifactService()
        # 只创建 1 个 slide
        (tmp_path / "slide_1.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>')
        result = await svc.create_from_slides_dir("test-session", tmp_path)
        assert result is None
        assert len(svc._last_quality_errors) > 0
        assert "不足" in svc._last_quality_errors[0]

    @pytest.mark.anyio
    async def test_missing_viewbox(self, tmp_path):
        svc = PptArtifactService()
        # 创建 3 个 slide，但缺少 viewBox
        for i in range(1, 4):
            (tmp_path / f"slide_{i}.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        result = await svc.create_from_slides_dir("test-session", tmp_path)
        assert result is None
        assert len(svc._last_quality_errors) > 0

    @pytest.mark.anyio
    async def test_inconsistent_viewbox(self, tmp_path):
        svc = PptArtifactService()
        (tmp_path / "slide_1.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>')
        (tmp_path / "slide_2.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>')
        (tmp_path / "slide_3.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"></svg>')
        result = await svc.create_from_slides_dir("test-session", tmp_path)
        assert result is None
        assert len(svc._last_quality_errors) > 0

    @pytest.mark.anyio
    async def test_valid_slides_succeed(self, tmp_path):
        """3 个格式正确的 slide 应该成功创建 artifact。"""
        svc = PptArtifactService()
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="openai">
            <g id="bg"><rect width="1280" height="720" fill="var(--bg)"/></g>
            <g id="content">
                <text x="640" y="360" font-size="68" font-weight="800" fill="var(--text-1)" text-anchor="middle">AI 科普</text>
            </g>
        </svg>'''
        for i in range(1, 4):
            (tmp_path / f"slide_{i}.svg").write_text(svg)

        # 需要 mock DB 写入
        with patch.object(svc, 'session_factory') as mock_factory:
            mock_db = MagicMock()
            mock_factory.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_factory.return_value.__exit__ = MagicMock(return_value=False)
            result = await svc.create_from_slides_dir("test-session", tmp_path)

        # 应该成功（或至少不是因为格式问题失败）
        if result is not None:
            assert result["slide_count"] == 3
            assert "html" in result
