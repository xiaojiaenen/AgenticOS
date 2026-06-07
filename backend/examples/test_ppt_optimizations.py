"""PPT 优化功能逐项测试

测试本次优化方案中新增的每个功能模块，使用 .env 中的真实 LLM 配置。

测试项：
1. spec_lock 一致性检查
2. 布局纪律检查（footer-rail / accent 密度 / 字号层级）
3. 多画布格式验证
4. 质量门禁（阻断 vs 警告）
5. SVG 质量检查便捷函数
6. 提示词注入（_inject_design_catalog 包含 spec_lock 步骤）
7. 端到端 LLM 生成（用真实 LLM 生成 5 页 PPT 验证全流程）

运行：
    cd backend
    uv run python examples/test_ppt_optimizations.py
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
# Test 1: spec_lock 一致性检查
# ---------------------------------------------------------------------------

def test_spec_lock_consistency():
    """测试 check_spec_lock_consistency 函数"""
    header("测试 1：spec_lock 一致性检查")

    from app.services.ppt.svg_quality_checker import check_spec_lock_consistency

    # Case A: 全部 var(--token)，无硬编码色 — 应通过
    svg_clean = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <rect width="1280" height="720" fill="var(--bg)"/>
      <text x="100" y="200" font-size="32" fill="var(--text-1)">Hello</text>
      <rect x="50" y="300" width="200" height="100" fill="var(--accent)" fill-opacity="0.8"/>
    </svg>"""
    warnings = check_spec_lock_consistency(svg_clean)
    if warnings:
        print(f"  ❌ Case A 应无警告，实际: {warnings}")
    else:
        print("  ✅ Case A: 纯 var(--token) 引用 — 无警告")

    # Case B: 硬编码 accent 色 — 应警告
    svg_bad = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <rect width="1280" height="720" fill="var(--bg)"/>
      <text x="100" y="200" font-size="32" fill="#FF6B35">Warning Text</text>
      <circle cx="640" cy="360" r="100" fill="#8B5CF6"/>
    </svg>"""
    warnings = check_spec_lock_consistency(svg_bad)
    if len(warnings) >= 2:
        print(f"  ✅ Case B: 检出 {len(warnings)} 个硬编码色警告")
        for w in warnings:
            print(f"    → {w}")
    else:
        print(f"  ❌ Case B 应检出 ≥2 个警告，实际: {warnings}")

    # Case C: rgba() 使用 — 应警告
    svg_rgba = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <rect width="1280" height="720" fill="var(--bg)"/>
      <rect x="50" y="50" width="200" height="100" fill="rgba(255,0,0,0.5)"/>
    </svg>"""
    warnings = check_spec_lock_consistency(svg_rgba)
    rgba_warnings = [w for w in warnings if "rgba" in w]
    if rgba_warnings:
        print(f"  ✅ Case C: rgba() 检出 — {rgba_warnings[0]}")
    else:
        print(f"  ❌ Case C 应检出 rgba 警告，实际: {warnings}")

    # Case D: spec_lock 一致性验证
    spec_lock = {
        "colors": {
            "bg": "var(--bg)",
            "accent": "var(--accent)",
        }
    }
    warnings = check_spec_lock_consistency(svg_clean, spec_lock)
    if not warnings:
        print("  ✅ Case D: 带 spec_lock 验证纯 token 引用 — 无警告")
    else:
        print(f"  ❌ Case D 不应有警告: {warnings}")

    print("  ✅ spec_lock 一致性检查测试完成\n")


# ---------------------------------------------------------------------------
# Test 2: 布局纪律检查
# ---------------------------------------------------------------------------

