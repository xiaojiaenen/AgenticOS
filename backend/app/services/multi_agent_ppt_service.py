"""Multi-Agent PPT 生成服务

使用 wuwei 2.2.0 的 Swarm + TeamMember 实现三 Agent 协作：
- Planner Agent：规划 PPT 结构（页面数、布局选择）
- Designer Agent：逐页生成 SVG
- Reviewer Agent：检查 SVG 质量

流程：
1. Planner 分析用户需求，输出 PPT 大纲
2. Designer 根据大纲逐页生成 SVG（调用 save_slide）
3. Reviewer 检查 SVG 质量，必要时要求 Designer 重新生成
"""

import asyncio
import logging
from typing import Any, AsyncIterator

from wuwei import Agent, LLMGateway, SkillManager, FileSystemSkillProvider
from wuwei.tools import ToolRegistry

from app.core.config import Settings, get_settings
from app.services.agent_service import AgentService
from app.services.ppt.theme_token_resolver import list_available_themes

_logger = logging.getLogger("multi_agent_ppt")


class MultiAgentPptService:
    """多 Agent 协作 PPT 生成服务"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def generate_ppt(
        self,
        user_message: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """使用多 Agent 协作生成 PPT。

        Yields SSE 事件格式的字典。
        """
        llm = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)

        # 创建工具注册表
        registry = self._build_ppt_registry()

        # Phase 1: Planner Agent 规划结构
        yield {"event": "run_status", "data": {"phase": "planning", "label": "正在规划 PPT 结构"}}
        planner_result = await self._run_planner(llm, user_message)

        if not planner_result:
            yield {"event": "error", "data": {"message": "PPT 结构规划失败"}}
            return

        # Phase 2: Designer Agent 逐页生成
        yield {"event": "run_status", "data": {"phase": "designing", "label": "正在生成 PPT 页面"}}

        theme = planner_result.get("theme", "openai")
        pages = planner_result.get("pages", [])

        for i, page in enumerate(pages):
            yield {"event": "run_status", "data": {"phase": "designing", "label": f"正在生成第 {i+1}/{len(pages)} 页"}}

            svg = await self._run_designer(
                llm=llm,
                registry=registry,
                page_spec=page,
                theme=theme,
                page_num=i + 1,
                total_pages=len(pages),
            )

            if svg:
                # 通过 save_slide 工具写入文件
                await self._save_slide(session_id, i + 1, svg)

        # Phase 3: Reviewer Agent 检查质量
        yield {"event": "run_status", "data": {"phase": "reviewing", "label": "正在检查 PPT 质量"}}
        review_result = await self._run_reviewer(llm, session_id)

        if review_result and review_result.get("needs_revision"):
            # 自动重试有问题的页面（最多 1 轮）
            issues = review_result.get("issues", [])
            if issues and len(issues) <= 3:
                yield {"event": "run_status", "data": {"phase": "revising", "label": f"正在修订 {len(issues)} 页"}}
                for issue_page in issues:
                    page_idx = issue_page.get("page", 1) - 1
                    if 0 <= page_idx < len(pages):
                        svg = await self._run_designer(
                            llm=llm, registry=registry,
                            page_spec={**pages[page_idx], "revision_hint": issue_page.get("message", "")},
                            theme=theme, page_num=page_idx + 1, total_pages=len(pages),
                        )
                        if svg:
                            await self._save_slide(session_id, page_idx + 1, svg)
            else:
                yield {"event": "delta", "data": {"content": f"PPT 生成完成，但有 {len(issues)} 个问题需要检查。"}}

        yield {"event": "done", "data": {"reason": "multi_agent_ppt_complete"}}

    def _build_ppt_registry(self) -> ToolRegistry:
        """构建 PPT 模式工具注册表"""
        from app.services.agent_service import AgentService
        from app.services.agent_profile_service import RuntimeAgentProfile

        profile = RuntimeAgentProfile(
            profile_id=None, name="ppt", slug="ppt", response_mode="ppt",
            system_prompt="", builtin_tools=("skill",),
            approval_tools=frozenset(), signature=(), skills=(),
        )
        registry, _ = AgentService._build_tool_registry(profile)
        return registry

    async def _run_planner(self, llm: LLMGateway, user_message: str) -> dict[str, Any] | None:
        """Planner Agent：分析需求，输出 PPT 大纲"""
        from wuwei.core.message import SystemMessage, HumanMessage

        themes = ", ".join(sorted(list_available_themes())[:20])
        planner_prompt = f"""你是 PPT 规划专家。分析用户需求，输出 JSON 格式的 PPT 大纲。

用户需求：{user_message}

可用主题：{themes}

输出格式（JSON）：
{{
  "title": "PPT 标题",
  "theme": "主题名（从上面列表选）",
  "page_count": 页数（8-14）,
  "pages": [
    {{"type": "cover", "title": "封面标题", "subtitle": "副标题"}},
    {{"type": "section", "title": "章节标题", "section_num": 1}},
    {{"type": "content", "title": "页面标题", "layout": "bullets/two-column/comparison", "content": "内容要点"}},
    {{"type": "ending", "title": "结束页标题"}}
  ]
}}

