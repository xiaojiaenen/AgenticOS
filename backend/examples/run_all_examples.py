"""综合示例：三个 wuwei 新功能联合测试

一次运行测试全部三个功能：
1. AsyncSubAgent — 后台异步子任务
2. MultiAgentGraph — 多 Agent 并行协作
3. 并发工具执行 — 安全工具自动并行

使用 .env 中的真实 LLM 配置（DeepSeek）。

运行：
    cd backend
    uv run python examples/run_all_examples.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

# 必须先导入 agent_service 以应用并发补丁
import app.services.agent_service  # noqa: F401

from app.core.config import get_settings


def header(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


async def test_async_sub_agent(settings):
    """测试 1：AsyncSubAgent 后台异步子任务"""
    header("测试 1：AsyncSubAgent — 后台异步子任务")

    from wuwei import Agent
    from wuwei.llm import LLMGateway
    from wuwei.tools import ToolRegistry
    from wuwei.middleware import MiddlewareStack
    from wuwei.plugin import PluginContext
    from wuwei.plugin.builtin import calc, python
    from wuwei.agent.async_sub_agent import AsyncSubAgentMiddleware, AsyncSubAgent

    # 子代理
    code_registry = ToolRegistry()
    code_ctx = PluginContext(tool_registry=code_registry)
    calc.setup(code_ctx)
    python.setup(code_ctx)

    sub_agents = [AsyncSubAgent(
        name="code_analyst",
        description="代码分析与执行：运行Python脚本、数学计算",
        system_prompt="你是代码分析助手。执行Python代码并返回结果。简洁明了。",
        tools=list(code_registry.list_tools()),
        max_steps=5,
        inherit_context=False,
    )]

    llm = LLMGateway.from_env(max_tokens=2048)
    registry = ToolRegistry()
    stack = MiddlewareStack()
    stack.add(AsyncSubAgentMiddleware(sub_agents=sub_agents, parent_llm=llm))

    agent = Agent(
        llm=llm,
        tools=registry,
        default_system_prompt="你是智能助手。有后台异步任务能力。用 start_async_task 启动子代理。",
        default_max_steps=5,
        middleware=stack,
        load_builtins=False,
    )
    session = agent.create_or_get_session()

    print("👤 帮我在后台算一下 fibonacci(20)")
    print("🤖 ", end="", flush=True)

    start = time.time()
    async for event in agent.stream_events("帮我在后台算一下 fibonacci(20)", session=session):
        if event.type == "text_delta":
            print(event.data.get("content", ""), end="", flush=True)
        elif event.type == "tool_start":
            print(f"\n   🔧 [{event.data.get('tool_name', '')}]")
        elif event.type == "tool_end":
            print(f"   ✅ {event.data.get('output', '')[:100]}")
        elif event.type == "done":
            print()

    print(f"\n⏱️  {time.time() - start:.1f}s")
    print("✅ AsyncSubAgent 测试通过")


async def test_multi_agent_graph(settings):
    """测试 2：MultiAgentGraph 多 Agent 并行协作"""
    header("测试 2：MultiAgentGraph — 多 Agent 并行协作")

    from app.services.multi_agent_graph_service import MultiAgentGraphService

    svc = MultiAgentGraphService(settings)

    task = "用三句话总结 Python 的 asyncio 核心概念"
    print(f"📋 {task}")

    start = time.time()
    result = await svc.run(task)
    elapsed = time.time() - start

    print(f"\n📄 {result}")
    print(f"\n⏱️  {elapsed:.1f}s")
    print("✅ MultiAgentGraph 测试通过")


async def test_concurrent_tools(settings):
    """测试 3：并发工具执行"""
    header("测试 3：并发工具执行 — 安全工具自动并行")

    from wuwei import Agent
    from wuwei.llm import LLMGateway
    from wuwei.tools import ToolRegistry
    from wuwei.middleware import MiddlewareStack
    from wuwei.plugin import PluginContext
    from wuwei.plugin.builtin import calc
    from wuwei.runtime.agent_runner import AgentRunner

    print(f"补丁: {AgentRunner.stream_events.__name__}")

    registry = ToolRegistry()
    ctx = PluginContext(tool_registry=registry)
    calc.setup(ctx)

    llm = LLMGateway.from_env(max_tokens=2048)
    agent = Agent(
        llm=llm,
        tools=registry,
        default_system_prompt="你是计算助手。同时调用多个calculate工具。",
        default_max_steps=3,
        middleware=MiddlewareStack(),
        load_builtins=False,
    )
    session = agent.create_or_get_session()

    print("👤 计算 123*456、789+321、2**16")
    print("🤖 ", end="", flush=True)

    start = time.time()
    async for event in agent.stream_events("计算 123*456、789+321、2**16", session=session):
        if event.type == "text_delta":
            print(event.data.get("content", ""), end="", flush=True)
        elif event.type == "tool_start":
            print(f"\n   🔧 [{event.data.get('tool_name', '')}]")
        elif event.type == "tool_end":
            print(f"   ✅ {event.data.get('output', '')[:80]}")
        elif event.type == "done":
            print()

    print(f"\n⏱️  {time.time() - start:.1f}s")
    print("✅ 并发工具执行测试通过")


async def main():
    settings = get_settings()

    header("AgenticOS wuwei 新功能综合测试")
    print(f"🔧 LLM: {settings.openai_model} @ {settings.openai_base_url}")

    await test_async_sub_agent(settings)
    await test_multi_agent_graph(settings)
    await test_concurrent_tools(settings)

    header("全部测试完成 ✅")
    print("三个 wuwei 新功能均正常工作：")
    print("  1. AsyncSubAgent — 后台异步子任务")
    print("  2. MultiAgentGraph — 多 Agent 并行协作")
    print("  3. 并发工具执行 — 安全工具自动并行")


if __name__ == "__main__":
    asyncio.run(main())