def test_layout_discipline():
    """测试 check_layout_discipline 函数"""
    header("测试 2：布局纪律检查（footer-rail / accent / 字号 / 分组）")

    from app.services.ppt.svg_quality_checker import check_layout_discipline

    # Case A: 正常布局 — 应通过（footer 组不计入 footer-rail 检查）
    svg_good = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <g id="bg">
        <rect width="1280" height="720" fill="var(--bg)"/>
      </g>
      <g id="title">
        <text x="100" y="100" font-size="48" fill="var(--text-1)">Title</text>
        <text x="100" y="160" font-size="24" fill="var(--text-2)">Subtitle</text>
      </g>
      <g id="content">
        <text x="100" y="300" font-size="16" fill="var(--text-2)">Body text</text>
        <text x="100" y="400" font-size="16" fill="var(--text-2)">More body</text>
      </g>
      <g id="footer-chrome">
        <text x="640" y="700" font-size="12" fill="var(--text-3)">01</text>
      </g>
    </svg>"""
    warnings = check_layout_discipline(svg_good)
    if not warnings:
        print("  ✅ Case A: 正常布局（footer chrome 组不计入）— 无警告")
    else:
        print(f"  ❌ Case A 应无警告: {warnings}")

    # Case B: Footer-rail 违规 — 文本侵入 y=680
    svg_footer = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <g id="bg"><rect width="1280" height="720" fill="var(--bg)"/></g>
      <g id="content">
        <text x="100" y="100" font-size="32" fill="var(--text-1)">Title</text>
        <text x="100" y="680" font-size="16" fill="var(--text-2)">Footer text too low</text>
      </g>
    </svg>"""
    warnings = check_layout_discipline(svg_footer)
    footer_warns = [w for w in warnings if "footer-rail" in w.lower()]
    if footer_warns:
        print(f"  ✅ Case B: footer-rail 违规检出 — {footer_warns[0]}")
    else:
        print(f"  ❌ Case B 应检出 footer-rail: {warnings}")

    # Case C: accent 过度使用 — 3 处
    svg_accent = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <g id="bg"><rect width="1280" height="720" fill="var(--bg)"/></g>
      <g id="content">
        <rect x="50" y="50" width="200" height="100" fill="var(--accent)"/>
        <rect x="300" y="50" width="200" height="100" fill="var(--accent)"/>
        <text x="100" y="300" font-size="32" fill="var(--accent)">Third accent</text>
      </g>
    </svg>"""
    warnings = check_layout_discipline(svg_accent)
    accent_warns = [w for w in warnings if "accent" in w.lower()]
    if accent_warns:
        print(f"  ✅ Case C: accent 过度使用检出 — {accent_warns[0]}")
    else:
        print(f"  ❌ Case C 应检出 accent: {warnings}")

    # Case D: 字号过多 — 6 种
    svg_sizes = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <g id="bg"><rect width="1280" height="720" fill="var(--bg)"/></g>
      <g id="content">
        <text x="100" y="100" font-size="72" fill="var(--text-1)">Huge</text>
        <text x="100" y="200" font-size="48" fill="var(--text-1)">Large</text>
        <text x="100" y="300" font-size="32" fill="var(--text-2)">Medium</text>
        <text x="100" y="400" font-size="24" fill="var(--text-2)">Body</text>
        <text x="100" y="500" font-size="18" fill="var(--text-3)">Small</text>
        <text x="100" y="600" font-size="12" fill="var(--text-3)">Tiny</text>
      </g>
    </svg>"""
    warnings = check_layout_discipline(svg_sizes)
    size_warns = [w for w in warnings if "字号" in w]
    if size_warns:
        print(f"  ✅ Case D: 字号过多检出 — {size_warns[0]}")
    else:
        print(f"  ❌ Case D 应检出字号过多: {warnings}")

    # Case E: 裸元素检测
    svg_bare = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <rect width="1280" height="720" fill="var(--bg)"/>
      <text x="100" y="200" font-size="32" fill="var(--text-1)">Bare element</text>
    </svg>"""
    warnings = check_layout_discipline(svg_bare)
    bare_warns = [w for w in warnings if "裸元素" in w]
    if bare_warns:
        print(f"  ✅ Case E: 裸元素检出 — {bare_warns[0]}")
    else:
        print(f"  ⚠️ Case E: 裸元素未检出（简化检查可能遗漏）: {warnings}")

    print("  ✅ 布局纪律检查测试完成\n")


# ---------------------------------------------------------------------------
# Test 3: 多画布格式验证
# ---------------------------------------------------------------------------

def test_canvas_formats():
    """测试 check_canvas_format 函数"""
    header("测试 3：多画布格式验证")

    from app.services.ppt.svg_quality_checker import check_canvas_format, SUPPORTED_VIEWBOXES

    print(f"  支持 {len(SUPPORTED_VIEWBOXES)} 种画布格式:")
    for fmt, vb in SUPPORTED_VIEWBOXES.items():
        print(f"    {fmt:15s} → {vb}")

    # Case A: ppt169 匹配
    err = check_canvas_format("0 0 1280 720", "ppt169")
    if err is None:
        print("  ✅ Case A: 1280×720 = ppt169 匹配")
    else:
        print(f"  ❌ Case A: {err}")

    # Case B: ppt43 匹配
    err = check_canvas_format("0 0 1024 768", "ppt43")
    if err is None:
        print("  ✅ Case B: 1024×768 = ppt43 匹配")
    else:
        print(f"  ❌ Case B: {err}")

    # Case C: xiaohongshu 匹配
    err = check_canvas_format("0 0 1242 1660", "xiaohongshu")
    if err is None:
        print("  ✅ Case C: 1242×1660 = xiaohongshu 匹配")
    else:
        print(f"  ❌ Case C: {err}")

    # Case D: 故意不匹配
    err = check_canvas_format("0 0 1920 1080", "ppt169")
    if err is not None:
        print(f"  ✅ Case D: 不匹配检出 — {err}")
    else:
        print("  ❌ Case D 应检出不匹配")

    # Case E: story 竖屏格式
    err = check_canvas_format("0 0 1080 1920", "story")
    if err is None:
        print("  ✅ Case E: 1080×1920 = story 匹配")
    else:
        print(f"  ❌ Case E: {err}")

    # Case F: 未知格式
    err = check_canvas_format("0 0 1280 720", "unknown_format")
    if err is not None:
        print(f"  ✅ Case F: 未知格式检出 — {err}")
    else:
        print("  ❌ Case F 应检出未知格式")

    print("  ✅ 多画布格式验证测试完成\n")


# ---------------------------------------------------------------------------
# Test 4: 质量门禁（阻断 vs 警告）
# ---------------------------------------------------------------------------

def test_quality_gate():
    """测试质量门禁的阻断逻辑"""
    header("测试 4：质量门禁 — 阻断 vs 警告")

    from app.services.ppt.svg_quality_checker import SVGQualityChecker

    checker = SVGQualityChecker()

    # Case A: 合格 SVG — 应通过
    svg_pass = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <g id="bg"><rect width="1280" height="720" fill="#FFFFFF"/></g>
      <g id="title"><text x="100" y="200" font-size="32" fill="#0F172A">Title</text></g>
      <g id="body"><text x="100" y="400" font-size="16" fill="#334155">Body</text></g>
    </svg>"""
    result = checker.check_svg_string(svg_pass, "test_pass")
    if result["passed"] and not result["errors"]:
        print("  ✅ Case A: 合格 SVG — passed=True, 0 errors")
    else:
        print(f"  ❌ Case A: {result}")

    # Case B: 含 <style> — 应报错
    svg_style = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <style>.foo { fill: red; }</style>
      <rect width="1280" height="720" fill="#FFFFFF"/>
    </svg>"""
    result = checker.check_svg_string(svg_style, "test_style")
    if not result["passed"] and result["errors"]:
        print(f"  ✅ Case B: <style> 被检出 — {result['errors'][0][:80]}")
    else:
        print(f"  ❌ Case B 应报错: {result}")

    # Case C: viewBox 不匹配 — 应报错
    svg_vb = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">
      <rect width="1920" height="1080" fill="#FFFFFF"/>
    </svg>"""
    result = checker.check_svg_string(svg_vb, "test_vb", "ppt169")
    if not result["passed"] and any("viewBox" in e for e in result["errors"]):
        print(f"  ✅ Case C: viewBox 不匹配检出 — {result['errors'][0][:80]}")
    else:
        print(f"  ❌ Case C 应报错: {result}")

    # Case D: XML 格式错误 — 应报错
    svg_bad_xml = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720">
      <text>R&D < 5%</text>
    </svg>"""
    result = checker.check_svg_string(svg_bad_xml, "test_xml")
    if not result["passed"] and any("Invalid XML" in e or "XML" in e for e in result["errors"]):
        print(f"  ✅ Case D: XML 错误检出 — {result['errors'][0][:80]}")
    else:
        print(f"  ⚠️ Case D: XML 错误检测结果: {result}")

    print("  ✅ 质量门禁测试完成\n")


# ---------------------------------------------------------------------------
# Test 5: SVG 质量检查便捷函数
# ---------------------------------------------------------------------------

def test_check_svg_quality():
    """测试 check_svg_quality 便捷函数"""
    header("测试 5：check_svg_quality 便捷函数")

    from app.services.ppt.svg_quality_checker import check_svg_quality

    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-theme="apple">
      <g id="bg"><rect width="1280" height="720" fill="var(--bg)"/></g>
      <g id="header">
        <text x="640" y="180" font-size="18" fill="var(--accent)" text-anchor="middle">SUBTITLE</text>
        <text x="640" y="300" font-size="56" font-weight="800" fill="var(--text-1)" text-anchor="middle">Main Title</text>
      </g>
      <g id="card-1">
        <rect x="60" y="400" width="565" height="260" rx="20" fill="var(--surface)"/>
        <text x="105" y="470" font-size="32" fill="var(--text-1)">Key Metric</text>
        <text x="105" y="530" font-size="56" fill="var(--accent)">+42%</text>
      </g>
      <g id="card-2">
        <rect x="655" y="400" width="565" height="260" rx="20" fill="var(--surface)"/>
        <text x="700" y="470" font-size="32" fill="var(--text-1)">Growth</text>
        <text x="700" y="530" font-size="56" fill="var(--text-1)">3.2x</text>
      </g>
      <g id="footer">
        <text x="640" y="700" font-size="12" fill="var(--text-3)" text-anchor="middle">01 / 08</text>
      </g>
    </svg>"""

    result = check_svg_quality(svg, "cover_test", "ppt169")
    print(f"  文件: {result['file']}")
    print(f"  通过: {result['passed']}")
    print(f"  错误: {result['errors']}")
    print(f"  警告: {result['warnings']}")

    if result["passed"]:
        print("  ✅ 高质量 SVG 通过检查")
    else:
        print(f"  ❌ 高质量 SVG 未通过: {result['errors']}")

    print("  ✅ 便捷函数测试完成\n")


