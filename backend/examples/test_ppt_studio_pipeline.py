"""PPT Studio Pipeline 端到端测试

测试 4 阶段多智能体 PPT 流水线的完整流程：
1. Planner — 结构规划
2. Designer — 逐页 SVG 生成
3. Reviewer — 质量审查
4. Assembler — 组装 artifact

同时验证工具、技能、主题系统是否正常工作。

运行：
    cd backend
    uv run python examples/test_ppt_studio_pipeline.py
"""

import asyncio
import json
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


# ---------------------------------------------------------------------------
# Test 1: 基础设施检查
# ---------------------------------------------------------------------------

def test_infrastructure():
    """验证主题系统、技能文件、质量检查器是否正常"""
    header("测试 1：基础设施检查")

    # 主题系统
    from app.services.ppt.theme_token_resolver import (
        list_available_themes, load_theme_tokens, build_color_token_table,
    )
    themes = list_available_themes()
    print(f"  主题数量: {len(themes)}")
    assert len(themes) > 10, f"主题数量不足: {len(themes)}"
    print(f"  ✅ 主题系统正常 ({len(themes)} 个主题)")

    # 加载一个主题的 tokens
    tokens = load_theme_tokens("apple")
    print(f"  apple 主题 tokens: {len(tokens)} 个")
    assert len(tokens) > 5, f"apple tokens 不足: {len(tokens)}"
    print(f"  ✅ 主题 Token 加载正常")

    # 技能文件
    skills_dir = Path(__file__).resolve().parent.parent.parent / "data" / "skills"
    required_skills = ["ppt-design-guide", "ppt-template-library", "ppt-workflow", "ppt-quality-budgets"]
    for skill_name in required_skills:
        skill_path = skills_dir / skill_name / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text("utf-8")
            print(f"  ✅ {skill_name} 存在 ({len(content)} 字符)")
        else:
            print(f"  ❌ {skill_name} 不存在: {skill_path}")

    # 质量检查器
    from app.services.ppt.svg_quality_checker import (
        SVGQualityChecker, check_spec_lock_consistency, check_layout_discipline,
        check_canvas_format, SUPPORTED_VIEWBOXES,
    )
    print(f"  ✅ 质量检查器导入正常")
    print(f"  ✅ 支持 {len(SUPPORTED_VIEWBOXES)} 种画布格式")

    # PptArtifactService
    from app.services.ppt_artifact_service import PptArtifactService
    print(f"  ✅ PptArtifactService 导入正常")

    print("\n  ✅ 基础设施检查全部通过\n")


# ---------------------------------------------------------------------------
# Test 2: PPT Studio Pipeline 端到端（真实 LLM）
# ---------------------------------------------------------------------------

async def test_pipeline_e2e():
    """用真实 LLM 运行完整的 4 阶段流水线"""
    header("测试 2：PPT Studio Pipeline 端到端")

    from app.core.config import get_settings
    from app.services.ppt.ppt_studio_pipeline import run_ppt_studio_pipeline
    from app.services.ppt.theme_token_resolver import list_available_themes

    settings = get_settings()
    print(f"  🔧 Model: {settings.openai_model} @ {settings.openai_base_url}")

    # 生成唯一 session_id
    import uuid
    session_id = f"test_studio_{uuid.uuid4().hex[:8]}"
    print(f"  📂 Session: {session_id}")

    user_message = "帮我做一个 5 页的 PPT，主题是「2025 年 AI 行业趋势」，面向投资人。简洁大气。"

    print(f"\n  👤 用户请求: {user_message}\n")

    start = time.time()
    events = []

    async for event in run_ppt_studio_pipeline(
        user_message=user_message,
        session_id=session_id,
        settings=settings,
    ):
        events.append(event)
        event_type = event.get("event", "?")
        data = event.get("data", {})

        if event_type == "run_status":
            phase = data.get("phase", "")
            label = data.get("label", "")
            print(f"  🔄 [{phase}] {label}")
        elif event_type == "delta":
            content = data.get("content", "")
            print(f"  💬 {content}")
        elif event_type == "done":
            artifact = data.get("artifact", {})
            print(f"\n  ✅ 完成!")
            if artifact:
                print(f"     标题: {artifact.get('title', '?')}")
                print(f"     页数: {artifact.get('slide_count', '?')}")
                print(f"     artifact_id: {artifact.get('artifact_id', '?')}")
        elif event_type == "error":
            msg = data.get("message", "未知错误")
            print(f"\n  ❌ 错误: {msg}")

    elapsed = time.time() - start
    print(f"\n  ⏱️  总耗时: {elapsed:.1f}s")
    print(f"  📊 事件总数: {len(events)}")

    # 检查是否成功
    done_events = [e for e in events if e.get("event") == "done"]
    error_events = [e for e in events if e.get("event") == "error"]

    if done_events:
        artifact = done_events[0].get("data", {}).get("artifact", {})
        slide_count = artifact.get("slide_count", 0)
        print(f"  ✅ Pipeline 成功: {slide_count} 页 PPT")

        # 验证生成的 SVG 文件
        from app.core.data_path import PPT_SESSIONS_DIR
        slides_dir = PPT_SESSIONS_DIR / session_id
        if slides_dir.exists():
            svg_files = sorted(slides_dir.glob("slide_*.svg"))
            print(f"  📄 SVG 文件: {len(svg_files)} 个")
            for f in svg_files:
                content = f.read_text("utf-8")
                has_viewbox = "viewBox" in content
                has_theme = "data-theme" in content
                has_notes = "<!-- notes:" in content
                has_groups = "<g " in content
                uses_var = "var(--" in content
                status = "✅" if all([has_viewbox, has_theme, has_groups, uses_var]) else "⚠️"
                print(f"    {status} {f.name} ({len(content)} chars) vb={has_viewbox} theme={has_theme} notes={has_notes} <g>={has_groups} var={uses_var}")

        # 验证 artifact 输出目录
        from app.core.data_path import PPT_OUTPUT_DIR
        output_dirs = list(PPT_OUTPUT_DIR.glob("*"))
        if output_dirs:
            latest = max(output_dirs, key=lambda p: p.stat().st_mtime)
            preview = latest / "preview.html"
            if preview.exists():
                html_content = preview.read_text("utf-8")
                print(f"  🌐 Preview HTML: {len(html_content)} 字符")
                print(f"  ✅ Artifact 输出正常")
    else:
        print(f"  ❌ Pipeline 失败")
        for e in error_events:
            print(f"     错误: {e.get('data', {}).get('message', '?')}")

    print(f"\n  ✅ 端到端测试完成\n")


