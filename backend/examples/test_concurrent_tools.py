"""示例 3：并发工具执行 — 安全工具自动并行

测试场景：Agent 同时调用多个计算工具，安全工具自动用 asyncio.gather 并行执行。
使用 .env 中的真实 LLM 配置（DeepSeek）。

运行：
    cd backend
    uv run python examples/test_concurrent_tools.py
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
from wuwei import Agent
from wuwei.llm import LLMGateway
from wuwei.tools import ToolRegistry
from wuwei.middleware import MiddlewareStack
from wuwei.plugin import PluginContext
from wuwei.plugin.builtin import calc, time_plugin
from wuwei.runtime.agent_runner import AgentRunner


async def main():
    settings = get_settings()
    print(f"🔧 LLM: {settings.openai_model} @ {settings.openai_base_url}")
    print(f"🔧 并发补丁: {AgentRunner.stream_events.__name__}")
    print()

    # 构建工具集
    registry = ToolRegistry()
    ctx = PluginContext(tool_registry=registry)
    calc.setup(ctx)
    time_plugin.setup(ctx)

    # 创建 Agent
    llm = LLMGateway.from_env(max_tokens=2048)
    agent = Agent(
        llm=llm,
        tools=registry,
        default_system_prompt=(
            "你是计算助手。用户要求多个计算时，请同时调用多个 calculate 工具，不要一个一个调用。"
        ),
        default_max_steps=5,
        middleware=MiddlewareStack(),
        load_builtins=False,
    )
    session = agent.create_or_get_session()

    print("👤 用户: 计算 123*456、789+321、1000/7、2^16")
    print("🤖 AI: ", end="", flush=True)

    start = time.time()
    tool_log = []

    async for event in agent.stream_events(
        "请同时计算 123*456、789+321、1000/7、2**16 四个表达式，把结果都告诉我",
        session=session,
    ):
        if event.type == "text_delta":
            print(event.data.get("content", ""), end="", flush=True)
        elif event.type == "tool_start":
            name = event.data.get("tool_name", "")
            args = event.data.get("args", {})
            tool_log.append({"name": name, "args": args, "t": time.time()})
            print(f"\n   🔧 [{name}] {json.dumps(args, ensure_ascii=False)[:50]}")
        elif event.type == "tool_end":
            output = event.data.get("output", "")[:80]
            print(f"   ✅ {output}")
        elif event.type == "done":
            print()

    elapsed = time.time() - start
    print(f"\n⏱️  总耗时: {elapsed:.1f}s")
    print(f"📊 工具调用: {len(tool_log)} 次")

    # 检测并发
    if len(tool_log) >= 2:
        overlaps = 0
        for i in range(len(tool_log) - 1):
            for j in range(i + 1, len(tool_log)):
                a, b = tool_log[i], tool_log[j]
                if abs(a["t"] - b["t"]) < 0.5:  # 500ms 内视为并发
                    overlaps += 1
        if overlaps > 0:
            print(f"⚡ 检测到并发执行!")

    print("\n✅ 并发工具执行测试完成")


if __name__ == "__main__":
    asyncio.run(main())
