"""
Wiki 编译器

使用 LLM 驱动的知识提取和页面生成：
1. 分析阶段：LLM 阅读文档，输出结构化分析（实体、概念、事实、流程等）
2. 生成阶段：根据分析结果生成 Wiki 页面
3. 冲突检测：与已有页面比对，发现矛盾
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from .document_parser import ParsedDocument

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """实体"""
    name: str
    type: str  # person, organization, product, system, location
    description: str


@dataclass
class Concept:
    """概念"""
    name: str
    description: str
    key_points: list[str] = field(default_factory=list)


@dataclass
class Fact:
    """事实"""
    claim: str
    evidence: str
    confidence: float = 0.8


@dataclass
class Procedure:
    """流程/操作"""
    name: str
    steps: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class FAQ:
    """问答对"""
    question: str
    answer: str


@dataclass
class Contradiction:
    """矛盾"""
    claim: str
    existing_page_id: Optional[int] = None
    existing_page_title: str = ""
    nature: str = ""  # 矛盾性质描述


@dataclass
class AnalysisResult:
    """文档分析结果"""
    entities: list[Entity] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    faqs: list[FAQ] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    summary: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class WikiPageDraft:
    """Wiki 页面草稿"""
    title: str
    page_type: str  # entity, concept, source_summary, synthesis, comparison, faq, procedure
    content: str  # Markdown 内容
    frontmatter: dict = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)  # ["kb_document:3"]
    wikilinks: list[str] = field(default_factory=list)  # 链接的其他页面标题
    action: str = "create"  # create, merge, skip


class WikiCompiler:
    """LLM 驱动的 Wiki 页面生成器"""

    def __init__(self, llm_gateway, knowledge_base_purpose: str = ""):
        """
        Args:
            llm_gateway: wuwei LLMGateway 实例
            knowledge_base_purpose: 知识库的目标声明
        """
        self.llm = llm_gateway
        self.purpose = knowledge_base_purpose

    async def analyze(self, document: ParsedDocument) -> AnalysisResult:
        """
        分析阶段：LLM 阅读文档，输出结构化分析

        Args:
            document: 解析后的文档

        Returns:
            AnalysisResult: 结构化分析结果
        """
        logger.info(f"Analyzing document: {document.metadata.get('file_name', 'unknown')}")

        # 构建分析提示
        prompt = self._build_analysis_prompt(document)

        # 调用 LLM
        response = await self._call_llm(prompt)

        # 解析响应
        return self._parse_analysis_response(response)

    def analyze_sync(self, document: ParsedDocument) -> AnalysisResult:
        """同步版本的分析方法（不调用 LLM，返回空结果）"""
        logger.info(f"Analyzing document (sync): {document.metadata.get('file_name', 'unknown')}")
        # 同步模式下暂不执行 LLM 分析，返回空结果
        return AnalysisResult()

    async def generate_pages(
        self,
        analysis: AnalysisResult,
        document: ParsedDocument,
        document_id: int,
    ) -> list[WikiPageDraft]:
        """
        生成阶段：根据分析结果生成 Wiki 页面

        Args:
            analysis: 分析结果
            document: 原始文档
            document_id: 文档 ID

        Returns:
            list[WikiPageDraft]: Wiki 页面草稿列表
        """
        logger.info("Generating wiki pages from analysis")

        pages = []
        source_ref = f"kb_document:{document_id}"

        # 生成实体页面
        for entity in analysis.entities:
            page = self._generate_entity_page(entity, source_ref, document)
            pages.append(page)

        # 生成概念页面
        for concept in analysis.concepts:
            page = self._generate_concept_page(concept, source_ref, document)
            pages.append(page)

        # 生成流程页面
        for procedure in analysis.procedures:
            page = self._generate_procedure_page(procedure, source_ref, document)
            pages.append(page)

        # 生成 FAQ 页面
        if analysis.faqs:
            page = self._generate_faq_page(analysis.faqs, source_ref, document)
            pages.append(page)

        # 生成来源摘要页面
        page = self._generate_source_summary_page(analysis, document, source_ref)
        pages.append(page)

        return pages

    def generate_pages_sync(
        self,
        analysis: AnalysisResult,
        document: ParsedDocument,
        document_id: int,
    ) -> list[WikiPageDraft]:
        """同步版本的页面生成方法"""
        logger.info("Generating wiki pages from analysis (sync)")
        pages = []
        source_ref = f"kb_document:{document_id}"

        for entity in analysis.entities:
            page = self._generate_entity_page(entity, source_ref, document)
            pages.append(page)

        for concept in analysis.concepts:
            page = self._generate_concept_page(concept, source_ref, document)
            pages.append(page)

        for procedure in analysis.procedures:
            page = self._generate_procedure_page(procedure, source_ref, document)
            pages.append(page)

        if analysis.faqs:
            page = self._generate_faq_page(analysis.faqs, source_ref, document)
            pages.append(page)

        page = self._generate_source_summary_page(analysis, document, source_ref)
        pages.append(page)

        return pages

    async def detect_conflicts(
        self,
        new_pages: list[WikiPageDraft],
        existing_pages: list[dict],
    ) -> list[Contradiction]:
        """
        冲突检测：新页面与已有页面比对

        Args:
            new_pages: 新生成的页面
            existing_pages: 已有页面列表 [{"id": 1, "title": "...", "content": "..."}]

        Returns:
            list[Contradiction]: 检测到的矛盾
        """
        if not existing_pages:
            return []

        logger.info(f"Detecting conflicts against {len(existing_pages)} existing pages")

        contradictions = []

        for new_page in new_pages:
            # 找到标题相似的已有页面
            similar_pages = self._find_similar_pages(new_page, existing_pages)

            for existing in similar_pages:
                # 使用 LLM 判断是否矛盾
                conflict = await self._check_conflict(new_page, existing)
                if conflict:
                    contradictions.append(conflict)

        return contradictions

    def detect_conflicts_sync(
        self,
        new_pages: list[WikiPageDraft],
        existing_pages: list[dict],
    ) -> list[Contradiction]:
        """同步版本的冲突检测方法（不调用 LLM，返回空列表）"""
        if not existing_pages:
            return []
        logger.info(f"Detecting conflicts (sync) against {len(existing_pages)} existing pages")
        # 同步模式下暂不执行 LLM 冲突检测
        return []

    def _build_analysis_prompt(self, document: ParsedDocument) -> str:
        """构建分析提示"""
        doc_text = document.text[:8000]  # 限制长度

        purpose_section = ""
        if self.purpose:
            purpose_section = f"""
