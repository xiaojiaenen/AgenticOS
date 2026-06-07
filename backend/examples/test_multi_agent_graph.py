"""示例 2：MultiAgentGraph — 多 Agent 并行协作

测试场景：Leader 将"写一份 Python 异步编程技术报告"分配给 researcher + writer 并行执行，
reviewer 最后审查。使用 .env 中的真实 LLM 配置（DeepSeek）。

运行：
    cd backend
    uv run python examples/test_multi_agent_graph.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

from app.core.config import get_settings
from app.services.multi_agent_graph_service import MultiAgentGraphService


async def main():
    settings = get_settings()
    print(f"🔧 LLM: {settings.openai_model} @ {settings.openai_base_url}")
    print()

    svc = MultiAgentGraphService(settings)
    graph = svc.build_graph()

    print("🏗️  MultiAgentGraph 架构：")
    print("   Leader (任务分解)")
    print("   ├── researcher (调研分析)")
    print("   ├── writer (内容写作)")
    print("   └── reviewer (质量审查)")
    print()

    task = "写一份 Python asyncio 异步编程的技术报告，包含：1) 核心概念 2) 常见模式 3) 最佳实践"
    print(f"📋 任务: {task}")
    print("-" * 60)

    # 方式 1：流式执行，观察每个 Agent 的输出
    print("\n🚀 开始执行...\n")
    step = 0
    async for event in graph.run_stream(task):
        event_type = event.type if hasattr(event, "type") else str(event)

        if hasattr(event, "type"):
            if event.type == "text_delta":
                content = event.data.get("content", "")
                if content:
                    print(content, end="", flush=True)
            elif event.type == "tool_start":
                tool_name = event.data.get("tool_name", "")
                print(f"\n   🔧 [{tool_name}]", end="")
            elif event.type == "tool_end":
                print(" ✅")
            elif event.type == "done":
                step += 1
                print(f"\n   📊 Step {step} 完成")
            elif event.type == "task_start":
                agent_name = event.data.get("name", "unknown")
                print(f"\n{'='*40}")
                print(f"🤖 Worker [{agent_name}] 开始工作")
                print(f"{'='*40}")
            elif event.type == "task_end":
                agent_name = event.data.get("name", "unknown")
                print(f"\n✅ Worker [{agent_name}] 完成")
        else:
            # 其他事件类型
            print(f"   📡 Event: {event_type}")

    print("\n" + "=" * 60)
    print("✅ MultiAgentGraph 测试完成")

    # 方式 2：非流式执行（适合后端内部调用）
    print("\n📝 非流式模式测试（简单任务）...")
    result = await svc.run("用三句话总结 Python GIL 的作用")
    print(f"\n📄 结果:\n{result}")
    print("\n✅ 全部测试完成")


if __name__ == "__main__":
    asyncio.run(main())