只返回 JSON，不要其他内容。"""

        try:
            response = await llm.generate(
                messages=[
                    SystemMessage(content="你是 PPT 规划专家，只输出 JSON。"),
                    HumanMessage(content=planner_prompt),
                ],
            )
            content = response.message.content
            if content:
                import json
                # 提取 JSON（可能被 markdown 代码块包裹）
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                return json.loads(content.strip())
        except Exception as e:
            _logger.error(f"Planner failed: {e}")
        return None

    async def _run_designer(
        self,
        llm: LLMGateway,
        registry: ToolRegistry,
        page_spec: dict,
        theme: str,
        page_num: int,
        total_pages: int,
    ) -> str | None:
        """Designer Agent：加载设计规范后生成 SVG"""
        from wuwei.core.message import SystemMessage, HumanMessage

        page_type = page_spec.get("type", "content")
        title = page_spec.get("title", "")
        content = page_spec.get("content", "")
        layout = page_spec.get("layout", "bullets")

        # 加载设计指南（如有）
        design_guide = self._load_design_guide()
        theme_css = self._load_theme_css(theme)

        designer_prompt = f"""你是 SVG 幻灯片设计专家。根据以下规格生成一个 SVG 页面。

页面规格：
- 类型：{page_type}
- 标题：{title}
- 内容：{content}
- 布局：{layout}
- 主题：{theme}
- 页码：{page_num}/{total_pages}

要求：
1. 使用 viewBox="0 0 1280 720"
2. 所有颜色用 var(--xxx) 引用
3. data-theme="{theme}"
4. 字体：Inter, Noto Sans SC, sans-serif
5. 包含 <!-- notes: 演讲者备注 -->

{design_guide}

{theme_css}

只输出 SVG 代码，不要其他内容。"""

        try:
            response = await llm.generate(
                messages=[
                    SystemMessage(content="你是 SVG 幻灯片设计专家，只输出 SVG 代码。"),
                    HumanMessage(content=designer_prompt),
                ],
            )
            content = response.message.content
            if content:
                if "<svg" in content:
                    start = content.index("<svg")
                    end = content.rfind("</svg>") + 6
                    return content[start:end]
        except Exception as e:
            _logger.error(f"Designer failed for page {page_num}: {e}")
        return None

    def _load_design_guide(self) -> str:
        """加载 PPT 设计指南 skill 内容"""
        try:
            from app.services.skill_service import SkillService
            svc = SkillService()
            with svc.session_factory() as db:
                from sqlalchemy import select
                from app.db.models import SkillModel
                skill = db.scalar(select(SkillModel).where(SkillModel.slug == "ppt-design-guide"))
                if skill and skill.root_dir:
                    from pathlib import Path
                    skill_md = Path(skill.root_dir) / "SKILL.md"
                    if skill_md.exists():
                        text = skill_md.read_text(encoding="utf-8")
                        # 截取前 3000 字符避免 prompt 过长
                        return f"## 设计规范\n\n{text[:3000]}"
        except Exception as e:
            _logger.debug(f"Could not load design guide: {e}")
        return ""

    def _load_theme_css(self, theme: str) -> str:
        """加载主题 CSS token 定义"""
        try:
            from app.services.ppt.theme_token_resolver import load_theme_tokens
            tokens = load_theme_tokens(theme)
            if tokens:
                css_vars = "\n".join(f"  --{k}: {v};" for k, v in list(tokens.items())[:30])
                return f"## 主题 CSS 变量\n\n```css\n:root {{\n{css_vars}\n}}\n```"
        except Exception as e:
            _logger.debug(f"Could not load theme CSS: {e}")
        return ""

    async def _save_slide(self, session_id: str | None, slide_num: int, svg: str) -> bool:
        """保存 slide SVG 文件"""
        from pathlib import Path
        from app.core.data_path import PPT_SESSIONS_DIR

        if not session_id:
            return False

        slides_dir = PPT_SESSIONS_DIR / session_id
        slides_dir.mkdir(parents=True, exist_ok=True)

        slide_path = slides_dir / f"slide_{slide_num}.svg"
        slide_path.write_text(svg, encoding="utf-8")
        return True

    async def _run_reviewer(self, llm: LLMGateway, session_id: str | None) -> dict[str, Any] | None:
        """Reviewer Agent：检查 SVG 质量，返回有问题的页面列表"""
        from pathlib import Path
        from app.core.data_path import PPT_SESSIONS_DIR

        if not session_id:
            return None

        slides_dir = PPT_SESSIONS_DIR / session_id
        if not slides_dir.exists():
            return None

        svg_files = sorted(slides_dir.glob("slide_*.svg"))
        if not svg_files:
            return {"needs_revision": True, "issues": [{"page": 1, "message": "没有找到 SVG 文件"}]}

        issues = []
        import re

        for f in svg_files:
            page_num = int(re.search(r'slide_(\d+)', f.name).group(1))
            content = f.read_text(encoding="utf-8")

            # 基础检查
            if "<svg" not in content:
                issues.append({"page": page_num, "message": "无效 SVG：缺少 <svg> 标签"})
                continue

            # viewBox 检查
            m = re.search(r'viewBox=["\']([^"\']+)["\']', content)
            if not m:
                issues.append({"page": page_num, "message": "缺少 viewBox 属性"})
            elif m.group(1) != "0 0 1280 720":
                issues.append({"page": page_num, "message": f"viewBox 不标准: {m.group(1)}"})

            # 内容过少检查
            if len(content) < 200:
                issues.append({"page": page_num, "message": "SVG 内容过少，可能生成不完整"})

            # 空白页检查
            text_match = re.findall(r'>([^<]+)<', content)
            visible_text = " ".join(t.strip() for t in text_match if t.strip())
            if len(visible_text) < 10 and page_num > 1:
                issues.append({"page": page_num, "message": "页面几乎没有可见文字内容"})

        if issues:
            return {"needs_revision": True, "issues": issues}

        return {"needs_revision": False, "issues": []}
