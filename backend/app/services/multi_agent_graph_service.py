"""多 Agent 并行协作服务。

基于 wuwei 的 MultiAgentGraph 实现 leader-worker 并行模式：
- Leader Agent 分析任务并分配给合适的 Worker
- Workers 并行执行（asyncio.gather）
- Leader 综合所有结果生成最终输出

典型用法：
    service = MultiAgentGraphService(settings)
    result = await service.run("帮我调研 Python 异步编程最佳实践，并写一份技术报告")

适用场景：
- 需要多步骤、多角色协作的复杂任务
- 需要并行处理的批量任务（如同时生成多页 PPT、同时分析多个文件）
- 需要不同专业视角的综合任务（如调研 + 设计 + 审查）
"""

from __future__ import annotations

import logging
from typing import Any

from wuwei import Agent
from wuwei.agent.multi_agent import MultiAgentGraph, TeamMember
from wuwei.llm import LLMGateway

from app.core.config import Settings

_logger = logging.getLogger("multi_agent_graph")


class MultiAgentGraphService:
    """多 Agent 并行协作服务。

    提供两种使用方式：
    1. 直接调用 `run(task)` 获取结果（适合后端内部调用）
    2. 通过 `build_graph()` 获取编排好的 MultiAgentGraph（适合与 Agent 工具集成）

    Leader 负责分析任务、分配子任务、综合结果。
    Workers 并行执行各自的专业任务。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def _create_leader_agent(self) -> Agent:
        """创建 Leader Agent：负责任务分解与结果综合。"""
        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        return Agent(
            llm=llm,
            tools=None,
            default_system_prompt=(
                "你是多 Agent 协作的总指挥（Leader）。\n"
                "你的职责：\n"
                "1. 分析用户的任务需求\n"
                "2. 将任务分解为子任务，分配给最合适的 Worker\n"
                "3. 综合所有 Worker 的结果，生成最终输出\n\n"
                "任务分配格式（必须使用 YAML）：\n"
                "```yaml\n"
                "[DECISION]\n"
                "assignments:\n"
                "  - member: worker_name\n"
                "    task: 具体任务描述\n"
                "  - member: another_worker\n"
                "    task: 另一个任务\n"
                "[/DECISION]\n"
                "```\n\n"
                "如果任务简单不需要分工，直接回答即可，不必分配。"
                "分配任务时，确保每个 Worker 的任务描述清晰具体。"
            ),
            default_max_steps=3,
            load_builtins=False,
        )

    def _create_research_agent(self) -> Agent:
        """调研 Agent：擅长信息收集、分析、总结。"""
        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        return Agent(
            llm=llm,
            tools=None,
            default_system_prompt=(
                "你是一名专业的调研分析师。你的任务是：\n"
                "1. 深入分析给定的主题\n"
                "2. 收集关键信息和数据\n"
                "3. 提供有洞察力的分析和建议\n"
                "4. 输出结构化的调研报告\n\n"
                "你的输出应该：条理清晰、数据准确、观点有深度。"
            ),
            default_max_steps=5,
            load_builtins=False,
        )

    def _create_writer_agent(self) -> Agent:
        """写作 Agent：擅长文档撰写、内容组织。"""
        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        return Agent(
            llm=llm,
            tools=None,
            default_system_prompt=(
                "你是一名专业的技术写作专家。你的任务是：\n"
                "1. 将复杂的技术内容转化为易懂的文字\n"
                "2. 组织内容结构，确保逻辑清晰\n"
                "3. 使用准确的专业术语\n"
                "4. 输出格式规范的文档\n\n"
                "你的输出应该：结构清晰、语言精准、可直接使用。"
            ),
            default_max_steps=5,
            load_builtins=False,
        )

    def _create_reviewer_agent(self) -> Agent:
        """审查 Agent：擅长质量检查、代码审查。"""
        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        return Agent(
            llm=llm,
            tools=None,
            default_system_prompt=(
                "你是一名严格的质量审查专家。你的任务是：\n"
                "1. 检查内容的准确性和完整性\n"
                "2. 发现潜在的问题和改进建议\n"
                "3. 评估是否符合预期目标\n"
                "4. 提供具体的修改建议\n\n"
                "你的审查应该：客观严谨、建议具体、重点突出。"
            ),
            default_max_steps=3,
            load_builtins=False,
        )

    def build_graph(self) -> MultiAgentGraph:
        """构建多 Agent 协作图。

        返回配置好的 MultiAgentGraph，可直接调用 .run(task) 执行。
        """
        graph = MultiAgentGraph()

        leader = self._create_leader_agent()
        graph.set_leader(leader)

        graph.add_worker(
            name="researcher",
            agent=self._create_research_agent(),
            role="调研分析",
            description="负责信息收集、数据分析、趋势调研。适合需要查找和分析信息的任务。",
        )

        graph.add_worker(
            name="writer",
            agent=self._create_writer_agent(),
            role="内容写作",
            description="负责文档撰写、报告编写、内容组织。适合需要输出文字内容的任务。",
        )

        graph.add_worker(
            name="reviewer",
            agent=self._create_reviewer_agent(),
            role="质量审查",
            description="负责质量检查、错误发现、改进建议。适合需要审核和反馈的任务。",
        )

        graph.set_max_steps(8)
        return graph

    async def run(self, task: str) -> str:
        """执行多 Agent 协作任务，返回最终结果。"""
        _logger.info("MultiAgentGraph starting: task=%s", task[:100])
        graph = self.build_graph()
        try:
            result = await graph.run(task)
            _logger.info("MultiAgentGraph completed: result_len=%d", len(result))
            return result
        except Exception as e:
            _logger.error("MultiAgentGraph failed: %s", e, exc_info=True)
            raise

    async def run_stream(self, task: str):
        """以事件流方式执行多 Agent 协作任务。"""
        _logger.info("MultiAgentGraph stream starting: task=%s", task[:100])
        graph = self.build_graph()
        async for event in graph.run_stream(task):
            yield event


# 全局实例（惰性初始化）
_service_instance: MultiAgentGraphService | None = None


def get_multi_agent_graph_service(settings: Settings | None = None) -> MultiAgentGraphService:
    """获取多 Agent 协作服务的全局实例。"""
    global _service_instance
    if _service_instance is None:
        _service_instance = MultiAgentGraphService(settings)
    return _service_instance