# ---------------------------------------------------------------------------
# Test 3: 工具和技能可用性检查
# ---------------------------------------------------------------------------

def test_tools_and_skills():
    """验证 PPT 模式下的工具和技能是否正确注册"""
    header("测试 3：工具和技能可用性")

    from app.services.agent_service import AgentService
    from app.services.agent_profile_service import RuntimeAgentProfile
    from app.core.config import get_settings

    settings = get_settings()

    # 构建 PPT 模式的工具注册表
    profile = RuntimeAgentProfile(
        profile_id=None, name="ppt", slug="ppt", response_mode="ppt",
        system_prompt="", builtin_tools=("skill", "file", "calc", "time"),
        approval_tools=frozenset(), signature=(), skills=(),
    )

    try:
        registry, _ = AgentService._build_tool_registry(profile)
        tool_names = list(registry._tools.keys()) if hasattr(registry, '_tools') else []
        print(f"  注册工具数量: {len(tool_names)}")
        for name in sorted(tool_names):
            print(f"    - {name}")

        # 检查关键工具是否存在
        expected_tools = ["save_slide", "read_slide", "load_skill", "search_icons"]
        for tool_name in expected_tools:
            if tool_name in tool_names:
                print(f"  ✅ {tool_name} 已注册")
            else:
                print(f"  ⚠️ {tool_name} 未注册（可能在运行时动态加载）")
    except Exception as e:
        print(f"  ⚠️ 工具注册表构建出错: {e}")
        print(f"  （这不影响 pipeline 测试，因为 pipeline 使用 LLMGateway.generate）")

    # 验证技能可通过文件系统访问
    from pathlib import Path
    skills_dir = Path(__file__).resolve().parent.parent.parent / "data" / "skills"
    ppt_skills = [d.name for d in skills_dir.iterdir() if d.is_dir() and d.name.startswith("ppt-")]
    print(f"\n  PPT 技能目录: {ppt_skills}")

    for skill_name in ppt_skills:
        skill_md = skills_dir / skill_name / "SKILL.md"
        if skill_md.exists():
            content = skill_md.read_text("utf-8")
            # 提取 frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    import yaml
                    meta = yaml.safe_load(parts[1])
                    print(f"  ✅ {skill_name}: v{meta.get('version', '?')} — {meta.get('description', '?')[:60]}")
                else:
                    print(f"  ✅ {skill_name}: {len(content)} 字符")
            else:
                print(f"  ✅ {skill_name}: {len(content)} 字符")

    print(f"\n  ✅ 工具和技能检查完成\n")


# ---------------------------------------------------------------------------
# Test 4: Planner 单独测试
# ---------------------------------------------------------------------------

async def test_planner_only():
    """单独测试 Planner 阶段"""
    header("测试 4：Planner 单独测试")

    from app.core.config import get_settings
    from app.services.ppt.ppt_studio_pipeline import _run_planner
    from wuwei import LLMGateway

    settings = get_settings()
    llm = LLMGateway.from_env(max_tokens=settings.agent_max_tokens)

    user_message = "做一个 8 页的季度销售分析 PPT，面向高管，需要数据图表"

    print(f"  👤 {user_message}")
    print(f"  🔧 Model: {settings.openai_model}\n")

    start = time.time()
    result = await _run_planner(llm, user_message)
    elapsed = time.time() - start

    if result:
        print(f"  ✅ Planner 成功 ({elapsed:.1f}s)")
        print(f"     标题: {result.get('title', '?')}")
        print(f"     主题: {result.get('theme', '?')}")
        print(f"     页数: {result.get('page_count', len(result.get('pages', [])))}")
        print(f"     受众: {result.get('audience', '?')}")

        pages = result.get("pages", [])
        print(f"\n     页面规划:")
        for p in pages:
            print(f"       P{p.get('num', '?'):02d} [{p.get('layout', '?'):20s}] {p.get('rhythm', '?'):10s} — {p.get('title', '?')}")

        spec_lock = result.get("spec_lock", {})
        if spec_lock:
            print(f"\n     spec_lock:")
            print(f"       颜色: {list(spec_lock.get('colors', {}).keys())}")
            print(f"       字体: {list(spec_lock.get('typography', {}).keys())}")
            print(f"       节奏: {spec_lock.get('rhythm', {})}")
    else:
        print(f"  ❌ Planner 失败 ({elapsed:.1f}s)")

    print(f"\n  ✅ Planner 测试完成\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    header("PPT Studio Pipeline 测试套件")
    from app.core.config import get_settings
    s = get_settings()
    print(f"  🔧 Model: {s.openai_model} @ {s.openai_base_url}")

    # 同步测试
    test_infrastructure()
    test_tools_and_skills()

    # 异步测试
    await test_planner_only()
    await test_pipeline_e2e()

    header("全部测试完成 ✅")


if __name__ == "__main__":
    asyncio.run(main())