# ---------------------------------------------------------------------------
# Test 6: 提示词注入验证
# ---------------------------------------------------------------------------

def test_prompt_injection():
    """验证 _inject_design_catalog 包含分阶段技能加载指令"""
    header("测试 6：提示词注入验证（分阶段加载 + 主题 + Token）")

    from app.services.agent_service import AgentService
    from app.core.config import get_settings

    settings = get_settings()
    svc = AgentService(settings)

    base_message = "帮我做一个关于 Q3 销售分析的 PPT"
    injected = svc._inject_design_catalog(base_message)

    # 检查分阶段加载指令
    checks = [
        ("阶段 1 技能加载", 'load_skill("ppt-design-guide")' in injected),
        ("模板库加载", 'load_skill("ppt-template-library")' in injected),
        ("阶段 2 工作流技能", 'load_skill("ppt-workflow")' in injected),
        ("阶段 3 质量预算技能", 'load_skill("ppt-quality-budgets")' in injected),
        ("分阶段关键词", "分阶段" in injected or "阶段" in injected),
        ("Token 语义速查", "Token 语义速查" in injected),
        ("主题列表", "theme" in injected.lower()),
        ("主题选择指引", "商业汇报" in injected),
        ("当前时间", "CURRENT TIME" in injected),
    ]

    all_pass = True
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
        if not result:
            all_pass = False

    if all_pass:
        print("\n  ✅ 提示词注入包含所有分阶段加载指令")
    else:
        print("\n  ❌ 提示词注入缺少内容")

    # 检查注入后的总长度（应该比旧版短）
    inject_len = len(injected) - len(base_message)
    print(f"  原始消息长度: {len(base_message)} 字符")
    print(f"  注入后总长度: {len(injected)} 字符")
    print(f"  注入部分长度: {inject_len} 字符")
    if inject_len < 3000:
        print(f"  ✅ 注入部分精简（{inject_len} < 3000 字符）")
    else:
        print(f"  ⚠️ 注入部分较长（{inject_len} 字符）")

    print("  ✅ 提示词注入验证完成\n")


