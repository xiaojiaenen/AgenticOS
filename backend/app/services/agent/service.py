"""AgentService 门面：组合 factory / orchestrator / artifacts / prompts。

拆分自原单文件 ``app/services/agent_service.py``（TECH-DEBT-2026-09）：
- factory.AgentFactory      —— Agent/中间件栈/工具注册表构建 + 并发补丁
- orchestrator.StreamOrchestrator —— stream_chat SSE 编排主循环
- artifacts.ArtifactFactory —— PPT/website 工件与 PPTX 导出
- prompts                   —— PPT/website 目录注入文案（资源文件）

组合方式为 Mixin 继承：AgentService(Factory, Orchestrator, ArtifactFactory)，
各模块方法整段搬移、通过 self 访问宿主状态，保证公共 API 与行为零变更。
"""

from typing import Any

import asyncio

from cachetools import TTLCache
from wuwei import Agent

from app.core.config import Settings, get_settings
from app.db.models import ApprovalModel, PptArtifactModel, UserModel
from sqlalchemy import select

from app.db.session import create_db_session
from app.schemas.agent import AgentStreamRequest
from app.services.agent import prompts
from app.services.agent.artifacts import ArtifactFactory
from app.services.agent.factory import AgentFactory
from app.services.agent.orchestrator import StreamOrchestrator
from app.services.agent_profile_service import AgentProfileService, RuntimeAgentProfile
from app.services.approval_manager import ApprovalManager
from app.services.external_system_service import UserInputBlocker
from app.services.ppt_artifact_service import PptArtifactService
from app.services.session_storage import DatabaseAgentStorage
from app.services.tool_config_service import ToolConfigService


