"""PPT 生成工具 — save_slide 将 SVG 写入会话工作目录"""

import json
import os
from pathlib import Path

from wuwei.tools import ToolRegistry

from app.core.data_path import (
    PPT_SESSIONS_DIR,
    get_current_session_id,
    get_current_user_id,
    next_version_dir,
)

# ---------------------------------------------------------------------------
# slides directory — uses versioned naming: u<user_id>_s<session_id>_v<N>
# ---------------------------------------------------------------------------
_slides_dir_cache: Path | None = None
_pending_slide_plan: list[dict] | None = None
_spec_lock_summary: str = ""


def reset_slides_dir_cache() -> None:
    """Reset the cached slides dir (called at the start of each stream).

    注意：不再重置 _pending_slide_plan 和 _spec_lock_summary，
    它们需要跨 stream 保持，防止上下文压缩后丢失计划和设计参数。
    """
    global _slides_dir_cache
    _slides_dir_cache = None


def pop_pending_slide_plan() -> list[dict] | None:
    """Retrieve and clear the pending slide plan submitted by submit_slide_plan."""
    global _pending_slide_plan
    plan = _pending_slide_plan
    _pending_slide_plan = None
    return plan


def _get_slides_dir() -> Path:
    global _slides_dir_cache
    if _slides_dir_cache is not None and _slides_dir_cache.exists():
        return _slides_dir_cache

    session_id = get_current_session_id()
    if not session_id:
        raise RuntimeError("save_slide: session_id 未设置，无法确定写入目录")

    user_id = get_current_user_id()
    # Check if there's already a directory for this user+session
    if PPT_SESSIONS_DIR.exists():
        for child in sorted(PPT_SESSIONS_DIR.iterdir()):
            if not child.is_dir():
                continue
            parts = child.name.split("_v", 1)
            if len(parts) == 2 and parts[0] == f"u{user_id}_s{session_id}":
                _slides_dir_cache = child
                child.mkdir(parents=True, exist_ok=True)
                return child

    # No existing dir — create next version
    slides_dir = next_version_dir(PPT_SESSIONS_DIR, user_id, session_id)
    slides_dir.mkdir(parents=True, exist_ok=True)
    _slides_dir_cache = slides_dir
    return slides_dir


def _count_slides(slides_dir: Path) -> int:
    if not slides_dir.exists():
        return 0
    return len([f for f in slides_dir.iterdir() if f.suffix == ".svg"])


def _build_next_slide_hint(current_slide_num: int) -> str:
    """构建布局约束提示，注入到 save_slide 返回值中。

    硬约束格式：每页注入下一页的布局/标题/内容，禁止偏离。
    每 5 页注入完整剩余计划摘要。
    """
    if not _pending_slide_plan:
        return ""

    # 每 5 页注入完整剩余计划（防压缩丢失）
    if current_slide_num % 5 == 0:
        remaining = [s for s in _pending_slide_plan if s.get("slide_num", 0) > current_slide_num]
        if remaining:
            parts = [f"\n\n⚠️ 剩余计划约束（{len(remaining)} 页，必须严格遵守）："]
            for s in remaining:
                line = f"  P{s['slide_num']}: {s['layout']} — {s.get('title', '')}"
                if s.get("content"):
                    c = s["content"][:80] + ("..." if len(s["content"]) > 80 else "")
                    line += f"\n      内容: {c}"
                parts.append(line)
            parts.append("  → 禁止跳过、替换或合并页面布局。违反约束 = 任务失败。")
            return "\n".join(parts)

    # 每页注入下一页布局约束
    next_slide = next(
        (s for s in _pending_slide_plan if s.get("slide_num") == current_slide_num + 1),
        None,
    )
    if not next_slide:
        return ""

    parts = [f"\n\n⚠️ 下一页生成约束（必须严格遵守）："]
    parts.append(f"  第{next_slide['slide_num']}页 layout: {next_slide['layout']}")
    if next_slide.get("title"):
        parts.append(f"  第{next_slide['slide_num']}页 title: {next_slide['title']}")
    if next_slide.get("content"):
        parts.append(f"  第{next_slide['slide_num']}页 content: {next_slide['content']}")
    parts.append(f"  → 禁止用其他布局替代。生成前必须先读取 {next_slide['layout']} 模板。")
    return "\n".join(parts)


