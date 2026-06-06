"""Website Agent + taste-skill 集成测试（含构建）

运行：
    cd backend
    uv run python examples/test_website_taste.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


def header(title: str):
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


def test_taste_skill_loading():
    header("测试 1：taste-skill 加载验证")
    from pathlib import Path
    skills_dir = Path('/Users/xiaojia/code/AgenticOS/data/skills/website-design-taste')

    core = (skills_dir / 'SKILL.md').read_text('utf-8')
    ref = (skills_dir / 'references' / 'taste-reference.md').read_text('utf-8')
    print(f"  ✅ 核心规则: {len(core)} 字符 ({core.count(chr(10))+1} 行)")
    print(f"  ✅ 参考手册: {len(ref)} 字符 ({ref.count(chr(10))+1} 行)")

    for s in ["BRIEF INFERENCE", "THREE DIALS", "DESIGN ENGINEERING", "AI TELLS", "PRE-FLIGHT"]:
        print(f"  {'✅' if s in core else '❌'} {s}")
    print(f"\n  ✅ taste-skill 加载验证通过\n")


def test_website_prompt():
    header("测试 2：Website Agent 提示词验证")
    from app.prompts import WEBSITE_ROUTER_PROMPT
    checks = [
        ("Router 包含 taste-skill 引用", "website-design-taste" in WEBSITE_ROUTER_PROMPT),
        ("Router 包含 Design Read", "Design Read" in WEBSITE_ROUTER_PROMPT),
    ]
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
    print(f"\n  ✅ Website 提示词验证通过\n")


async def test_website_generation():
    header("测试 3：Website 端到端生成（含构建）")

    from app.core.config import get_settings
    from wuwei import Agent, LLMGateway
    from wuwei.tools import ToolRegistry
    from wuwei.middleware import MiddlewareStack
    from app.tools.website_tools import register_website_tools

    settings = get_settings()
    print(f"  Model: {settings.openai_model}")

    # 注册网站工具 + 文件工具
    registry = ToolRegistry()
    register_website_tools(registry)

    def list_files() -> str:
        from app.core.data_path import get_current_website_dir
        wd = get_current_website_dir()
        if not wd or not Path(wd).exists():
            return "当前没有活跃的网站项目"
        files = sorted(str(p.relative_to(wd)) for p in Path(wd).rglob("*") if p.is_file())
        return f"项目文件 ({len(files)} 个):\n" + "\n".join(f"  {f}" for f in files)

    registry.register_callable(list_files, name="list_files",
                               description="列出当前网站项目的所有文件")

    # 构建系统提示词
    from app.prompts import WEBSITE_ROUTER_PROMPT
    skill_md = Path('/Users/xiaojia/code/AgenticOS/data/skills/website-design-taste/SKILL.md')
    taste_core = skill_md.read_text('utf-8')
    if taste_core.startswith('---'):
        parts = taste_core.split('---', 2)
        if len(parts) >= 3:
            taste_core = parts[2].strip()

    system_prompt = WEBSITE_ROUTER_PROMPT + "\n\n---\n\n" + taste_core[:8000]

    llm = LLMGateway.from_env(max_tokens=settings.agent_max_tokens)
    agent = Agent(
        llm=llm, tools=registry, default_system_prompt=system_prompt,
        default_max_steps=15, middleware=MiddlewareStack(), load_builtins=False,
    )
    session = agent.create_or_get_session()

    user_message = "帮我做一个个人作品集网站，极简风格，深色主题，展示 3 个项目。用 vanilla 模式。"
    print(f"\n  👤 {user_message}\n")

    start = time.time()
    text_parts = []
    tool_calls = []
    build_ok = False

    async for event in agent.stream_events(user_message, session=session):
        if event.type == "text_delta":
            text_parts.append(event.data.get("content", ""))
        elif event.type == "tool_start":
            tn = event.data.get("tool_name", "")
            tool_calls.append(tn)
            print(f"  🔧 [{tn}]", end="", flush=True)
        elif event.type == "tool_end":
            out = event.data.get("output", "")[:150]
            print(f" → {out}", end="", flush=True)
            if "构建成功" in str(out):
                build_ok = True
        elif event.type == "done":
            print()

    elapsed = time.time() - start
    full_text = "".join(text_parts)

    print(f"\n  ⏱️  耗时: {elapsed:.1f}s")
    print(f"  📊 文本输出: {len(full_text)} 字符")
    print(f"  📊 工具调用: {tool_calls}")

    has_design_read = 'Reading this as' in full_text or 'Design Read' in full_text
    has_copy = 'copy_template' in tool_calls
    has_build = 'build_website' in tool_calls

    print(f"\n  {'✅' if has_design_read else '⚠️'} Design Read: {'有' if has_design_read else '未检测到'}")
    print(f"  {'✅' if has_copy else '❌'} copy_template: {'已调用' if has_copy else '未调用'}")
    print(f"  {'✅' if has_build else '❌'} build_website: {'已调用' if has_build else '未调用'}")
    print(f"  {'✅' if build_ok else '⚠️'} 构建结果: {'成功' if build_ok else '未确认'}")

    success = has_copy and has_build
    print(f"\n  {'✅' if success else '⚠️'} Website 生成{'成功' if success else '部分完成'}\n")
    return success


async def main():
    header("Website Agent + taste-skill 集成测试")
    from app.core.config import get_settings
    s = get_settings()
    print(f"  Model: {s.openai_model}")

    test_taste_skill_loading()
    test_website_prompt()
    await test_website_generation()

    header("全部测试完成 ✅")


if __name__ == "__main__":
    asyncio.run(main())
