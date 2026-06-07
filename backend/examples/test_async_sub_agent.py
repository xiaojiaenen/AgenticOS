"""示例 1：AsyncSubAgent — 后台异步子任务

测试场景：主 Agent 启动一个后台代码计算任务，继续对话，稍后查询结果。
使用 .env 中的真实 LLM 配置（DeepSeek）。

运行：
    cd backend
    uv run python examples/test_async_sub_agent.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

# 必须先导入 agent_service 以应用并发补丁
import app.services.agent_service  # noqa: F401

from app.core.config import get_settings
from wuwei import Agent
from wuwei.llm import LLMGateway
from wuwei.tools import ToolRegistry
from wuwei.middleware import MiddlewareStack
from wuwei.plugin import PluginContext
from wuwei.plugin.builtin import calc, python, git
from wuwei.agent.async_sub_agent import AsyncSubAgentMiddleware, AsyncSubAgent


async def main():
    settings = get_settings()
    print(f"🔧 LLM: {settings.openai_model} @ {settings.openai_base_url}")
    print()

    # 1. 构建子代理的工具集
    code_registry = ToolRegistry()
    code_ctx = PluginContext(tool_registry=code_registry)
    calc.setup(code_ctx)
    python.setup(code_ctx)
    git.setup(code_ctx)

    sub_agents = [
        AsyncSubAgent(
            name="code_analyst",
            description="代码分析与执行：运行 Python 脚本、数学计算、Git 操作。适合需要后台运行代码或分析的场景。",
            system_prompt="你是一个代码分析助手。执行 Python 代码并返回结果。直接返回执行结果，简洁明了。",
            tools=list(code_registry.list_tools()),
            max_steps=5,
            inherit_context=False,
        ),
    ]

    # 2. 创建主 Agent，注入 AsyncSubAgentMiddleware
    llm = LLMGateway.from_env(max_tokens=2048)
    registry = ToolRegistry()
    stack = MiddlewareStack()
    stack.add(AsyncSubAgentMiddleware(sub_agents=sub_agents, parent_llm=llm))

    agent = Agent(
        llm=llm,
        tools=registry,
        default_system_prompt=(
            "你是智能助手。你有后台异步任务能力。\n"
            "用户要求计算或执行代码时，用 start_async_task 启动 code_analyst 子代理。\n"
            "启动后告知用户任务已开始，用户问结果时用 check_async_task 查询。"
        ),
        default_max_steps=5,
        middleware=stack,
        load_builtins=False,
    )

    session = agent.create_or_get_session()

    # 第一轮：启动后台任务
    print("👤 用户: 帮我在后台算一下 fibonacci(25)")
    print("🤖 AI: ", end="", flush=True)

    start = time.time()
    async for event in agent.stream_events("帮我在后台算一下 fibonacci(25) 的值", session=session):
        if event.type == "text_delta":
            print(event.data.get("content", ""), end="", flush=True)
        elif event.type == "tool_start":
            print(f"\n   🔧 [{event.data.get('tool_name', '')}]")
        elif event.type == "tool_end":
            output = event.data.get("output", "")[:120]
            print(f"   ✅ {output}")
        elif event.type == "done":
            print()

    print(f"\n⏱️  耗时: {time.time() - start:.1f}s")

    # 第二轮：查询结果
    print("\n👤 用户: 结果出来了吗？")
    print("🤖 AI: ", end="", flush=True)

    async for event in agent.stream_events("结果出来了吗？", session=session):
        if event.type == "text_delta":
            print(event.data.get("content", ""), end="", flush=True)
        elif event.type == "tool_start":
            print(f"\n   🔧 [{event.data.get('tool_name', '')}]")
        elif event.type == "tool_end":
            output = event.data.get("output", "")[:120]
            print(f"   ✅ {output}")
        elif event.type == "done":
            print()

    print("\n✅ AsyncSubAgent 测试完成")


if __name__ == "__main__":
    asyncio.run(main())