def _build_batch_plan_hint(slides: list[dict]) -> str:
    """为批量保存构建本批次所有页的布局约束提示。"""
    if not _pending_slide_plan or not slides:
        return ""

    slide_nums = [s.get("slide_num", 0) for s in slides]
    planned = [s for s in _pending_slide_plan if s.get("slide_num") in slide_nums]
    if not planned:
        return ""

    parts = [f"\n\n⚠️ 本批次布局约束（{len(planned)} 页，必须严格遵守）："]
    for s in planned:
        line = f"  第{s['slide_num']}页: {s['layout']} — {s.get('title', '')}"
        if s.get("content"):
            c = s["content"][:60] + ("..." if len(s["content"]) > 60 else "")
            line += f" | {c}"
        parts.append(line)
    parts.append("  → 每页必须按指定布局生成，禁止替换。违反约束 = 任务失败。")
    return "\n".join(parts)


def _build_spec_lock_hint() -> str:
    """构建 spec_lock 摘要提示，注入到 save_slide 返回值中。"""
    if not _spec_lock_summary:
        return ""
    return f"\n\n🔒 设计参数：{_spec_lock_summary}"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------
def register_ppt_tools(registry: ToolRegistry) -> None:

    @registry.tool(display_name="读取幻灯片")
    async def read_slide(slide_num: int) -> str:
        """读取已有幻灯片的 SVG 内容，用于修改前查看。

        参数:
          slide_num: 要读取的页码（从 1 开始）
        """
        slides_dir = _get_slides_dir()
        file_path = slides_dir / f"slide_{slide_num}.svg"
        if not file_path.exists():
            existing = _count_slides(slides_dir)
            return f"第 {slide_num} 页不存在（当前共 {existing} 页）"
        return file_path.read_text(encoding="utf-8")

    @registry.tool(display_name="保存幻灯片")
    async def save_slide(slide_num: int, svg: str, notes: str = "") -> str:
        """将一页 SVG 幻灯片写入会话工作目录。新建或覆盖已有页。每页调用一次，调用完所有页后停止即可。

        参数:
          slide_num: 页码（从 1 开始递增）
          svg: 完整的单个 <svg>...</svg> 元素，必须包含 viewBox="0 0 1280 720"
          notes: 演讲者备注（150-300字，口语化），可选
        """
        import re

        if not svg.strip().startswith("<svg"):
            return "错误：svg 参数必须以 <svg> 开头"
        if "viewBox" not in svg:
            return '错误：svg 必须包含 viewBox 属性，例如 viewBox="0 0 1280 720"'

        slides_dir = _get_slides_dir()
        file_path = slides_dir / f"slide_{slide_num}.svg"
        existed = file_path.exists()
        file_path.write_text(svg, encoding="utf-8")
        count = _count_slides(slides_dir)
        action = "已更新" if existed else "已保存"
        result = f"第 {slide_num} 页{action}（共 {count} 页）"

        # 保存演讲者备注
        if notes:
            notes_file = slides_dir / f"slide_{slide_num}.notes.md"
            notes_file.write_text(notes.strip(), encoding="utf-8")
            result += f"\n📝 演讲者备注已保存"
        else:
            # 尝试从 SVG 注释中提取备注
            notes_match = re.search(r'<!--\s*notes:\s*(.*?)\s*-->', svg, re.DOTALL)
            if notes_match:
                extracted_notes = notes_match.group(1).strip()
                if extracted_notes:
                    notes_file = slides_dir / f"slide_{slide_num}.notes.md"
                    notes_file.write_text(extracted_notes, encoding="utf-8")
                    result += f"\n📝 演讲者备注已从 SVG 注释中提取"

        # 自动保存检查点（用于分段执行）
        try:
            from app.services.ppt.resume_service import get_resume_service
            from app.services.agent_service import _current_session_id

            session_id = _current_session_id.get()
            if session_id and _pending_slide_plan:
                resume_service = get_resume_service()
                # 获取已完成的页码列表
                completed = []
                for f in slides_dir.glob("slide_*.svg"):
                    match = re.search(r'slide_(\d+)', f.name)
                    if match:
                        completed.append(int(match.group(1)))

                resume_service.save_checkpoint(
                    session_id=session_id,
                    slide_num=slide_num,
                    spec_lock=_spec_lock_summary,
                    slide_plan=_pending_slide_plan,
                    completed_slides=sorted(completed),
                )
        except Exception as e:
            # 检查点保存失败不影响主流程
            pass

        # 注入下一页计划提示（防上下文压缩丢失）
        result += _build_next_slide_hint(slide_num)

        # 注入 spec_lock 摘要（每页都注入，防压缩丢失）
        result += _build_spec_lock_hint()

        # 附带 SVG 预览（前端可提取渲染缩略图）
        result += f"\n<svg_preview>{svg}</svg_preview>"

        return result

    @registry.tool(display_name="批量保存幻灯片")
    async def save_slides_batch(slides_json: str) -> str:
        """批量保存多页幻灯片，减少 LLM 调用次数（推荐每 3 页一批）。

        参数:
          slides_json: JSON 数组字符串，每个元素包含:
            - slide_num(int): 页码（从 1 开始递增）
            - svg(str): 完整的 <svg>...</svg> 元素
            - notes(str,可选): 演讲者备注（150-300字，口语化）
          示例: '[{"slide_num":1,"svg":"<svg>...</svg>","notes":"备注"},...]'

        使用场景：一次生成 3 页幻灯片，减少 LLM 调用次数 40-60%。
        """
        import re

        try:
            slides = json.loads(slides_json)
            if not isinstance(slides, list):
                return "错误：slides_json 必须是 JSON 数组"
        except json.JSONDecodeError as e:
            return f"错误：JSON 解析失败 — {e}"

        slides_dir = _get_slides_dir()
        results = []

        for slide in slides:
            slide_num = slide.get("slide_num")
            svg = slide.get("svg", "")
            notes = slide.get("notes", "")

            if not slide_num:
                results.append(f"❌ 缺少 slide_num")
                continue

            if not svg.strip().startswith("<svg"):
                results.append(f"❌ 第 {slide_num} 页：svg 必须以 <svg> 开头")
                continue

            if "viewBox" not in svg:
                results.append(f"❌ 第 {slide_num} 页：svg 必须包含 viewBox 属性")
                continue

            file_path = slides_dir / f"slide_{slide_num}.svg"
            existed = file_path.exists()
            file_path.write_text(svg, encoding="utf-8")

            action = "已更新" if existed else "已保存"
            results.append(f"✅ 第 {slide_num} 页{action}")

            # 保存演讲者备注
            if notes:
                notes_file = slides_dir / f"slide_{slide_num}.notes.md"
                notes_file.write_text(notes.strip(), encoding="utf-8")
            else:
                # 尝试从 SVG 注释中提取备注
                notes_match = re.search(r'<!--\s*notes:\s*(.*?)\s*-->', svg, re.DOTALL)
                if notes_match:
                    extracted_notes = notes_match.group(1).strip()
                    if extracted_notes:
                        notes_file = slides_dir / f"slide_{slide_num}.notes.md"
                        notes_file.write_text(extracted_notes, encoding="utf-8")

        count = _count_slides(slides_dir)
        summary = "\n".join(results)

        # 注入本批次布局约束
        batch_hint = _build_batch_plan_hint(slides)

        # 注入 spec_lock 摘要
        spec_hint = _build_spec_lock_hint()

        # 注入下一页计划提示（取最后一页的 slide_num）
        last_slide_num = max((s.get("slide_num", 0) for s in slides), default=0)
        plan_hint = _build_next_slide_hint(last_slide_num)

        # 为每页附带 SVG 预览（前端可提取渲染缩略图）
        svg_previews = ""
        for slide in slides:
            svg = slide.get("svg", "")
            sn = slide.get("slide_num", 0)
            if svg and sn:
                svg_previews += f"\n<svg_preview>{svg}</svg_preview>"

        return f"批量保存完成（共 {count} 页）：\n{summary}{batch_hint}{spec_hint}{plan_hint}{svg_previews}"

    @registry.tool(display_name="读取演讲者备注")
    async def read_notes(slide_num: int) -> str:
        """读取指定幻灯片的演讲者备注。

        参数:
          slide_num: 要读取备注的页码（从 1 开始）
        """
        slides_dir = _get_slides_dir()
        notes_file = slides_dir / f"slide_{slide_num}.notes.md"

        if not notes_file.exists():
            # 尝试从 SVG 注释中提取
            svg_file = slides_dir / f"slide_{slide_num}.svg"
            if svg_file.exists():
                import re
                svg_content = svg_file.read_text(encoding="utf-8")
                notes_match = re.search(r'<!--\s*notes:\s*(.*?)\s*-->', svg_content, re.DOTALL)
                if notes_match:
                    return f"第 {slide_num} 页备注（从 SVG 注释提取）：\n\n{notes_match.group(1).strip()}"
            return f"第 {slide_num} 页没有演讲者备注"

        return f"第 {slide_num} 页备注：\n\n{notes_file.read_text(encoding='utf-8')}"

    @registry.tool(display_name="提交设计参数")
    async def submit_spec_lock(colors: str, fonts: str, icon_library: str) -> str:
        """提交 spec_lock 的核心设计参数，确保后续页面生成不偏离。

        在输出 spec_lock 表格后调用此工具，将关键参数持久化。
        每页生成时会自动注入这些参数，防止上下文压缩后丢失。

        参数:
          colors: 颜色方案摘要，如 "bg:#ffffff, primary:#1a1a2e, accent:#e94560, text:#333"
          fonts: 字体方案摘要，如 "title:Playfair Display 48px bold, body:Inter 16px"
          icon_library: 图标库名，如 "chunk-filled" 或 "tabler-outline"
        """
        global _spec_lock_summary
        _spec_lock_summary = f"颜色:{colors} | 字体:{fonts} | 图标:{icon_library}"
        return f"设计参数已锁定：{_spec_lock_summary}"

    @registry.tool(display_name="提交幻灯片计划")
    async def submit_slide_plan(slides: str) -> str:
        """在规划阶段结束时提交结构化的页面计划（JSON 数组），并自动触发用户确认。

        参数:
          slides: JSON 数组字符串，每个元素必须包含:
            - slide_num(int): 页码
            - layout(str): 布局类型
            - title(str): 页面标题
            - content(str): 该页需要展示的具体内容/数据（从参考文档提取，不可编造）
            - notes(str,可选): 备注
          示例: '[{"slide_num":1,"layout":"cover","title":"AI科普","content":"封面标题: AI科普 | 副标题: 入门指南","notes":"封面"}]'

        调用时机：spec_lock 输出、调用 submit_spec_lock 之后。工具会自动弹出决策面板等待用户确认。
        """
        import json
        import logging
        global _pending_slide_plan

        _logger = logging.getLogger("ppt_tools.submit_slide_plan")

        try:
            plan = json.loads(slides)
            if not isinstance(plan, list):
                return "错误：slides 必须是 JSON 数组"
            for item in plan:
                if not isinstance(item, dict) or "slide_num" not in item or "layout" not in item:
                    return "错误：每个元素必须包含 slide_num 和 layout 字段"
                if "content" not in item:
                    return (
                        "错误：每个元素必须包含 content 字段（从参考文档提取的具体数据）。\n"
                        "示例: {\"slide_num\":2, \"layout\":\"bullets\", \"title\":\"市场背景\", "
                        "\"content\":\"• 全球AI市场规模5500亿\\n• 年增长率42%\"}\n"
                        "如果没有参考文档，content 可以是该页要展示的核心信息摘要。"
                    )
        except json.JSONDecodeError as e:
            return f"错误：JSON 解析失败 — {e}"

        # 持久化到模块级缓存（不再被 reset_slides_dir_cache 重置）
        _pending_slide_plan = plan

        # 构建完整的计划展示（含布局、标题、内容）
        plan_lines = []
        for s in plan:
            plan_lines.append(f"第{s['slide_num']}页 [{s['layout']}] {s.get('title', '')}")
            if s.get("content"):
                plan_lines.append(f"  内容: {s['content']}")
            plan_lines.append("")
        summary = "\n".join(plan_lines).strip()

        # 自动调用 ask_user_decision 等待用户确认
        try:
            from app.tools.decision_tools import (
                _decision_queues,
                _decision_futures,
                DECISION_TIMEOUT_SECONDS,
            )
            import asyncio
            import uuid
            from app.services.agent_service import _current_session_id

            session_id = _current_session_id.get() or "default"
            decision_id = str(uuid.uuid4())[:8]

            # 构建决策事件
            decision_event = {
                "decision_id": decision_id,
                "session_id": session_id,
                "type": "user_decision",
                "question": f"已规划 {len(plan)} 页幻灯片，确认开始生成？",
                "options": ["确认开始生成", "修改方案"],
                "context": summary,
                "allow_custom": False,
                "status": "pending",
            }

            # 推送到决策队列
            if session_id not in _decision_queues:
                _decision_queues[session_id] = []
            _decision_queues[session_id].append(decision_event)

            _logger.info(
                "PPT slide plan submitted: %d slides, decision_id=%s, waiting for user",
                len(plan), decision_id,
            )

            # 创建 Future 并阻塞等待用户响应
            loop = asyncio.get_running_loop()
            future: asyncio.Future[str] = loop.create_future()
            _decision_futures[decision_id] = future

            try:
                answer = await asyncio.wait_for(future, timeout=DECISION_TIMEOUT_SECONDS)
                _logger.info("PPT decision resolved: %s → %s", decision_id, answer)

                if "确认" in answer or "开始生成" in answer:
                    return (
                        f"已提交 {len(plan)} 页计划，用户已确认。\n"
                        f"页面列表：\n{summary}\n"
                        f"开始生成幻灯片。"
                    )
                else:
                    return (
                        f"已提交 {len(plan)} 页计划，用户要求修改。\n"
                        f"页面列表：\n{summary}\n"
                        f"请根据用户反馈调整方案。"
                    )
            except asyncio.TimeoutError:
                _decision_futures.pop(decision_id, None)
                _logger.warning("PPT decision timeout: %s", decision_id)
                return (
                    f"已提交 {len(plan)} 页计划，但用户未在规定时间内确认。\n"
                    f"页面列表：\n{summary}\n"
                    f"请等待用户回复。"
                )

        except Exception as exc:
            _logger.warning("Failed to trigger decision panel: %s", exc)
            # 降级：返回普通确认提示
            return (
                f"已提交 {len(plan)} 页计划：\n{summary}\n"
                f'请回复"确认"开始生成，或提出修改意见。'
            )

    @registry.tool(display_name="继续生成PPT")
    async def resume_ppt(from_slide: int = 0) -> str:
        """从上次中断的地方继续生成 PPT。

        参数:
            from_slide: 从第几页开始（0=自动检测下一个未完成的页）

        返回: 恢复状态信息，包括 spec_lock 和剩余页面计划
        """
        from app.services.ppt.resume_service import get_resume_service
        from app.services.agent_service import _current_session_id

        session_id = _current_session_id.get() or "default"
        resume_service = get_resume_service()

        checkpoint = resume_service.load_checkpoint(session_id)
        if not checkpoint:
            return "未找到检查点，请开始新的 PPT 生成任务。"

        if from_slide == 0:
            # 自动找到下一个未完成的页
            next_slide = resume_service.get_next_slide(session_id)
            if next_slide is None:
                return "所有页面已生成完成！"
            from_slide = next_slide

        # 恢复 spec_lock
        global _spec_lock_summary
        _spec_lock_summary = checkpoint.spec_lock

        # 恢复 slide_plan
        global _pending_slide_plan
        _pending_slide_plan = checkpoint.slide_plan

        hint = resume_service.get_resume_hint(session_id)

        return f"""已恢复检查点！

{hint}

从第 {from_slide} 页开始继续生成。
spec_lock 已恢复：{checkpoint.spec_lock}

请调用 save_slide 逐页生成剩余页面。"""

    @registry.tool(display_name="查看生成进度")
    async def check_ppt_progress() -> str:
        """查看当前 PPT 生成进度。

        返回: 已完成页数、剩余页数、检查点状态
        """
        from app.services.ppt.resume_service import get_resume_service
        from app.services.agent_service import _current_session_id

        session_id = _current_session_id.get() or "default"
        resume_service = get_resume_service()

        checkpoint = resume_service.load_checkpoint(session_id)
        if not checkpoint:
            return "未找到检查点，请开始新的 PPT 生成任务。"

        completed = checkpoint.completed_slides
        total = len(checkpoint.slide_plan)
        remaining = [
            s for s in checkpoint.slide_plan
            if s.get("slide_num") not in completed
        ]

        lines = [
            f"**PPT 生成进度**",
            f"",
            f"总页数: {total}",
            f"已完成: {len(completed)} 页",
            f"剩余: {len(remaining)} 页",
            f"",
            f"**已完成页面**: {', '.join(f'第{n}页' for n in sorted(completed))}",
        ]

        if remaining:
            lines.append("")
            lines.append("**剩余页面**:")
            for s in remaining:
                lines.append(f"  - 第{s['slide_num']}页: {s.get('layout', 'unknown')} - {s.get('title', '无标题')}")

        return "\n".join(lines)

    if "save_slide" in os.environ.get("PPT_TOOLS_DISABLED", "").split(","):
        del registry._tools["save_slide"]