# ---------------------------------------------------------------------------
# Test 7: 端到端 LLM 生成（真实 LLM）
# ---------------------------------------------------------------------------

async def test_e2e_llm_generation():
    """用真实 LLM 生成 5 页 PPT，验证全流程"""
    header("测试 7：端到端 LLM 生成（5 页 PPT）")

    from app.core.config import get_settings
    from wuwei import Agent
    from wuwei.llm import LLMGateway
    from wuwei.tools import ToolRegistry
    from wuwei.middleware import MiddlewareStack

    settings = get_settings()
    print(f"  🔧 LLM: {settings.openai_model} @ {settings.openai_base_url}")

    # 准备 save_slide / read_slide 工具
    import tempfile
    import os

    slides_dir = Path(tempfile.mkdtemp(prefix="ppt_test_"))
    print(f"  📂 临时目录: {slides_dir}")

    saved_slides: dict[int, str] = {}

    def save_slide(slide_num: int, svg: str) -> str:
        """模拟 save_slide 工具"""
        if not svg.strip().startswith("<svg"):
            return f"错误：slide {slide_num} 的内容不是有效的 SVG"
        if "viewBox" not in svg:
            return f"错误：slide {slide_num} 缺少 viewBox"
        path = slides_dir / f"slide_{slide_num}.svg"
        path.write_text(svg, encoding="utf-8")
        saved_slides[slide_num] = svg
        return f"第 {slide_num} 页已保存（共 {len(saved_slides)} 页）"

    def read_slide(slide_num: int) -> str:
        """模拟 read_slide 工具"""
        path = slides_dir / f"slide_{slide_num}.svg"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return f"第 {slide_num} 页不存在（当前共 {len(saved_slides)} 页）"

    # 注册工具
    registry = ToolRegistry()
    registry.register_callable(
        save_slide,
        name="save_slide",
        description="保存一页 SVG 幻灯片。参数：slide_num(页码从1开始), svg(SVG字符串)",
    )
    registry.register_callable(
        read_slide,
        name="read_slide",
        description="读取一页 SVG 幻灯片。参数：slide_num(页码)",
    )

    # 创建 Agent
    from app.prompts import PPT_SYSTEM_PROMPT
    from app.services.agent_service import AgentService

    # 注入设计目录到用户消息
    svc = AgentService(settings)
    user_msg = svc._inject_design_catalog(
        "做一个 5 页的 PPT，主题是「2025 年 AI 行业趋势」，面向投资人。"
    )

    llm = LLMGateway.from_env(max_tokens=8192)
    agent = Agent(
        llm=llm,
        tools=registry,
        default_system_prompt=PPT_SYSTEM_PROMPT,
        default_max_steps=15,
        middleware=MiddlewareStack(),
        load_builtins=False,
    )
    session = agent.create_or_get_session()

    print("\n  👤 做一个 5 页的 PPT，主题是「2025 年 AI 行业趋势」，面向投资人")
    print("  🤖 ", end="", flush=True)

    start = time.time()
    text_parts = []
    tool_calls_count = 0

    async for event in agent.stream_events(user_msg, session=session):
        if event.type == "text_delta":
            content = event.data.get("content", "")
            text_parts.append(content)
            # 只打印前 200 字符概要
            if len("".join(text_parts)) <= 200:
                print(content, end="", flush=True)
        elif event.type == "tool_start":
            tool_name = event.data.get("tool_name", "")
            tool_calls_count += 1
            if tool_name == "save_slide":
                print(f"\n  🔧 [save_slide #{tool_calls_count}]", end="", flush=True)
            elif tool_name == "read_slide":
                print(f"\n  🔧 [read_slide]", end="", flush=True)
            else:
                print(f"\n  🔧 [{tool_name}]", end="", flush=True)
        elif event.type == "tool_end":
            output = event.data.get("output", "")[:60]
            print(f" → {output}", end="", flush=True)
        elif event.type == "done":
            print()

    elapsed = time.time() - start
    full_text = "".join(text_parts)

    print(f"\n  ⏱️  耗时: {elapsed:.1f}s")
    print(f"  📊 工具调用: {tool_calls_count} 次")
    print(f"  📊 已保存幻灯片: {len(saved_slides)} 页")
    print(f"  📊 文本输出: {len(full_text)} 字符")

    # 验证 spec_lock 是否被生成
    has_spec_lock = "spec_lock" in full_text.lower() or "执行锁" in full_text
    print(f"  {'✅' if has_spec_lock else '⚠️'} spec_lock 生成: {'是' if has_spec_lock else '未检测到（LLM 可能以其他形式输出）'}")

    # 验证保存的 slides
    if saved_slides:
        print("\n  📄 已保存幻灯片验证:")
        for num in sorted(saved_slides.keys()):
            svg = saved_slides[num]
            has_theme = "data-theme=" in svg
            has_viewbox = "viewBox=" in svg
            has_notes = "<!-- notes:" in svg
            has_groups = "<g " in svg
            uses_vars = "var(--" in svg
            no_hex_accent = "#6366f1" not in svg and "#4f46e5" not in svg

            issues = []
            if not has_theme:
                issues.append("缺 data-theme")
            if not has_viewbox:
                issues.append("缺 viewBox")
            if not has_notes:
                issues.append("缺 notes")
            if not has_groups:
                issues.append("缺 <g> 分组")
            if not uses_vars:
                issues.append("未使用 var(--token)")
            if not no_hex_accent:
                issues.append("使用了禁用 indigo")

            status = "✅" if not issues else "⚠️"
            detail = f"theme={has_theme} vb={has_viewbox} notes={has_notes} <g>={has_groups} var={uses_vars}"
            print(f"    {status} slide_{num}.svg ({len(svg)} chars) — {detail}")
            if issues:
                print(f"       ⚠️ 问题: {', '.join(issues)}")

        # 对所有保存的 slides 运行质量检查
        from app.services.ppt.svg_quality_checker import (
            check_spec_lock_consistency,
            check_layout_discipline,
            check_canvas_format,
        )
        print("\n  🔍 质量检查:")
        for num in sorted(saved_slides.keys()):
            svg = saved_slides[num]
            spec_w = check_spec_lock_consistency(svg)
            layout_w = check_layout_discipline(svg)
            vb_match = re.search(r'viewBox="([^"]+)"', svg)
            vb_err = check_canvas_format(vb_match.group(1), "ppt169") if vb_match else "缺 viewBox"

            issues = len(spec_w) + len(layout_w) + (1 if vb_err else 0)
            status = "✅" if issues == 0 else "⚠️"
            print(f"    {status} slide_{num}: spec_lock={len(spec_w)}w layout={len(layout_w)}w viewBox={'✓' if not vb_err else '✗'}")
            for w in spec_w[:2] + layout_w[:2]:
                print(f"       → {w[:80]}")
    else:
        print("  ❌ 未保存任何幻灯片 — LLM 可能未调用 save_slide")

    print(f"\n  ✅ 端到端测试完成\n")


