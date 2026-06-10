"""PPT 生成工具 — save_slide 将 SVG 写入会话工作目录"""

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
    """构建下一页计划提示，注入到 save_slide 返回值中。"""
    if not _pending_slide_plan:
        return ""

    next_slide = next(
        (s for s in _pending_slide_plan if s.get("slide_num") == current_slide_num + 1),
        None,
    )
    if not next_slide:
        return ""

    parts = [f"\n\n📋 第{next_slide['slide_num']}页计划："]
    parts.append(f"  布局: {next_slide['layout']}")
    if next_slide.get("title"):
        parts.append(f"  标题: {next_slide['title']}")
    if next_slide.get("content"):
        parts.append(f"  内容: {next_slide['content']}")
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
    async def save_slide(slide_num: int, svg: str) -> str:
        """将一页 SVG 幻灯片写入会话工作目录。新建或覆盖已有页。每页调用一次，调用完所有页后停止即可。

        参数:
          slide_num: 页码（从 1 开始递增）
          svg: 完整的单个 <svg>...</svg> 元素，必须包含 viewBox="0 0 1280 720"
        """
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

        # 注入下一页计划提示（防上下文压缩丢失）
        result += _build_next_slide_hint(slide_num)

        # 注入 spec_lock 摘要（每页都注入，防压缩丢失）
        result += _build_spec_lock_hint()

        # 附带 SVG 预览（前端可提取渲染缩略图）
        result += f"\n<svg_preview>{svg}</svg_preview>"

        return result

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

        summary = "\n".join(
            f"  {s['slide_num']}. {s['layout']} — {s.get('title', '')}"
            for s in plan
        )

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
                "context": f"页面计划：\n{summary}",
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

    if "save_slide" in os.environ.get("PPT_TOOLS_DISABLED", "").split(","):
        del registry._tools["save_slide"]