## 知识库目标

本知识库的目标：{self.purpose}

请根据上述目标，判断哪些信息值得提取。
"""

        prompt = f"""你是一个知识管理专家。请分析以下文档，提取关键知识。

{purpose_section}

## 文档内容

{doc_text}

## 提取要求

请提取以下类型的知识，以 JSON 格式输出：

```json
{{
  "entities": [
    {{"name": "实体名称", "type": "person|organization|product|system|location", "description": "描述"}}
  ],
  "concepts": [
    {{"name": "概念名称", "description": "描述", "key_points": ["要点1", "要点2"]}}
  ],
  "facts": [
    {{"claim": "事实陈述", "evidence": "证据/来源", "confidence": 0.8}}
  ],
  "procedures": [
    {{"name": "流程名称", "description": "描述", "steps": ["步骤1", "步骤2"]}}
  ],
  "faqs": [
    {{"question": "问题", "answer": "答案"}}
  ],
  "summary": "文档摘要（100字以内）",
  "tags": ["标签1", "标签2"]
}}
```

注意：
1. 每个页面内容必须是自包含的，不依赖上下文即可理解
2. 提取的信息应该准确反映原文内容
3. 如果某些类型没有内容，返回空数组
4. 只输出 JSON，不要其他内容
"""
        return prompt

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM"""
        try:
            # 使用 wuwei LLMGateway
            response = await self.llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000,
            )
            return response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    def _parse_analysis_response(self, response: str) -> AnalysisResult:
        """解析 LLM 响应"""
        # 提取 JSON
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON: {json_str[:500]}")
            return AnalysisResult()

        result = AnalysisResult()

        # 解析实体
        for item in data.get("entities", []):
            result.entities.append(Entity(
                name=item.get("name", ""),
                type=item.get("type", "unknown"),
                description=item.get("description", ""),
            ))

        # 解析概念
        for item in data.get("concepts", []):
            result.concepts.append(Concept(
                name=item.get("name", ""),
                description=item.get("description", ""),
                key_points=item.get("key_points", []),
            ))

        # 解析事实
        for item in data.get("facts", []):
            result.facts.append(Fact(
                claim=item.get("claim", ""),
                evidence=item.get("evidence", ""),
                confidence=item.get("confidence", 0.8),
            ))

        # 解析流程
        for item in data.get("procedures", []):
            result.procedures.append(Procedure(
                name=item.get("name", ""),
                description=item.get("description", ""),
                steps=item.get("steps", []),
            ))

        # 解析 FAQ
        for item in data.get("faqs", []):
            result.faqs.append(FAQ(
                question=item.get("question", ""),
                answer=item.get("answer", ""),
            ))

        result.summary = data.get("summary", "")
        result.tags = data.get("tags", [])

        return result

    def _generate_entity_page(
        self,
        entity: Entity,
        source_ref: str,
        document: ParsedDocument,
    ) -> WikiPageDraft:
        """生成实体页面"""
        slug = self._slugify(entity.name)
        content = f"""# {entity.name}

**类型**: {entity.type}

## 描述

{entity.description}

## 相关信息

- 来源: {document.metadata.get('file_name', 'unknown')}
"""
        return WikiPageDraft(
            title=entity.name,
            page_type="entity",
            content=content,
            frontmatter={
                "title": entity.name,
                "type": "entity",
                "entity_type": entity.type,
                "tags": [],
            },
            sources=[source_ref],
            wikilinks=[],
        )

    def _generate_concept_page(
        self,
        concept: Concept,
        source_ref: str,
        document: ParsedDocument,
    ) -> WikiPageDraft:
        """生成概念页面"""
        slug = self._slugify(concept.name)
        key_points_md = "\n".join(f"- {point}" for point in concept.key_points)

        content = f"""# {concept.name}

## 定义

{concept.description}

## 要点

{key_points_md}

## 来源

- {document.metadata.get('file_name', 'unknown')}
"""
        return WikiPageDraft(
            title=concept.name,
            page_type="concept",
            content=content,
            frontmatter={
                "title": concept.name,
                "type": "concept",
                "tags": [],
            },
            sources=[source_ref],
            wikilinks=[],
        )

    def _generate_procedure_page(
        self,
        procedure: Procedure,
        source_ref: str,
        document: ParsedDocument,
    ) -> WikiPageDraft:
        """生成流程页面"""
        slug = self._slugify(procedure.name)
        steps_md = "\n".join(f"{i+1}. {step}" for i, step in enumerate(procedure.steps))

        content = f"""# {procedure.name}

## 概述

{procedure.description}

## 步骤

{steps_md}

## 来源

- {document.metadata.get('file_name', 'unknown')}
"""
        return WikiPageDraft(
            title=procedure.name,
            page_type="procedure",
            content=content,
            frontmatter={
                "title": procedure.name,
                "type": "procedure",
                "tags": [],
            },
            sources=[source_ref],
            wikilinks=[],
        )

    def _generate_faq_page(
        self,
        faqs: list[FAQ],
        source_ref: str,
        document: ParsedDocument,
    ) -> WikiPageDraft:
        """生成 FAQ 页面"""
        faq_items = []
        for faq in faqs:
            faq_items.append(f"## {faq.question}\n\n{faq.answer}\n")

        content = f"""# 常见问题

{"".join(faq_items)}

---

*来源: {document.metadata.get('file_name', 'unknown')}*
"""
        return WikiPageDraft(
            title="常见问题",
            page_type="faq",
            content=content,
            frontmatter={
                "title": "常见问题",
                "type": "faq",
                "tags": [],
            },
            sources=[source_ref],
            wikilinks=[],
        )

    def _generate_source_summary_page(
        self,
        analysis: AnalysisResult,
        document: ParsedDocument,
        source_ref: str,
    ) -> WikiPageDraft:
        """生成来源摘要页面"""
        file_name = document.metadata.get("file_name", "unknown")
        title = f"{file_name} - 摘要"

        content = f"""# {file_name}

## 摘要

{analysis.summary}

## 标签

{", ".join(analysis.tags) if analysis.tags else "无"}

## 统计

- 实体: {len(analysis.entities)} 个
- 概念: {len(analysis.concepts)} 个
- 事实: {len(analysis.facts)} 个
- 流程: {len(analysis.procedures)} 个
- FAQ: {len(analysis.faqs)} 个
"""
        return WikiPageDraft(
            title=title,
            page_type="source_summary",
            content=content,
            frontmatter={
                "title": title,
                "type": "source_summary",
                "source_file": file_name,
                "tags": analysis.tags,
            },
            sources=[source_ref],
            wikilinks=[],
        )

    def _find_similar_pages(
        self,
        new_page: WikiPageDraft,
        existing_pages: list[dict],
    ) -> list[dict]:
        """找到标题相似的已有页面"""
        similar = []
        new_title_lower = new_page.title.lower()

        for page in existing_pages:
            existing_title = page.get("title", "").lower()
            # 简单的字符串相似度
            if new_title_lower in existing_title or existing_title in new_title_lower:
                similar.append(page)
            elif self._jaccard_similarity(new_title_lower, existing_title) > 0.5:
                similar.append(page)

        return similar[:3]  # 最多返回 3 个

    async def _check_conflict(
        self,
        new_page: WikiPageDraft,
        existing_page: dict,
    ) -> Optional[Contradiction]:
        """使用 LLM 检查是否矛盾"""
        prompt = f"""请判断以下两个内容是否存在矛盾。

## 新内容

标题: {new_page.title}
内容:
{new_page.content[:1000]}

## 已有内容

标题: {existing_page.get('title', '')}
内容:
{existing_page.get('content', '')[:1000]}

如果存在矛盾，请输出：
```json
{{"has_conflict": true, "nature": "矛盾描述"}}
```

如果没有矛盾，请输出：
```json
{{"has_conflict": false}}
```
"""
        try:
            response = await self._call_llm(prompt)
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
            if json_match:
                data = json.loads(json_match.group(1))
                if data.get("has_conflict"):
                    return Contradiction(
                        claim=new_page.content[:200],
                        existing_page_id=existing_page.get("id"),
                        existing_page_title=existing_page.get("title", ""),
                        nature=data.get("nature", ""),
                    )
        except Exception as e:
            logger.error(f"Conflict check failed: {e}")

        return None

    def _jaccard_similarity(self, s1: str, s2: str) -> float:
        """计算 Jaccard 相似度"""
        set1 = set(s1.split())
        set2 = set(s2.split())
        if not set1 or not set2:
            return 0.0
        intersection = set1 & set2
        union = set1 | set2
        return len(intersection) / len(union)

    def _slugify(self, text: str) -> str:
        """生成 URL 友好的 slug"""
        # 移除特殊字符，保留中文、英文、数字
        text = re.sub(r"[^\w\s\u4e00-\u9fff-]", "", text)
        # 替换空白为连字符
        text = re.sub(r"\s+", "-", text.strip())
        return text.lower()[:100]
