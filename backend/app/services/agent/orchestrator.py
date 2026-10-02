"""StreamOrchestrator：stream_chat 的 SSE 编排主循环、事件泵、keepalive、队列 fan-out。

从原 ``app/services/agent_service.py`` 整段搬移（TECH-DEBT-2026-09 拆分）：
- stream_chat 主循环（runtime/approval/user_input/api_approval 四路事件泵 + keepalive）
- 事件映射（_map_agent_event 及 tool payload 构建）
- usage 记录 / 会话消息持久化 / 会话限额归一化

本类为 Mixin：由 ``service.AgentService`` 组合继承，依赖宿主提供的属性
（self.settings / self.storage / self.approval_manager / self.ppt_artifacts /
self._agents / self._get_agent / self._get_display_name_map，以及
factory / artifacts / prompts 模块注入的方法）。

跨模块上下文：``_current_session_id`` contextvar 仍定义在
``app/services/agent_service.py``（兼容层），此处以函数级导入设置，
避免包与兼容层之间的模块级循环导入。
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Any, AsyncIterator

from wuwei import Agent, AgentEvent

from app.core.data_path import (
    restore_website_dir_for_session,
    set_current_session_id as set_data_session_id,
    set_current_user_id,
)
from app.db.models import AgentUsageEventModel, UserModel
from app.schemas.agent import AgentStreamRequest
from app.services.external_system_service import (
    ApprovalBlocker,
    UserInputBlocker,
    set_ext_user_id,
    _current_session_id as ext_session_id_ctx,
)
from app.services.session_storage import dump_json
from app.tools.email_tools import set_current_session_id as set_email_session_id
from app.services.agent.factory import _REJECTED_TOOL_NAME

_logger = logging.getLogger("agent")


class StreamOrchestrator:
    """SSE 流编排器（Mixin，由 AgentService 组合继承）。"""

    def _build_tool_call_payload(self, event: AgentEvent) -> dict[str, Any]:
        # 优先使用事件中的 display_name，否则从 TOOL_CATALOG 查找中文名
        tool_name = event.data.get("tool_name") or ""
        # 拒绝工具显示原始工具名 + "已拒绝"
        if tool_name == _REJECTED_TOOL_NAME:
            original = event.data.get("args", {}).get("original_tool", "") if isinstance(event.data.get("args"), dict) else ""
            display_name = f"{self._get_display_name_map().get(original, original) or '工具'}（已拒绝）"
        else:
            display_name = (
                event.data.get("display_name")
                or self._get_display_name_map().get(tool_name)
                or tool_name
                or "工具调用"
            )
        payload = {
            "id": event.data.get("tool_call_id"),
            "function": {
                "name": display_name,
                "arguments": event.data.get("args") or {},
            },
        }
        for source_key, target_key in (
            ("side_effect", "side_effect"),
            ("requires_approval", "requires_approval"),
        ):
            value = event.data.get(source_key)
            if isinstance(value, bool):
                payload[target_key] = value
        return payload

    def _build_tool_result_payload(
        self,
        event: AgentEvent,
        *,
        status: str,
        result: str | None,
    ) -> dict[str, Any]:
        tool_name = event.data.get("tool_name") or ""
        display_name = (
            event.data.get("display_name")
            or self._get_display_name_map().get(tool_name)
            or tool_name
            or "工具调用"
        )
        payload = {
            "tool_call_id": event.data.get("tool_call_id"),
            "name": display_name,
            "status": status,
            "result": result,
        }
        error_type = event.data.get("error_type")
        if isinstance(error_type, str) and error_type:
            payload["error_type"] = error_type
        payload.update(StreamOrchestrator._extract_tool_output_metadata(result))
        return payload

    @staticmethod
    def _extract_tool_output_metadata(output: str | None) -> dict[str, Any]:
        if not output:
            return {}
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}

        metadata: dict[str, Any] = {}
        error = payload.get("error")
        if isinstance(error, dict):
            error_type = error.get("type")
            if isinstance(error_type, str) and error_type:
                metadata["error_type"] = error_type

        for key in ("tool_executed", "retryable", "instruction"):
            value = payload.get(key)
            if value is not None:
                metadata[key] = value

        attempts = payload.get("attempts")
        if isinstance(attempts, int):
            metadata["attempts"] = attempts

        return metadata

    @staticmethod
    def _status_from_tool_output(output: str | None) -> str:
        if not output:
            return "success"
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            return "success"
        if isinstance(payload, dict) and payload.get("ok") is False:
            return "error"
        return "success"

    async def _load_session_if_needed(self, agent: Agent, request: AgentStreamRequest) -> None:
        if not request.session_id or not hasattr(agent, "_sessions"):
            return
        sessions = getattr(agent, "_sessions")
        if request.session_id in sessions:
            return
        loaded = await self.storage.load(request.session_id)
        if loaded is not None:
            sessions[request.session_id] = loaded

    async def _persist_session_messages(self, session) -> None:
        """Persist session.context messages to DB.
        wuwei AgentSession only stores messages in memory."""
        try:
            context = getattr(session, "context", None)
            if context is None:
                _logger.warning(f"No context found for session {session.session_id}")
                return
            messages = getattr(context, "_messages", [])
            if not messages:
                return
            existing_count = await self.storage.get_message_count(session.session_id)
            if existing_count >= len(messages):
                return
            new_messages = messages[existing_count:]
            count = await self.storage.append_messages_batch(session.session_id, new_messages)
            _logger.info(f"Persisted {count} messages for session {session.session_id}")
        except Exception as e:
            _logger.warning(f"Failed to persist messages for session {session.session_id}: {e}", exc_info=True)

    def _normalize_session_limits(
        self,
        session,
        *,
        response_mode: str,
        requested_max_steps: int | None,
        profile_max_steps: int | None = None,
    ) -> None:
        if requested_max_steps is not None:
            return
        effective = profile_max_steps or self.settings.agent_max_steps
        current_max_steps = getattr(session, "max_steps", self.settings.agent_max_steps)
        if current_max_steps < effective:
            session.max_steps = effective

    def _build_user_message(self, request: AgentStreamRequest) -> str:
        """Build the user message, describing attached files so the Agent can use tools to process them."""
        if not request.files:
            return request.message

        file_descriptions: list[str] = []
        for f in request.files:
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
            if ext in ("pptx", "ppt"):
                hint = f"PPTX 文件，用 convert_pptx_to_svg(file_path=\"{f.file_path}\") 转换为 SVG 后编辑"
            else:
                hint = f"文档文件，用 file_to_md(path=\"{f.file_path}\") 读取内容"
            file_descriptions.append(f"- **{f.filename}** → 路径 `{f.file_path}` → {hint}")

        return (
            "## 📎 用户上传了以下文件\n\n"
            + "\n".join(file_descriptions)
            + f"\n\n---\n\n{request.message}"
        )

    def _session_payload(self, session) -> dict[str, Any]:
        metadata = getattr(session, "metadata", {}) or {}
        return {
            "session_id": session.session_id,
            "user_id": metadata.get("user_id"),
            "summary": getattr(session, "summary", None),
            "metadata": metadata,
            "context_compressed": bool(getattr(session, "summary", None)),
            "storage": "sqlalchemy",
            "last_usage": getattr(session, "last_usage", None),
            "last_latency_ms": getattr(session, "last_latency_ms", None),
            "last_llm_calls": getattr(session, "last_llm_calls", None),
        }

    def _map_agent_event(self, event: AgentEvent, session) -> dict[str, Any] | None:
        # 运行预算（"第 N/M 步"）：wuwei 事件对象顶层已带 step，这里透出给前端
        step = getattr(event, "step", None)
        max_steps = getattr(session, "max_steps", None)
        budget = {
            **({"step": int(step)} if isinstance(step, int) else {}),
            **({"max_steps": int(max_steps)} if isinstance(max_steps, int) else {}),
        }

        if event.type == "text_delta":
            return {
                "event": "delta",
                "data": {
                    "session_id": session.session_id,
                    "content": event.data.get("content", ""),
                    **budget,
                },
            }

        if event.type == "reasoning_delta":
            return {
                "event": "reasoning_delta",
                "data": {
                    "session_id": session.session_id,
                    "content": event.data.get("content", ""),
                    **budget,
                },
            }

        if event.type == "tool_start":
            return {
                "event": "tool_calls",
                "data": {
                    "session_id": session.session_id,
                    "tool_calls": [self._build_tool_call_payload(event)],
                    **budget,
                },
            }

        if event.type == "tool_end":
            output = event.data.get("output")
            return {
                "event": "tool_results",
                "data": {
                    "session_id": session.session_id,
                    "tool_calls": [
                        self._build_tool_result_payload(
                            event,
                            status=self._status_from_tool_output(output),
                            result=output,
                        )
                    ],
                },
            }

        if event.type == "tool_error":
            return {
                "event": "tool_error",
                "data": {
                    "session_id": session.session_id,
                    "tool_call_id": event.data.get("tool_call_id"),
                    "tool_name": event.data.get("display_name") or event.data.get("tool_name") or "工具调用",
                    "message": event.data.get("message"),
                    "error_type": event.data.get("error_type"),
                },
            }

        if event.type == "done":
            return {
                "event": "done",
                "data": {
                    **self._session_payload(session),
                    "finish_reason": event.data.get("reason", "stop"),
                    "usage": event.data.get("usage"),
                    "latency_ms": event.data.get("latency_ms"),
                    "llm_calls": event.data.get("llm_calls"),
                },
            }

        if event.type == "error":
            if event.data.get("tool_call_id") or event.data.get("tool_name"):
                return {
                    "event": "tool_results",
                    "data": {
                        "session_id": session.session_id,
                        "tool_calls": [
                            self._build_tool_result_payload(
                                event,
                                status="error",
                                result=event.data.get("message"),
                            )
                        ],
                    },
                }

            return {
                "event": "error",
                "data": {
                    "session_id": session.session_id,
                    "message": event.data.get("message", "智能体执行失败。"),
                    "error_type": event.data.get("error_type"),
                    "usage": event.data.get("usage"),
                    "latency_ms": event.data.get("latency_ms"),
                    "llm_calls": event.data.get("llm_calls"),
                },
            }

        return None

    @staticmethod
    def _extract_usage_numbers(usage: Any) -> tuple[int, int, int]:
        if not isinstance(usage, dict):
            return 0, 0, 0

        input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
        return input_tokens, output_tokens, total_tokens

    @staticmethod
    def _estimate_tokens_from_text(text: str) -> int:
        """Rough token estimation when the LLM provider doesn't return usage in streaming mode."""
        if not text:
            return 0
        # ~4 chars per token for Latin, ~1.5 for CJK; use 3 as a balanced average
        return max(1, round(len(text) / 3))

    async def _record_usage_event(
        self,
        *,
        session,
        request: AgentStreamRequest,
        user: UserModel | None,
        event_data: dict[str, Any],
        tool_names: list[str],
        response_mode: str,
        agent_profile_id: int | None,
        collected_text: str = "",
    ) -> None:
        usage = event_data.get("usage") or getattr(session, "last_usage", None)
        input_tokens, output_tokens, total_tokens = self._extract_usage_numbers(usage)
        if total_tokens <= 0:
            estimated_output = self._estimate_tokens_from_text(collected_text)
            total_tokens = estimated_output
            output_tokens = estimated_output
        latency_ms = int(event_data.get("latency_ms") or getattr(session, "last_latency_ms", 0) or 0)
        llm_calls = int(event_data.get("llm_calls") or getattr(session, "last_llm_calls", 0) or 0)

        def _run():
            import time
            for attempt in range(3):
                try:
                    with self.storage.session_factory() as db:
                        db.add(
                            AgentUsageEventModel(
                                user_id=user.id if user is not None else None,
                                agent_profile_id=agent_profile_id,
                                session_id=session.session_id,
                                model_name=str(event_data.get("model") or self.settings.openai_model),
                                response_mode=response_mode,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                total_tokens=total_tokens,
                                llm_calls=llm_calls,
                                tool_calls=len(tool_names),
                                tool_names_json=dump_json(tool_names),
                                latency_ms=latency_ms,
                            )
                        )
                        db.commit()
                    return
                except Exception as e:
                    if "database is locked" in str(e) and attempt < 2:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise
        await asyncio.to_thread(_run)

    async def stream_chat(self, request: AgentStreamRequest, user: UserModel | None = None) -> AsyncIterator[dict[str, Any]]:
        # Restore agent_profile_id and response_mode from stored session metadata
        # so that page-refreshed sessions correctly resolve the right tools.
        if request.session_id and user is not None:
            stored = await self.storage.describe(request.session_id)
            if stored:
                meta = stored.get("metadata") or {}
                if request.agent_profile_id is None:
                    stored_id = meta.get("agent_profile_id")
                    if isinstance(stored_id, int) and stored_id > 0:
                        request.agent_profile_id = stored_id
                stored_mode = meta.get("response_mode")
                if isinstance(stored_mode, str) and stored_mode in ("general", "ppt", "website", "email"):
                    request.response_mode = stored_mode

        runtime_profile = await self._resolve_runtime_profile(request, user)
        response_mode = runtime_profile.response_mode
        ppt_mode = response_mode == "ppt"
        email_mode = response_mode == "email"

        # 提前设置 user context，确保 register_external_tools 能获取 user_id
        if user is not None:
            set_current_user_id(user.id)
            set_ext_user_id(user.id)

        agent = self._get_agent(runtime_profile)

        _logger.info(
            "stream_chat start: session=%s mode=%s profile=%s msg_len=%d files=%d",
            request.session_id or "(new)",
            response_mode,
            runtime_profile.slug,
            len(request.message),
            len(request.files or ()),
        )
        # ensure_session_access 已在 endpoint 层调用，此处不再重复
        await self._load_session_if_needed(agent, request)

        # 记录用户输入到补全缓存
        if user is not None and request.message:
            try:
                from app.services.cache_service import get_cache_service
                await get_cache_service().add_user_input(user.id, request.message)
                await get_cache_service().add_global_input(request.message)
            except Exception as e:
                _logger.debug("Cache input recording failed: %s", e)

        # Inject design system catalog for PPT mode
        message = request.message
        if ppt_mode:
            message = self._inject_design_catalog(message)
            edit_hint = await self._get_edit_hint(request.session_id)
            if edit_hint:
                message = message + edit_hint
            # Phase-specific injection — deferred to after session creation (see below)

        website_mode = response_mode == "website"
        if website_mode:
            message = await self._inject_website_catalog(message)

        session = agent.create_or_get_session(
            session_id=request.session_id,
            system_prompt=runtime_profile.system_prompt,
            max_steps=request.max_steps,
            parallel_tool_calls=request.parallel_tool_calls,
        )
        self._normalize_session_limits(
            session,
            response_mode=response_mode,
            requested_max_steps=request.max_steps,
            profile_max_steps=runtime_profile.max_steps,
        )
        metadata = getattr(session, "metadata", {}) or {}
        metadata.update(
            {
                "user_id": user.id if user is not None else None,
                "user_email": user.email if user is not None else None,
                "user_name": user.name if user is not None else None,
                "response_mode": response_mode,
                "agent_profile_id": runtime_profile.profile_id,
                "agent_profile_name": runtime_profile.name,
                "agent_profile_slug": runtime_profile.slug,
                # 会话展示标题：取用户本轮输入（website/email 模式会在其后追加
                # 系统注入的工作流消息，用"首条 user 消息"推导标题会取到内部提示）
                "title": (request.message or "").strip()[:40] or None,
            }
        )
        session.metadata = metadata
        # 单事务完成 owner/profile 绑定与元数据持久化
        # （原先为 assign_owner → assign_agent_profile → save_meta 三段独立事务）
        await self.storage.save_session_meta(
            session,
            user_id=user.id if user is not None else None,
            agent_profile_id=runtime_profile.profile_id,
        )
        approval_queue = self.approval_manager.subscribe(session.session_id)
        user_input_queue = UserInputBlocker.subscribe(session.session_id)
        api_approval_queue = ApprovalBlocker.subscribe(session.session_id)
        set_email_session_id(session.session_id)
        set_data_session_id(session.session_id)
        restore_website_dir_for_session(session.session_id)
        if user is not None:
            set_current_user_id(user.id)
            set_ext_user_id(user.id)
        # contextvar 兼容层：定义保留在 app.services.agent_service（外部模块按原路径读取）
        from app.services.agent_service import _current_session_id
        _current_session_id.set(session.session_id)
        ext_session_id_ctx.set(session.session_id)

        yield {
            "event": "session",
            "data": self._session_payload(session),
        }
        yield {
            "event": "run_status",
            "data": {
                "session_id": session.session_id,
                "phase": "thinking",
                "label": "大模型正在思考",
            },
        }

        runtime_queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        collected_text = ""
        saw_text_delta = False
        tool_names: list[str] = []
        usage_recorded = False
        turn_total_tokens = 0

        # 注入用户记忆上下文（按 mode 装配；ppt 也注入 —— ppt loadout 此前因 not ppt_mode 永不执行）
        if user is not None and not website_mode and not email_mode:
            try:
                from app.services.memory_loadout import assemble_memory_context
                memory_context = await assemble_memory_context(user.id, request.message, response_mode)
                if memory_context:
                    _logger.info(f"Injecting memory loadout for user {user.id} mode={response_mode}")
                    message = memory_context + "\n\n---\n\n" + message
                else:
                    _logger.info(f"No memory context found for user {user.id}")
            except Exception as e:
                _logger.warning(f"Memory loadout assembly failed: {e}")

        task_start_time = time.time()

        async def produce_events() -> None:
            nonlocal message
            try:
                # message 变量已经包含记忆注入或设计目录注入
                # 如果有文件附件，追加文件描述
                if request.files:
                    file_desc = self._build_user_message(request)
                    if file_desc != request.message:
                        message = message + "\n\n" + file_desc
                user_message = message
                _ctx_msgs = getattr(getattr(session, "context", None), "_messages", [])
                _logger.info(f"produce_events: starting, user_msg_len={len(user_message)}, context_msgs={len(_ctx_msgs)}")
                event_count = 0
                async for event in agent.stream_events(user_message, session=session):
                    event_count += 1
                    await runtime_queue.put(event)
                _ctx_msgs = getattr(getattr(session, "context", None), "_messages", [])
                _logger.info(f"produce_events: done, events={event_count}, context_msgs={len(_ctx_msgs)}")
            except Exception as e:
                _logger.error(f"produce_events: exception: {e}", exc_info=True)
                raise
            finally:
                task_had_error = False
                try:
                    if hasattr(session, "system_prompt"):
                        # Shield to ensure DB write completes even when the
                        # producer task is cancelled by client disconnecting
                        # the SSE stream, so connections are returned to the pool.
                        _logger.info(f"produce_events finally: saving meta for session {session.session_id}")
                        await asyncio.shield(self.storage.save_meta(session))
                        # 保存消息到数据库（wuwei 的 AgentSession 只在内存中存储消息）
                        _logger.info(f"produce_events finally: persisting messages for session {session.session_id}")
                        await asyncio.shield(self._persist_session_messages(session))
                        _logger.info(f"produce_events finally: done for session {session.session_id}")

                except asyncio.CancelledError:
                    _logger.warning(f"produce_events finally: cancelled for session {session.session_id}")
                    task_had_error = True
                except Exception as e:
                    _logger.warning(f"produce_events finally: error for session {session.session_id}: {e}", exc_info=True)
                    task_had_error = True
                finally:
                    # 任务完成/失败通知（异步，不阻塞 SSE）
                    if user is not None:
                        task_duration = time.time() - task_start_time
                        try:
                            from app.services.notification_service import send_task_complete_notification
                            from app.core.config import get_settings
                            settings = get_settings()
                            frontend_base = settings.get_cors_allow_origins()[0] if settings.get_cors_allow_origins() else ""
                            asyncio.create_task(
                                send_task_complete_notification(
                                    user_id=user.id,
                                    session_id=session.session_id,
                                    task_summary=collected_text[:300] if collected_text else "",
                                    duration_seconds=task_duration,
                                    frontend_base_url=frontend_base,
                                    is_error=task_had_error,
                                )
                            )
                        except Exception as notify_err:
                            _logger.warning(f"Failed to schedule task notification: {notify_err}")

                    await runtime_queue.put(None)

        producer = asyncio.create_task(produce_events())
        runtime_task = asyncio.create_task(runtime_queue.get())
        approval_task = asyncio.create_task(approval_queue.get())
        user_input_task = asyncio.create_task(user_input_queue.get())
        api_approval_task = asyncio.create_task(api_approval_queue.get())

        # Keepalive: 每 15 秒发送一次注释防止连接超时
        KEEPALIVE_INTERVAL = 15
        loop = asyncio.get_running_loop()
        last_event_time = loop.time()

        try:
            while True:
                # 使用 timeout 避免无限等待，以便发送 keepalive
                done, _ = await asyncio.wait(
                    {runtime_task, approval_task, user_input_task, api_approval_task},
                    timeout=KEEPALIVE_INTERVAL,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # 如果没有事件且距上次事件超过 keepalive 间隔，发送 keepalive
                current_time = loop.time()
                if not done and (current_time - last_event_time) >= KEEPALIVE_INTERVAL:
                    yield {"event": "keepalive", "data": {"timestamp": int(current_time)}}
                    last_event_time = current_time
                    continue

                if done:
                    last_event_time = current_time

                runtime_ended = False
                if runtime_task in done:
                    event = runtime_task.result()
                    if event is None:
                        # 不立即 break：先消费同批完成的 approval/user_input，
                        # 避免 done 竞态丢失最后一个审批事件
                        runtime_ended = True
                    else:

                        if event.type == "text_delta":
                            first_text_delta = not saw_text_delta
                            saw_text_delta = True
                            collected_text += event.data.get("content", "")
                            if ppt_mode:
                                if first_text_delta:
                                    yield {
                                        "event": "run_status",
                                        "data": {
                                            "session_id": session.session_id,
                                            "phase": "generating_ppt",
                                            "label": "正在生成 PPT 内容与版式",
                                        },
                                    }
                                # PPT 模式不转发 text_delta（LLM 思考文本），但继续处理其他事件
                                # 不 continue — 让 tool_start、tool_results、reasoning 等事件正常处理
                            if not ppt_mode and first_text_delta:
                                yield {
                                    "event": "run_status",
                                    "data": {
                                        "session_id": session.session_id,
                                        "phase": "streaming",
                                        "label": "大模型正在输出",
                                    },
                                }

                        if event.type == "tool_start":
                            tool_name = event.data.get("tool_name")
                            if isinstance(tool_name, str) and tool_name:
                                tool_names.append(tool_name)

                        if ppt_mode and event.type == "done":
                            visible_text = ""

                            _logger.info("ppt done: session=%s, creating artifact...", session.session_id)

                            artifact = await self._create_ppt_artifact(session.session_id)
                            _logger.info("ppt artifact result: session=%s, artifact=%s", session.session_id, "OK" if artifact else "None")
                            if artifact is not None:
                                yield {
                                    "event": "run_status",
                                    "data": {
                                        "session_id": session.session_id,
                                        "phase": "rendering_ppt",
                                        "label": "正在渲染 PPT 预览",
                                    },
                                }
                                yield {
                                    "event": "artifact_ready",
                                    "data": artifact,
                                }
                            else:
                                # 质量门失败，返回错误信息给用户（按 session 读取，避免跨会话串扰）
                                quality_errors, quality_warnings = self.ppt_artifacts.get_quality_feedback(session.session_id)
                                # 模型整轮没有调用保存工具 → 本轮就是普通文字回答，
                                # 不属于"生成失败"，静默收尾即可（否则会给用户报"幻灯片目录不存在"）
                                no_slides = not quality_errors or all(
                                    "幻灯片目录不存在" in err for err in quality_errors
                                )
                                if no_slides:
                                    _logger.info(
                                        "ppt run produced no slides (text-only answer), session=%s",
                                        session.session_id,
                                    )
                                    visible_text = ""
                                else:
                                    error_detail = "; ".join(quality_errors[:3])
                                    _logger.warning(
                                        "ppt artifact creation failed: session=%s, errors=%s",
                                        session.session_id, quality_errors,
                                    )
                                    visible_text = f"PPT 预览生成失败：{error_detail}"
                            if visible_text:
                                yield {
                                    "event": "delta",
                                    "data": {
                                        "session_id": session.session_id,
                                        "content": visible_text,
                                    },
                                }
                            yield {
                                "event": "run_status",
                                "data": {
                                    "session_id": session.session_id,
                                    "phase": "done",
                                    "label": "本轮回复已完成",
                                },
                            }
                            mapped = self._map_agent_event(event, session)
                            usage_dict = event.data.get("usage") or getattr(session, "last_usage", None)
                            _, _, total_tokens = self._extract_usage_numbers(usage_dict)
                            if total_tokens > 0:
                                turn_total_tokens = total_tokens
                            if not usage_recorded:
                                await self._record_usage_event(
                                    session=session,
                                    request=request,
                                    user=user,
                                    event_data=event.data,
                                    tool_names=tool_names,
                                    response_mode=response_mode,
                                    agent_profile_id=runtime_profile.profile_id,
                                    collected_text=collected_text,
                                )
                                usage_recorded = True
                            if mapped is not None:
                                yield mapped
                            runtime_task = asyncio.create_task(runtime_queue.get())
                            continue

                        # 统一 done 处理：先按模式分流（website artifact / 截断提示），
                        # 再记录 usage 并映射 done 事件。原先通用分支先 continue，
                        # 导致 website_mode 分支与 finish_reason=length 截断提示成为死代码。
                        if event.type == "done":
                            finish_reason = str(event.data.get("reason") or "stop")
                            usage_dict = event.data.get("usage") or getattr(session, "last_usage", None)
                            _, _, total_tokens = self._extract_usage_numbers(usage_dict)
                            if total_tokens > 0:
                                turn_total_tokens = total_tokens

                            if website_mode:
                                artifact = await self._create_website_artifact(
                                    session.session_id, tool_names
                                )
                                if artifact is not None:
                                    yield {
                                        "event": "run_status",
                                        "data": {
                                            "session_id": session.session_id,
                                            "phase": "rendering_website",
                                            "label": "正在渲染网站预览",
                                        },
                                    }
                                    # 版本快照：项目目录是原地迭代的，这里把本轮产物
                                    # 存成快照，用户才能回看之前的每一版
                                    try:
                                        from app.services.artifact_version_service import (
                                            snapshot_website_version,
                                        )

                                        version = await snapshot_website_version(
                                            session.session_id,
                                            artifact.get("preview_html") or "",
                                            artifact.get("title") or "",
                                        )
                                        if version:
                                            artifact["version"] = version
                                    except Exception:
                                        _logger.exception(
                                            "website version snapshot failed: session=%s",
                                            session.session_id,
                                        )
                                    yield {
                                        "event": "artifact_ready",
                                        "data": artifact,
                                    }

                            # 非 ppt 模式（ppt 在上方已有分支 continue）：发 phase=done
                            yield {
                                "event": "run_status",
                                "data": {
                                    "session_id": session.session_id,
                                    "phase": "done",
                                    "label": "本轮回复已完成",
                                },
                            }

                            # 输出被截断时追加提示
                            if finish_reason == "length":
                                yield {
                                    "event": "delta",
                                    "data": {
                                        "session_id": session.session_id,
                                        "content": (
                                            "\n\n---\n⚠️ **回复被截断**：模型输出已达到 token 上限，内容不完整。"
                                            "你可以发送「继续」让模型接着输出，或精简需求后重新提问。"
                                        ),
                                    },
                                }
                                _logger.warning(
                                    "Output truncated (finish_reason=length): session=%s tokens_used=%s",
                                    session.session_id,
                                    usage_dict,
                                )

                            if not usage_recorded:
                                await self._record_usage_event(
                                    session=session,
                                    request=request,
                                    user=user,
                                    event_data=event.data,
                                    tool_names=tool_names,
                                    response_mode=response_mode,
                                    agent_profile_id=runtime_profile.profile_id,
                                    collected_text=collected_text,
                                )
                                usage_recorded = True

                            mapped = self._map_agent_event(event, session)
                            if mapped is not None:
                                yield mapped
                            runtime_task = asyncio.create_task(runtime_queue.get())
                            continue

                        if event.type == "error" and not usage_recorded:
                            _logger.warning(
                                "agent error event: session=%s error=%s tools=%s",
                                session.session_id,
                                event.data.get("message", "")[:200],
                                tool_names,
                            )
                            await self._record_usage_event(
                                session=session,
                                request=request,
                                user=user,
                                event_data=event.data,
                                tool_names=tool_names,
                                response_mode=response_mode,
                                agent_profile_id=runtime_profile.profile_id,
                                collected_text=collected_text,
                            )
                            usage_recorded = True

                        mapped = self._map_agent_event(event, session)
                        if mapped is not None:
                            yield mapped
                        runtime_task = asyncio.create_task(runtime_queue.get())

                # 检查决策工具队列（工具在 agent 内部执行时可能产生决策事件）
                from app.tools.decision_tools import get_decision_queue
                pending_decisions = get_decision_queue(session.session_id)
                for decision in pending_decisions:
                    yield {
                        "event": "user_decision",
                        "data": decision,
                    }

                if approval_task in done:
                    approval = approval_task.result()
                    func_name = approval.get("tool_name", "")
                    display_name_map = self._get_display_name_map()
                    approval["tool_name"] = display_name_map.get(func_name, func_name)
                    yield {
                        "event": "approval_required",
                        "data": approval,
                    }
                    approval_task = asyncio.create_task(approval_queue.get())

                if user_input_task in done:
                    user_input_data = user_input_task.result()
                    yield {
                        "event": "user_input_required",
                        "data": user_input_data,
                    }
                    user_input_task = asyncio.create_task(user_input_queue.get())

                if api_approval_task in done:
                    api_approval_data = api_approval_task.result()
                    yield {
                        "event": "api_approval_required",
                        "data": api_approval_data,
                    }
                    api_approval_task = asyncio.create_task(api_approval_queue.get())

                # 同批已消费 approval/user_input 后再结束流
                if runtime_ended:
                    break
            # 对话结束后触发分层蒸馏 pipeline（L0→L1→L2→L3）
            _logger.info(f"Memory pipeline conditions: user={user is not None}, collected_text_len={len(collected_text) if collected_text else 0}, ppt_mode={ppt_mode}, website_mode={website_mode}, message={request.message[:50] if request.message else ''}")
            if user is not None and request.message and not ppt_mode and not website_mode:
                try:
                    from app.services.memory_pipeline import get_pipeline
                    ai_response = collected_text[:2000] if collected_text else ""
                    # 优先用 done 事件 usage；无则用文本估算，避免写入假数据字段
                    memory_tokens = turn_total_tokens
                    if memory_tokens <= 0 and ai_response:
                        memory_tokens = self._estimate_tokens_from_text(ai_response)
                    asyncio.create_task(
                        get_pipeline().on_turn_complete(
                            user_id=user.id,
                            session_id=request.session_id,
                            user_message=request.message,
                            assistant_message=ai_response,
                            mode=response_mode,
                            tokens_used=max(0, int(memory_tokens)),
                        )
                    )
                    _logger.info(f"Memory pipeline triggered for user {user.id} tokens_used={memory_tokens}")
                except Exception as e:
                    _logger.warning(f"Memory pipeline trigger failed: {e}")

        finally:
            _logger.info(
                "stream_chat end: session=%s mode=%s tools=%s text_len=%d",
                session.session_id,
                response_mode,
                tool_names,
                len(collected_text),
            )
            self.approval_manager.unsubscribe(session.session_id, approval_queue)
            ApprovalBlocker.unsubscribe(session.session_id)
            # 清理孤儿决策 Future，防止泄漏和阻塞下次请求
            try:
                from app.tools.decision_tools import cleanup_session_decisions
                cleanup_session_decisions(session.session_id)
            except Exception:
                pass
            for task in (runtime_task, approval_task, user_input_task, api_approval_task):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            if not producer.done():
                producer.cancel()
                # Shield to keep the producer's DB cleanup (save_meta) from
                # being cancelled alongside the SSE stream — prevents leaked
                # connections when the client disconnects mid-stream.
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.shield(producer)
            else:
                with contextlib.suppress(Exception):
                    producer.result()
