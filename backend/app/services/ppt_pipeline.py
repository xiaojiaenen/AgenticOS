"""StateGraph PPT 生成流水线

使用 wuwei 2.2.0 的 StateGraph 编排 PPT 生成流程：
选择主题 → 加载模板 → 逐页生成 → 质量检查 → Token解析 → 导出PPTX

每个步骤有明确的输入输出，比 Agent 自由发挥更可控。
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from wuwei.graph import StateGraph, State

_logger = logging.getLogger("ppt_pipeline")


@dataclass
class PptPipelineState:
    """PPT Pipeline 状态"""
    # 输入
    user_message: str = ""
    session_id: str = ""
    theme: str = "openai"
    page_count: int = 10

    # 中间状态
    pages: list[dict] = field(default_factory=list)
    svgs: list[str] = field(default_factory=list)
    validated_svgs: list[str] = field(default_factory=list)

    # 输出
    artifact: dict | None = None
    error: str | None = None

    # 元数据
    step: int = 0
    metadata: dict = field(default_factory=dict)


class PptPipeline:
    """基于 StateGraph 的 PPT 生成流水线"""

    def __init__(self):
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建 PPT 生成状态图"""
        graph = StateGraph(PptPipelineState)

        # 添加节点
        graph.add_node("plan", self._plan_node)
        graph.add_node("generate_slides", self._generate_slides_node)
        graph.add_node("validate", self._validate_node)
        graph.add_node("create_artifact", self._create_artifact_node)

        # 添加边
        graph.add_edge("plan", "generate_slides")
        graph.add_edge("generate_slides", "validate")
        graph.add_conditional_edges(
            "validate",
            self._should_retry,
            {"retry": "generate_slides", "done": "create_artifact"}
        )
        graph.add_edge("create_artifact", "__end__")

        # 设置入口
        graph.set_entry_point("plan")

        return graph.compile()

    async def _plan_node(self, state: PptPipelineState) -> PptPipelineState:
        """规划节点：使用 wuwei Planner 分析需求，确定页面结构"""
        _logger.info(f"Planning PPT: {state.user_message[:50]}...")

        try:
            from wuwei import LLMGateway, Planner
            from wuwei.parsers import PydanticOutputParser
            from pydantic import BaseModel

            llm = LLMGateway.from_env()
            planner = Planner(llm)

            # 使用 wuwei Planner 规划任务
            tasks = await planner.plan_task(
                f"创建一个关于'{state.user_message}'的 PPT，主题：{state.theme}，页数：{state.page_count}"
            )

            # 将 Task 转换为页面结构
            state.pages = []
            for task in tasks:
                page = {
                    "type": getattr(task, "type", "content"),
                    "title": getattr(task, "title", "未命名页面"),
                    "layout": getattr(task, "layout", "bullets"),
                }
                state.pages.append(page)

            if not state.pages:
                # Planner 没有返回任务，使用默认结构
                state.pages = [
                    {"type": "cover", "title": state.user_message[:30]},
                    {"type": "section", "title": "概览"},
                    {"type": "content", "title": "核心内容", "layout": "bullets"},
                    {"type": "ending", "title": "总结"},
                ]

            state.step = 1
            _logger.info(f"Planned {len(state.pages)} pages")

        except Exception as e:
            _logger.error(f"Planning failed: {e}")
            state.error = f"规划失败: {e}"

        return state

    async def _generate_slides_node(self, state: PptPipelineState) -> PptPipelineState:
        """生成节点：逐页生成 SVG 并写入磁盘"""
        _logger.info(f"Generating {len(state.pages)} slides...")

        from wuwei import LLMGateway
        from wuwei.core.message import SystemMessage, HumanMessage
        from pathlib import Path
        from app.core.data_path import PPT_SESSIONS_DIR

        llm = LLMGateway.from_env()
        svgs = []

        # 确保 slides 目录存在
        slides_dir = PPT_SESSIONS_DIR / state.session_id
        slides_dir.mkdir(parents=True, exist_ok=True)

        for i, page in enumerate(state.pages):
            try:
                response = await llm.generate(
                    messages=[
                        SystemMessage(content="你是 SVG 幻灯片设计专家，只输出 SVG 代码。"),
                        HumanMessage(content=f"生成第 {i+1} 页 SVG：{page}，主题：{state.theme}"),
                    ],
                )
                content = response.message.content
                if "<svg" in content:
                    start = content.index("<svg")
                    end = content.rfind("</svg>") + 6
                    svg = content[start:end]
                    svgs.append(svg)
                    # 写入磁盘
                    slide_path = slides_dir / f"slide_{i + 1}.svg"
                    slide_path.write_text(svg, encoding="utf-8")
                    _logger.info(f"Saved slide {i + 1} to {slide_path}")
            except Exception as e:
                _logger.error(f"Slide generation failed: {e}")

        state.svgs = svgs
        state.step = 2
        return state

    async def _validate_node(self, state: PptPipelineState) -> PptPipelineState:
        """验证节点：检查 SVG 质量"""
        _logger.info(f"Validating {len(state.svgs)} slides...")

        import re
        viewboxes = set()
        valid_svgs = []

        for svg in state.svgs:
            m = re.search(r'viewBox=["\']([^"\']+)["\']', svg)
            if m:
                viewboxes.add(m.group(1))
                valid_svgs.append(svg)

        if len(viewboxes) <= 1 and len(valid_svgs) >= 3:
            state.validated_svgs = valid_svgs
            state.step = 3
        else:
            state.error = f"验证失败：viewBox 不一致或页数不足"

        return state

    def _should_retry(self, state: PptPipelineState) -> str:
        """判断是否需要重试"""
        if state.error and state.step < 3:
            return "retry"
        return "done"

    async def _create_artifact_node(self, state: PptPipelineState) -> PptPipelineState:
        """创建 Artifact 节点"""
        _logger.info(f"Creating artifact with {len(state.validated_svgs)} slides...")

        if not state.validated_svgs:
            state.error = "没有有效的 SVG 页面"
            return state

        # 这里可以调用 PptArtifactService 创建 artifact
        state.artifact = {
            "slide_count": len(state.validated_svgs),
            "theme": state.theme,
            "svgs": state.validated_svgs,
        }
        state.step = 4
        return state

    async def run(self, user_message: str, session_id: str, theme: str = "openai") -> dict:
        """运行 PPT 生成流水线"""
        initial_state = PptPipelineState(
            user_message=user_message,
            session_id=session_id,
            theme=theme,
        )

        final_state = await self.graph.ainvoke(initial_state)

        if final_state.error:
            return {"success": False, "error": final_state.error}

        return {
            "success": True,
            "artifact": final_state.artifact,
            "slide_count": final_state.artifact.get("slide_count", 0) if final_state.artifact else 0,
        }
