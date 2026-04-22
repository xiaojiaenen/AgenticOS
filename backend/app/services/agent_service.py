from functools import lru_cache
from typing import Any, AsyncIterator

from wuwei import Agent, LLMGateway

from app.core.config import Settings, get_settings
from app.schemas.agent import AgentStreamRequest


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._agent: Agent | None = None

    def ensure_ready(self) -> None:
        self._get_agent()

    def _get_agent(self) -> Agent:
        if self._agent is not None:
            return self._agent

        if not self.settings.openai_api_key:
            raise RuntimeError("缺少 OPENAI_API_KEY，请先在环境变量或 .env 中配置后再调用 /agent/stream。")

        llm_config: dict[str, Any] = {
            "provider": "openai",
            "api_key": self.settings.openai_api_key,
            "model": self.settings.openai_model,
        }
        if self.settings.openai_base_url:
            llm_config["base_url"] = self.settings.openai_base_url

        self._agent = Agent(
            llm=LLMGateway(llm_config),
            tools=[],
            default_system_prompt=self.settings.agent_system_prompt,
            default_max_steps=self.settings.agent_max_steps,
            default_parallel_tool_calls=self.settings.agent_parallel_tool_calls,
        )
        return self._agent

    async def stream_chat(self, request: AgentStreamRequest) -> AsyncIterator[dict[str, Any]]:
        agent = self._get_agent()
        session = agent.create_or_get_session(
            session_id=request.session_id,
            system_prompt=request.system_prompt,
            max_steps=request.max_steps,
            parallel_tool_calls=request.parallel_tool_calls,
        )

        yield {
            "event": "session",
            "data": {
                "session_id": session.session_id,
            },
        }

        stream = await agent.run(
            request.message,
            session=session,
            stream=True,
        )

        last_usage: dict[str, int] | None = None
        emitted_done = False

        async for chunk in stream:
            if chunk.content:
                yield {
                    "event": "delta",
                    "data": {
                        "session_id": session.session_id,
                        "content": chunk.content,
                    },
                }

            if chunk.tool_calls_complete:
                yield {
                    "event": "tool_calls",
                    "data": {
                        "session_id": session.session_id,
                        "tool_calls": [tool_call.model_dump(mode="json") for tool_call in chunk.tool_calls_complete],
                    },
                }

            if chunk.usage:
                last_usage = chunk.usage

            if chunk.finish_reason == "stop":
                emitted_done = True
                yield {
                    "event": "done",
                    "data": {
                        "session_id": session.session_id,
                        "finish_reason": chunk.finish_reason,
                        "usage": last_usage,
                    },
                }

        if not emitted_done:
            yield {
                "event": "done",
                "data": {
                    "session_id": session.session_id,
                    "finish_reason": "completed",
                    "usage": last_usage,
                },
            }


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(get_settings())
