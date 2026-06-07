"""端到端 LLM PPT 生成测试 — 验证完整流程（规划→生成→预览）

使用 .env 中的真实 LLM 配置，测试：
1. submit_slide_plan 工具 + 缓存机制
2. 质量门 + artifact 创建
3. 端到端 LLM 生成（真实 LLM）

运行：
    cd backend
    uv run python examples/test_ppt_e2e.py
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
# Test 1: submit_slide_plan 工具 + 缓存机制
# ---------------------------------------------------------------------------

async def test_submit_slide_plan():
    """验证 submit_slide_plan 存储计划到缓存。"""
    header("测试 1：submit_slide_plan + 缓存机制")

    from app.tools.ppt_tools import pop_pending_slide_plan, reset_slides_dir_cache

    reset_slides_dir_cache()

    # 模拟 submit_slide_plan 内部逻辑
    import app.tools.ppt_tools as ppt_tools
    plan = [
        {"slide_num": 1, "layout": "cover", "title": "AI 科普"},
        {"slide_num": 2, "layout": "toc", "title": "目录"},
        {"slide_num": 3, "layout": "timeline", "title": "AI 发展"},
    ]
    ppt_tools._pending_slide_plan = plan
    print(f"  ✅ submit_slide_plan: 暂存 {len(plan)} 页计划")

    # 取出计划
    result = pop_pending_slide_plan()
    assert result is not None
    assert len(result) == 3
    print(f"  ✅ pop_pending_slide_plan: 取出 {len(result)} 页计划")

    # 缓存已清空
    assert pop_pending_slide_plan() is None
    print(f"  ✅ 缓存已清空")


# ---------------------------------------------------------------------------
# Test 2: 质量门错误路径
# ---------------------------------------------------------------------------

async def test_quality_gate_errors():
    """验证 _create_ppt_artifact 所有失败路径都有错误信息。"""
    header("测试 2：质量门错误路径")

    from app.services.ppt_artifact_service import PptArtifactService
    import tempfile

    # Case 1: 目录不存在
    svc = PptArtifactService()
    result = await svc.create_from_slides_dir("test", Path("/tmp/nonexistent_xyz"))
    assert result is None
    assert len(svc._last_quality_errors) > 0
    print(f"  ✅ 目录不存在: {svc._last_quality_errors[0]}")

    # Case 2: 不足 3 页
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "slide_1.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>')
        svc = PptArtifactService()
        result = await svc.create_from_slides_dir("test", td)
        assert result is None
        print(f"  ✅ 不足 3 页: {svc._last_quality_errors[0]}")

    # Case 3: 缺少 viewBox
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i in range(1, 4):
            (td / f"slide_{i}.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
        svc = PptArtifactService()
        result = await svc.create_from_slides_dir("test", td)
        assert result is None
        print(f"  ✅ 缺少 viewBox: {svc._last_quality_errors[0]}")

    # Case 4: viewBox 不一致
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "slide_1.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>')
        (td / "slide_2.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720"></svg>')
        (td / "slide_3.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080"></svg>')
        svc = PptArtifactService()
        result = await svc.create_from_slides_dir("test", td)
        assert result is None
        print(f"  ✅ viewBox 不一致: {svc._last_quality_errors[0]}")


# ---------------------------------------------------------------------------
# Test 3: 端到端 LLM 生成（真实 LLM）
# ---------------------------------------------------------------------------

async def test_e2e_llm_generation():
    """用真实 LLM 生成 5 页 PPT，验证完整流程。

    流程：
    1. 规划阶段：agent 规划 + submit_slide_plan
    2. 生成阶段：agent 逐页 save_slide
    3. 质量门 + artifact 创建
    """
    header("测试 3：端到端 LLM 生成（真实 LLM）")

    from app.core.config import get_settings
    from wuwei import Agent
    from wuwei.llm import LLMGateway
    from wuwei.tools import ToolRegistry

    from app.services.agent_service import AgentService
    from app.prompts import PPT_SYSTEM_PROMPT
    from app.tools.ppt_tools import register_ppt_tools, reset_slides_dir_cache

    settings = get_settings()
    print(f"  🔧 LLM: {settings.openai_model} @ {settings.openai_base_url}")

    reset_slides_dir_cache()

    registry = ToolRegistry()
    register_ppt_tools(registry)

    # 注册 load_skill 模拟（不需要真实 skill 文件）
    def load_skill(skill_name: str) -> dict:
        return {"name": skill_name, "description": f"技能 {skill_name}", "instruction": "（测试模式，跳过技能内容）", "load_token": "test-token", "references": []}

    def load_skill_reference(skill_name: str, reference_path: str, load_token: str = "") -> dict:
        return {"ok": True, "content": f"（测试模式，跳过模板 {reference_path}）"}

    def search_icons(query: list[str] | str, style: str = "chunk-filled") -> dict:
        return {"results": [{"name": "brain", "style": "chunk-filled"}, {"name": "robot", "style": "chunk-filled"}]}

    registry.register_callable(load_skill, name="load_skill", description="加载技能")
    registry.register_callable(load_skill_reference, name="load_skill_reference", description="读取技能引用文件")
    registry.register_callable(search_icons, name="search_icons", description="搜索图标")

    svc = AgentService(settings)
    user_msg = svc._inject_design_catalog(
        "做一个 5 页的 AI 科普 PPT，多加图表。"
    )

    llm = LLMGateway.from_env(max_tokens=8192)
    agent = Agent(
        llm=llm,
        tools=registry,
        default_system_prompt=PPT_SYSTEM_PROMPT,
        default_max_steps=30,
        load_builtins=False,
    )
    session = agent.create_or_get_session()

    print(f"  👤 做一个 5 页的 AI 科普 PPT，多加图表")
    print(f"  🤖 ", end="", flush=True)

    start = time.time()
    text_parts = []
    tool_calls = []

    async for event in agent.stream_events(user_msg, session=session):
        if event.type == "text_delta":
            content = event.data.get("content", "")
            text_parts.append(content)
            if len("".join(text_parts)) <= 300:
                print(content, end="", flush=True)
        elif event.type == "tool_start":
            name = event.data.get("tool_name", "")
            tool_calls.append(name)
            print(f"\n  🔧 [{name}]", end="", flush=True)
        elif event.type == "tool_end":
            output = event.data.get("output", "")[:80]
            print(f" → {output}", end="", flush=True)
        elif event.type == "done":
            print()

    elapsed = time.time() - start
    full_text = "".join(text_parts)

    print(f"\n  ⏱️  规划耗时: {elapsed:.1f}s")
    print(f"  📊 工具调用: {len(tool_calls)} 次")

    # 检查 submit_slide_plan 是否被调用
    has_plan = "submit_slide_plan" in tool_calls
    print(f"  {'✅' if has_plan else '⚠️'} submit_slide_plan: {'已调用' if has_plan else '未调用'}")

    # ── 阶段 2：生成 ──
    print(f"\n  📋 阶段 2：生成（模拟用户确认）")

    # 设置 session_id context variable（save_slide 需要）
    from app.core.data_path import set_current_session_id as set_data_sid, set_current_user_id
    set_data_sid(session.session_id)
    set_current_user_id(1)

    user_msg_gen = "确认，开始生成。"

    print(f"  👤 确认，开始生成")
    print(f"  🤖 ", end="", flush=True)

    gen_tool_calls = []
    save_slide_count = 0

    async for event in agent.stream_events(user_msg_gen, session=session):
        if event.type == "text_delta":
            content = event.data.get("content", "")
            text_parts.append(content)
            if len("".join(text_parts)) <= 600:
                print(content, end="", flush=True)
        elif event.type == "tool_start":
            name = event.data.get("tool_name", "")
            gen_tool_calls.append(name)
            if name == "save_slide":
                save_slide_count += 1
            print(f"\n  🔧 [{name}]", end="", flush=True)
        elif event.type == "tool_end":
            output = event.data.get("output", "")[:80]
            print(f" → {output}", end="", flush=True)
        elif event.type == "done":
            print()

    elapsed_total = time.time() - start

    print(f"\n  ⏱️  总耗时: {elapsed_total:.1f}s")
    print(f"  📊 生成阶段工具调用: {len(gen_tool_calls)} 次")
    print(f"  📊 save_slide 调用: {save_slide_count} 次")

    # ── 阶段 3：验证 artifact ──
    print(f"\n  📋 阶段 3：验证 artifact 创建")

    from app.tools.ppt_tools import _get_slides_dir
    svg_files = []
    slides_dir = None
    try:
        slides_dir = _get_slides_dir()
        svg_files = sorted(slides_dir.glob("slide_*.svg"))
        print(f"  📂 slides 目录: {slides_dir}")
        print(f"  📄 SVG 文件: {len(svg_files)} 个")
        if svg_files:
            for f in svg_files:
                content = f.read_text()
                has_viewbox = "viewBox" in content
                has_theme = "data-theme" in content
                has_vars = "var(--" in content
                print(f"    {f.name}: viewBox={has_viewbox} theme={has_theme} vars={has_vars}")
    except Exception as e:
        print(f"  ⚠️ 无法获取 slides 目录: {e}")

    # 尝试创建 artifact
    from app.services.ppt_artifact_service import PptArtifactService
    ppt_svc = PptArtifactService()
    if svg_files and slides_dir:
        artifact = await ppt_svc.create_from_slides_dir(session.session_id, slides_dir)
        if artifact:
            print(f"  ✅ Artifact 创建成功: {artifact['title']} ({artifact['slide_count']} 页)")
            print(f"  📄 HTML 长度: {len(artifact['html'])} 字符")
        else:
            print(f"  ❌ Artifact 创建失败: {ppt_svc._last_quality_errors}")
    else:
        print(f"  ⚠️ 没有 SVG 文件，跳过 artifact 创建")

    # 总结
    print(f"\n  {'=' * 40}")
    print(f"  总结:")
    print(f"    规划阶段工具调用: {len(tool_calls)} 次")
    print(f"    submit_slide_plan: {'✅' if has_plan else '⚠️ 未调用'}")
    print(f"    生成阶段 save_slide: {save_slide_count} 次")
    print(f"    总耗时: {elapsed_total:.1f}s")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("\n🧪 PPT 生成流程端到端测试\n")

    await test_submit_slide_plan()
    await test_quality_gate_errors()
    await test_e2e_llm_generation()

    print("\n" + "=" * 60)
    print("  全部测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