class AgentService(AgentFactory, StreamOrchestrator, ArtifactFactory):
    """智能体服务门面：保持原 agent_service.py 的全部公共 API。"""

    # PPT/website 目录注入（staticmethod，实现在 prompts 模块，文案在资源文件中）
    _inject_design_catalog = staticmethod(prompts.inject_design_catalog)
    _scan_website_catalog = staticmethod(prompts.scan_website_catalog)
    _inject_website_catalog = staticmethod(prompts.inject_website_catalog)

    def __init__(
        self,
        settings: Settings,
        storage: DatabaseAgentStorage | None = None,
        approval_manager: ApprovalManager | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or DatabaseAgentStorage()
        self.approval_manager = approval_manager or ApprovalManager(
            timeout_seconds=settings.hitl_timeout_seconds
        )
        self.ppt_artifacts = PptArtifactService()
        self.agent_profiles = AgentProfileService()
        self.tool_configs = ToolConfigService()
        # LRU 缓存：最多 50 个 Agent，1 小时过期
        self._agents: TTLCache[tuple, Agent] = TTLCache(maxsize=50, ttl=3600)
        self._cached_display_name_map: dict[str, str] | None = None

    def _get_display_name_map(self) -> dict[str, str]:
        if self._cached_display_name_map is None:
            self._cached_display_name_map = self.tool_configs.build_display_name_map()
        return self._cached_display_name_map

    def ensure_ready(self) -> None:
        self._ensure_llm_configured()

    def clear_agent_cache(self) -> None:
        self._agents.clear()

    def _runtime_from_mode(self, response_mode: str, system_prompt: str | None = None) -> RuntimeAgentProfile:
        profile = self.tool_configs.get_runtime_profile(response_mode)
        return RuntimeAgentProfile(
            profile_id=None,
            name=response_mode,
            slug=response_mode,
            response_mode=profile.mode,
            system_prompt=system_prompt or self.settings.agent_system_prompt,
            builtin_tools=profile.builtin_tools,
            approval_tools=profile.approval_tools,
            signature=profile.signature,
            skills=(),
        )

    async def _resolve_runtime_profile(self, request: AgentStreamRequest, user: UserModel | None) -> RuntimeAgentProfile:
        if request.agent_profile_id is not None:
            if user is None:
                raise PermissionError("Agent profile requires an authenticated user")
            return await asyncio.to_thread(
                self.agent_profiles.resolve_runtime,
                request.agent_profile_id,
                user,
                approval_mode=request.approval_mode,
                plan_mode=request.plan_mode,
            )
        if user is not None:
            from app.services.approval_policy import normalize_approval_mode

            return await asyncio.to_thread(
                self.agent_profiles.resolve_runtime_by_mode,
                request.response_mode,
                user,
                approval_mode=normalize_approval_mode(request.approval_mode),
                plan_mode=request.plan_mode,
            )
        return self._runtime_from_mode(request.response_mode, request.system_prompt)

    async def ensure_profile_access(self, request: AgentStreamRequest, user: UserModel) -> None:
        """对话入口的智能体权限拦截。

        商店里看不到 ≠ 用不了：用户可以手改请求体塞一个 profile_id 进来。
        所以真正动手前必须再查一次授权 —— 不可用的智能体在这里被直接
        403 掉，模型根本不会被唤醒（而不是让它跑一轮再报错）。

        三种越权场景都拦在这：

        - profile_id 指向未授权/未启用/暂不开放的智能体；
        - 不带 profile_id 时按 response_mode 落到内置智能体，而那个内置
          智能体当前不可用（例如"网站工程师"被设为暂不开放）；
        - 会话已绑定某个 profile，但该 profile 后来被收回权限。
        """
        if user is None:
            return

        def _check() -> None:
            from app.db.models import AgentProfileModel

            with create_db_session() as db:
                profile_id = request.agent_profile_id
                if profile_id is None:
                    # 未指定 profile：按模式找内置；找不到/不可用一律拒绝
                    # （不能悄悄退回 general —— 那等于让被禁用的智能体
                    #   以"通用助手"的身份继续跑）。
                    profile = db.scalar(
                        select(AgentProfileModel).where(
                            AgentProfileModel.slug == request.response_mode,
                            AgentProfileModel.is_builtin.is_(True),
                        )
                    )
                    if profile is None:
                        # 没有该模式的内置智能体（例如 video 模式已下线）：
                        # 允许按普通模式跑，不做拦截。
                        return
                else:
                    profile = db.get(AgentProfileModel, profile_id)
                    if profile is None:
                        raise PermissionError("智能体不存在或已被删除。")

                service = self.agent_profiles
                if not service._is_profile_available_to_user(db, profile, user):
                    raise PermissionError(
                        f"你没有使用「{profile.name}」的权限，请联系管理员开通。"
                    )

        await asyncio.to_thread(_check)

    async def ensure_session_access(self, request: AgentStreamRequest, user: UserModel) -> None:
        if not request.session_id:
            return
        owner_id = await self.storage.get_owner_id(request.session_id)
        if owner_id is not None:
            if owner_id != user.id and user.role != "admin":
                raise PermissionError("当前用户无权访问该会话。")
        else:
            # Session is unowned — allow access but verify it's empty or new.
            # If the session already has messages with a different user context,
            # it's likely a stale unowned session, deny access.
            msg_count = await self.storage.get_message_count(request.session_id)
            if msg_count > 0 and user.role != "admin":
                raise PermissionError("会话未绑定用户且已有消息记录，当前用户无权访问。")

    async def _ensure_record_owner(
        self,
        record_id: str,
        model_type: type[ApprovalModel | PptArtifactModel],
        user: UserModel,
    ) -> None:
        def _run():
            with create_db_session() as db:
                row = db.get(model_type, record_id)
                if row is None:
                    return None
                return row.session_id
        session_id = await asyncio.to_thread(_run)
        if not session_id:
            return
        owner_id = await self.storage.get_owner_id(session_id)
        if owner_id is not None and owner_id != user.id and user.role != "admin":
            raise PermissionError("当前用户无权访问此资源。")
        # Reject access when session owner is unset but the artifact exists
        if owner_id is None and user.role != "admin":
            raise PermissionError("资源所属会话未绑定用户，当前用户无权访问。")

    async def decide_approval(
        self,
        approval_id: str,
        *,
        status: str,
        reason: str | None = None,
        modified_arguments: dict[str, Any] | None = None,
        current_user: UserModel | None = None,
    ) -> dict[str, Any]:
        if current_user is not None:
            await self._ensure_record_owner(approval_id, ApprovalModel, current_user)
        return await self.approval_manager.decide(
            approval_id, status=status, reason=reason,
            modified_arguments=modified_arguments,
        )

    async def get_session_state(self, session_id: str) -> dict[str, Any]:
        stored = await self.storage.describe(session_id)
        if stored is None:
            stored = {"session_id": session_id, "storage": "sqlalchemy", "message_count": 0}
        stored["pending_approvals"] = await self.approval_manager.get_pending(session_id)
        return stored

    async def get_ppt_artifact(self, artifact_id: str, current_user: UserModel | None = None) -> dict[str, Any] | None:
        if current_user is not None:
            await self._ensure_record_owner(artifact_id, PptArtifactModel, current_user)
        return await self.ppt_artifacts.get(artifact_id)

    async def export_pptx(
        self,
        artifact_id: str,
        *,
        canvas_format: str | None = None,
        theme: str | None = None,
        use_native_shapes: bool = True,
        use_compat_mode: bool = False,
        transition: str | None = None,
        animation: str | None = None,
        enable_notes: bool = True,
        current_user: UserModel | None = None,
    ) -> bytes:
        """Export a PPT artifact as a native .pptx file.

        Converts the SVG pages stored in the artifact into DrawingML shapes
        and assembles a complete PowerPoint file.
        """
        if current_user is not None:
            await self._ensure_record_owner(artifact_id, PptArtifactModel, current_user)

        artifact = await self.ppt_artifacts.get(artifact_id)
        if artifact is None:
            raise FileNotFoundError(f"PPT 产物 {artifact_id} 不存在")

        svgs = self.ppt_artifacts.extract_svgs_from_artifact(artifact)
        if not svgs:
            raise ValueError("产物中没有可导出的幻灯片")

        # 在线程池中执行同步的 PPTX 生成，防止阻塞事件循环
        import asyncio
        return await asyncio.to_thread(
            self._export_pptx_sync,
            artifact_id,
            svgs,
            canvas_format,
            use_native_shapes,
            use_compat_mode,
            transition,
            animation,
            enable_notes,
        )

    async def list_user_sessions(self, user_id: int) -> list[dict[str, Any]]:
        return await self.storage.list_user_sessions(user_id)

    async def delete_session(self, session_id: str, current_user: UserModel) -> None:
        owner_id = await self.storage.get_owner_id(session_id)
        if owner_id is not None and owner_id != current_user.id and current_user.role != "admin":
            raise PermissionError("当前用户无权删除该会话。")
        await self.storage.delete(session_id)

    async def submit_user_input(self, session_id: str, params: dict[str, object], current_user: UserModel) -> dict[str, object]:
        """接收用户为集成接口提交的参数，以系统消息注入上下文并触发重试。

        前端提交的 params 格式：
        {
            "api_name": "search_issues",
            "values": {"assignee": "张三", "jql": "status=open"},
        }
        """
        session = await self.storage.load(session_id)
        if session is None:
            raise ValueError("会话不存在")
        owner_id = await self.storage.get_owner_id(session_id)
        if owner_id is not None and owner_id != current_user.id and current_user.role != "admin":
            raise PermissionError("当前用户无权操作该会话")

        api_name = params.get("api_name", "")
        values = params.get("values", {})
        if not isinstance(values, dict):
            values = {}

        # 解析 Future，让阻塞的 handler 继续执行
        await UserInputBlocker.resolve(session_id, values)

        return {"status": "ok", "session_id": session_id, "api_name": api_name, "values": values}


from app.core.singleton import ThreadSafeSingleton  # noqa: E402

_agent_service_singleton = ThreadSafeSingleton(lambda: AgentService(get_settings()))


def get_agent_service() -> AgentService:
    return _agent_service_singleton.get()


def clear_agent_service_cache() -> None:
    _agent_service_singleton.reset()
