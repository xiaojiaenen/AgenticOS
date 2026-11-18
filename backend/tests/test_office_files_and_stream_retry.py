"""办公助手文件工具失败 + Skill 可见性 + 流中断重试。

四个用户报障的回归锚点：

1. **file_to_md / run_python_script 失败** —— 上传响应的 rel_path 没被前端
   透传，注入提示词回退成容器绝对路径 `/app/data/uploads/...`，作用域文件
   工具的 workspace 校验直接拒绝（"路径必须位于 workspace 内"）。
   测试锁住「前端类型与发送载荷必须带 rel_path」与「wuwei 解析器对绝对路径
   必然拒绝」（后者证明这个链路断了的话症状就是用户看到的）。

2. **提示词泄露容器路径** —— 同一根因：rel_path 缺失时 orchestrator 的
   注入模板回退 file_path。rel_path 一到，注入的就是 uploads/xxx 相对路径。

3. **受限 Skill 在商店新建时仍可见** —— 工具过滤做了，Skill 漏了：
   `_list_available_skills` 从不查策略。已补。
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
"""仓库根（测试 cwd 在 backend/，前端与 deploy 都在它下面）。"""


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


class TestRelPathPropagation:
    def test_uploadedfile_type_has_rel_path(self):
        """前端类型必须带 rel_path —— 丢了它整条链路就断在第一环。"""
        src = _read("frontend/src/services/fileService.ts")
        assert "rel_path" in src, "UploadedFile 类型缺 rel_path 字段"

    def test_send_payload_includes_rel_path(self):
        """发送载荷（agentService）与上传准备（useChatStream）都要透传。"""
        svc = _read("frontend/src/services/agentService.ts")
        hook = _read("frontend/src/hooks/useChatStream.ts")
        assert "rel_path" in svc, "agentService 的 files 载荷没有 rel_path"
        assert "rel_path" in hook, "useChatStream.prepareUploadedFiles 没透传 rel_path"

    def test_backend_schema_accepts_rel_path(self):
        """后端 schema 本来就有 rel_path —— 防止有人"清理"掉它。"""
        src = _read("backend/app/schemas/agent.py")
        assert "rel_path" in src

    def test_wuwei_resolver_rejects_absolute_outside_workspace(self, tmp_path: Path):
        """wuwei 的解析器对 workspace 外的绝对路径必然拒绝。

        这就是用户看到的 file_to_md 失败的直接机制（不是猜测）。
        """
        from wuwei.plugin.builtin.file import _resolve_workspace_path

        with pytest.raises(ValueError, match="workspace"):
            _resolve_workspace_path("/app/data/uploads/1/x.xls", workspace=str(tmp_path))

    def test_relative_upload_path_resolves(self, tmp_path: Path):
        """相对路径（uploads/x.xls）能正常解析 —— 修复后模型拿到的形态。"""
        from wuwei.plugin.builtin.file import _resolve_workspace_path

        ws = tmp_path
        (ws / "uploads").mkdir()
        (ws / "uploads" / "x.xls").write_bytes(b"PK")
        resolved = _resolve_workspace_path("uploads/x.xls", workspace=str(ws))
        assert resolved.is_file()

    def test_orchestrator_prefers_rel_path(self):
        """注入模板在 rel_path 存在时必须优先用它（不再暴露容器路径）。"""
        src = _read("backend/app/services/agent/orchestrator.py")
        assert 'getattr(f, "rel_path", None) or f.file_path' in src, (
            "注入模板没有优先使用 rel_path"
        )


class TestSkillVisibility:
    def test_list_available_skills_supports_hidden(self):
        """_list_available_skills 必须支持 hidden_slugs 过滤。"""
        src = _read("backend/app/services/agent_profile_service.py")
        assert "hidden_slugs" in src
        assert "hidden_slugs=hidden_skill_slugs" in src, (
            "list_store / list_user_agents 没有把受限 Skill 传给清单构建"
        )

    def test_skill_save_guarded(self):
        """保存 Skill 绑定也要拦普通用户（与工具对称，防直接调 API）。"""
        src = _read("backend/app/services/agent_profile_service.py")
        idx = src.index("def _apply_skill_ids")
        block = src[idx : idx + 1200]
        assert "is_admin_like" in block, "_apply_skill_ids 没有角色检查"
        assert "PermissionError" in block


class TestStreamEndedRetryable:
    def test_stream_ended_classified_as_connection_error(self):
        """流中断（无终止事件）必须被分类为可重试的连接错误。

        用户报障：生成网站报 ValueError: Model stream ended without a
        terminal event。原分类是 unknown → 不重试 → 直接抛给用户。
        """
        from app.services.llm_providers.adapter import RetryingGateway

        for message in (
            "Model stream ended without a terminal event",
            "Model stream produced no events: the endpoint likely ignored "
            "Accept: text/event-stream",
        ):
            kind = RetryingGateway._classify_error(ValueError(message))
            assert kind == "connection_error", f"{message[:40]}... 分类为 {kind}"

    def test_normal_errors_unaffected(self):
        from app.services.llm_providers.adapter import RetryingGateway

        # 无关错误不该被这个新分支误伤
        assert RetryingGateway._classify_error(ValueError("bad request")) not in {
            "connection_error",
        } or "connection" in str(ValueError("bad request")).lower()