# ---------------------------------------------------------------------------
# Test 8: 提示词验证（PPT_SYSTEM_PROMPT 包含新增内容）
# ---------------------------------------------------------------------------

def test_prompt_content():
    """验证 PPT_SYSTEM_PROMPT 精简后仍包含核心规则，并引用 4 个技能"""
    header("测试 8：PPT_SYSTEM_PROMPT 精简验证")

    from app.prompts import PPT_SYSTEM_PROMPT

    # 核心规则必须在 system prompt 中（不能全部移到技能）
    core_checks = [
        ("save_slide 最高优先级", "save_slide" in PPT_SYSTEM_PROMPT),
        ("viewBox 要求", "viewBox" in PPT_SYSTEM_PROMPT),
        ("data-theme 要求", "data-theme" in PPT_SYSTEM_PROMPT),
        ("var(--token) 颜色", "var(--token)" in PPT_SYSTEM_PROMPT),
        ("禁止元素列表", "禁止元素" in PPT_SYSTEM_PROMPT or "foreignObject" in PPT_SYSTEM_PROMPT),
        ("元素分组 <g id>", "<g id" in PPT_SYSTEM_PROMPT),
        ("notes 演讲者备注", "notes" in PPT_SYSTEM_PROMPT),
    ]

    # 技能引用必须存在
    skill_checks = [
        ("引用 ppt-design-guide", "ppt-design-guide" in PPT_SYSTEM_PROMPT),
        ("引用 ppt-template-library", "ppt-template-library" in PPT_SYSTEM_PROMPT),
        ("引用 ppt-workflow", "ppt-workflow" in PPT_SYSTEM_PROMPT),
        ("引用 ppt-quality-budgets", "ppt-quality-budgets" in PPT_SYSTEM_PROMPT),
        ("分阶段加载说明", "按工作流阶段" in PPT_SYSTEM_PROMPT or "阶段" in PPT_SYSTEM_PROMPT),
    ]

    all_pass = True
    for name, result in core_checks + skill_checks:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
        if not result:
            all_pass = False

    # 验证精简效果
    prompt_len = len(PPT_SYSTEM_PROMPT)
    print(f"\n  📊 PPT_SYSTEM_PROMPT 长度: {prompt_len} 字符")
    if prompt_len < 4000:
        print(f"  ✅ 精简成功（{prompt_len} < 4000 字符，原 ~12000 字符）")
    else:
        print(f"  ⚠️ 仍较长（{prompt_len} 字符）")

    # 验证详细规则已移至技能文件
    from pathlib import Path
    skills_dir = Path(__file__).resolve().parent.parent.parent / "data" / "skills"
    for skill_name in ["ppt-workflow", "ppt-quality-budgets"]:
        skill_path = skills_dir / skill_name / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text("utf-8")
            print(f"  ✅ {skill_name} 技能文件存在（{len(content)} 字符）")
        else:
            print(f"  ❌ {skill_name} 技能文件不存在: {skill_path}")
            all_pass = False

    if all_pass:
        print(f"\n  ✅ PPT_SYSTEM_PROMPT 精简验证通过")
    else:
        print(f"\n  ❌ 部分检查未通过")

    print("  ✅ 提示词内容验证完成\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

import re  # noqa: E402


async def main():
    header("AgenticOS PPT 优化功能逐项测试")
    print("  使用 .env 中的真实 LLM 配置")
    from app.core.config import get_settings
    s = get_settings()
    print(f"  🔧 Model: {s.openai_model} @ {s.openai_base_url}")

    # 同步测试（不需要 LLM）
    test_spec_lock_consistency()
    test_layout_discipline()
    test_canvas_formats()
    test_quality_gate()
    test_check_svg_quality()
    test_prompt_injection()
    test_prompt_content()

    # 异步测试（需要真实 LLM）
    await test_e2e_llm_generation()

    header("全部测试完成 ✅")


if __name__ == "__main__":
    asyncio.run(main())
