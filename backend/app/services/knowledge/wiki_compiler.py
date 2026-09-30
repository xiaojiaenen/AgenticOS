"""
Wiki 编译器

使用 LLM 驱动的知识提取和页面生成：
1. 分析阶段：LLM 阅读文档，输出结构化分析（实体、概念、事实、流程等）
2. 生成阶段：根据分析结果生成 Wiki 页面
3. 冲突检测：与已有页面比对，发现矛盾

同步路径（analyze_sync / detect_conflicts_sync）提供规则启发式实现，
可选在独立线程中调用 LLM（避免嵌套事件循环问题）。
"""

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
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


# 在独立线程中跑 async LLM 调用（同步路径专用）
_llm_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wiki-llm")


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
        """
        logger.info(f"Analyzing document: {document.metadata.get('file_name', 'unknown')}")

        prompt = self._build_analysis_prompt(document)
        response = await self._call_llm(prompt)
        result = self._parse_analysis_response(response)
        if not (result.summary or result.entities or result.concepts or result.procedures):
            # LLM 返回不可用时回退启发式
            return self._analyze_heuristic(document)
        return result

    def analyze_sync(self, document: ParsedDocument) -> AnalysisResult:
        """同步分析：规则启发式为主，可选在独立线程调用 LLM。"""
        logger.info(f"Analyzing document (sync): {document.metadata.get('file_name', 'unknown')}")

        heuristic = self._analyze_heuristic(document)

        if self.llm is None:
            return heuristic

        # 可选 LLM：在独立线程 asyncio.run，避免与当前事件循环冲突
        try:
            prompt = self._build_analysis_prompt(document)

            def _run_llm() -> str:
                return asyncio.run(self._call_llm(prompt))

            future = _llm_executor.submit(_run_llm)
            response = future.result(timeout=90)
            llm_result = self._parse_analysis_response(response)
            if llm_result.summary or llm_result.entities or llm_result.concepts or llm_result.procedures:
                return llm_result
            logger.warning("LLM analysis returned empty, falling back to heuristics")
        except Exception as e:
            logger.warning(f"Sync LLM analysis failed, using heuristics: {e}")

        return heuristic

    def _analyze_heuristic(self, document: ParsedDocument) -> AnalysisResult:
        """规则启发式分析（无 LLM 时可用）。"""
        text = document.text or ""
        result = AnalysisResult()

        # 摘要：取前几行非空文本
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        result.summary = " ".join(lines[:3])[:200] if lines else ""

        # 标签：从标题/首行提取
        title = document.metadata.get("title") or (lines[0][:40] if lines else "")
        if title:
            result.tags.append(re.sub(r"[^\w一-鿿\-]+", "", title)[:20])

        # 概念/实体：Markdown 标题
        for m in re.finditer(r"^#{1,3}\s+(.+)$", text, re.MULTILINE):
            name = m.group(1).strip()
            if not name or name.lower() in {"摘要", "summary", "标签", "tags", "统计", "statistics"}:
                continue
            # 截取该标题下的段落作为描述
            start = m.end()
            nxt = re.search(r"^#{1,3}\s+", text[start:], re.MULTILINE)
            body = text[start: start + nxt.start()] if nxt else text[start: start + 400]
            body = body.strip()[:400]
            # 步骤列表 → Procedure
            steps = re.findall(r"^\s*(?:\d+\.|[-*])\s+(.+)$", body, re.MULTILINE)
            if len(steps) >= 2:
                result.procedures.append(Procedure(
                    name=name,
                    steps=[s.strip() for s in steps[:20]],
                    description=body[:200],
                ))
            else:
                result.concepts.append(Concept(
                    name=name,
                    description=body or name,
                    key_points=[ln.strip("-* ").strip() for ln in body.splitlines() if ln.strip()][:5],
                ))

        # FAQ：Q:/A: 模式
        for qm in re.finditer(
            r"(?:^|\n)(?:Q|问题)\s*[:：]\s*(.+)\n(?:A|答|回答)\s*[:：]\s*(.+)",
            text,
            re.IGNORECASE,
        ):
            result.faqs.append(FAQ(question=qm.group(1).strip(), answer=qm.group(2).strip()[:500]))

        # 事实：包含“必须/应当/默认/支持”等断言句
        for sent in re.split(r"[。.!?\n]", text):
            sent = sent.strip()
            if 10 < len(sent) < 200 and re.search(r"(必须|应当|默认|支持|不支持|禁止|使用)", sent):
                result.facts.append(Fact(claim=sent, evidence=document.metadata.get("file_name", ""), confidence=0.7))
            if len(result.facts) >= 15:
                break

        # 实体：像产品/系统名的大写英文或「XX系统/平台」
        for m in re.finditer(r"([A-Z][A-Za-z0-9_\-]{2,}|[\w一-鿿]{2,12}(?:系统|平台|服务|模块))", text):
            name = m.group(1)
            if len(name) < 3 or name.lower() in {"http", "https", "json", "html", "markdown"}:
                continue
            if not any(e.name == name for e in result.entities):
                result.entities.append(Entity(name=name, type="system", description=f"文档中出现：{name}"))
            if len(result.entities) >= 20:
                break

        return result

    async def generate_pages(
        self,
        analysis: AnalysisResult,
        document: ParsedDocument,
        document_id: int,
    ) -> list[WikiPageDraft]:
        """生成阶段：根据分析结果生成 Wiki 页面"""
        logger.info("Generating wiki pages from analysis")
        pages = self._build_pages_from_analysis(analysis, document, document_id)
        self._fill_wikilinks(pages)
        return pages

    def generate_pages_sync(
        self,
        analysis: AnalysisResult,
        document: ParsedDocument,
        document_id: int,
    ) -> list[WikiPageDraft]:
        """同步版本的页面生成方法"""
        logger.info("Generating wiki pages from analysis (sync)")
        pages = self._build_pages_from_analysis(analysis, document, document_id)
        self._fill_wikilinks(pages)
        return pages

    def _build_pages_from_analysis(
        self,
        analysis: AnalysisResult,
        document: ParsedDocument,
        document_id: int,
    ) -> list[WikiPageDraft]:
        pages: list[WikiPageDraft] = []
        source_ref = f"kb_document:{document_id}"

        for entity in analysis.entities:
            pages.append(self._generate_entity_page(entity, source_ref, document))
        for concept in analysis.concepts:
            pages.append(self._generate_concept_page(concept, source_ref, document))
        for procedure in analysis.procedures:
            pages.append(self._generate_procedure_page(procedure, source_ref, document))
        if analysis.faqs:
            pages.append(self._generate_faq_page(analysis.faqs, source_ref, document))
        pages.append(self._generate_source_summary_page(analysis, document, source_ref))
        return pages

    def _fill_wikilinks(self, pages: list[WikiPageDraft]) -> None:
        """根据页面标题互出现在内容中，填充 wikilinks（供 ingest 写入 KBWikiLinkModel）。"""
        titles = [p.title for p in pages if p.title]
        for page in pages:
            links: list[str] = []
            for t in titles:
                if t == page.title:
                    continue
                # 标题以纯文本出现在正文（长度 >= 2 避免误链）
                if len(t) >= 2 and t in page.content:
                    links.append(t)
            page.wikilinks = links

    async def detect_conflicts(
        self,
        new_pages: list[WikiPageDraft],
        existing_pages: list[dict],
    ) -> list[Contradiction]:
        """冲突检测：新页面与已有页面比对"""
        if not existing_pages:
            return []

        logger.info(f"Detecting conflicts against {len(existing_pages)} existing pages")
        contradictions: list[Contradiction] = []

        for new_page in new_pages:
            similar_pages = self._find_similar_pages(new_page, existing_pages)
            for existing in similar_pages:
                conflict = await self._check_conflict(new_page, existing)
                if conflict:
                    contradictions.append(conflict)

        return contradictions

    def detect_conflicts_sync(
        self,
        new_pages: list[WikiPageDraft],
        existing_pages: list[dict],
    ) -> list[Contradiction]:
        """同步冲突检测：规则启发式 + 可选 LLM（独立线程）。"""
        if not existing_pages:
            return []
        logger.info(f"Detecting conflicts (sync) against {len(existing_pages)} existing pages")

        contradictions: list[Contradiction] = []
        for new_page in new_pages:
            similar_pages = self._find_similar_pages(new_page, existing_pages)
            for existing in similar_pages:
                conflict = self._check_conflict_rule(new_page, existing)
                if conflict is None and self.llm is not None:
                    conflict = self._check_conflict_llm_sync(new_page, existing)
                if conflict:
                    contradictions.append(conflict)

        return contradictions

    def _check_conflict_rule(self, new_page: WikiPageDraft, existing_page: dict) -> Optional[Contradiction]:
        """规则启发式冲突检测（可返回非空）。"""
        new_content = new_page.content or ""
        old_content = existing_page.get("content") or ""

        # 1) 否定词对立：一方含“禁止/不可/不支持/不要”，另一方含“必须/应当/支持/需要”
        negative = re.search(r"(禁止|不可|不支持|不要|不应|无需)", new_content)
        positive = re.search(r"(必须|应当|需要|支持|应当)", old_content)
        if negative and positive:
            # 粗略：在相近句中出现对立倾向
            return Contradiction(
                claim=new_content[:200],
                existing_page_id=existing_page.get("id"),
                existing_page_title=existing_page.get("title", ""),
                nature=f"新内容强调限制/否定，已有页面强调肯定要求（标题: {existing_page.get('title', '')}）",
            )

        # 2) 同关键短语下数值冲突（如端口、超时、版本号）
        new_nums = set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)+|\d+)(?![\w])", new_content))
        old_nums = set(re.findall(r"(?<![\w.])(\d+(?:\.\d+)+|\d+)(?![\w])", old_content))
        shared_keys = set(self._extract_key_phrases(new_content)) & set(self._extract_key_phrases(old_content))
        if shared_keys:
            only_new = new_nums - old_nums
            only_old = old_nums - new_nums
            # 同主题但数值集合显著不同且至少各有数字 → 潜在冲突
            if only_new and only_old and len(only_new & only_old) < min(3, len(only_new | only_old)):
                return Contradiction(
                    claim=new_content[:200],
                    existing_page_id=existing_page.get("id"),
                    existing_page_title=existing_page.get("title", ""),
                    nature=(
                        f"同一主题（{', '.join(list(shared_keys)[:3])}）下数值不一致："
                        f"新={sorted(list(only_new))[:5]} vs 旧={sorted(list(only_old))[:5]}"
                    ),
                )

        # 3) 版本号对立
        new_ver = set(re.findall(r"v?(\d+\.\d+(?:\.\d+)?)", new_content))
        old_ver = set(re.findall(r"v?(\d+\.\d+(?:\.\d+)?)", old_content))
        if new_ver and old_ver and not (new_ver & old_ver):
            # 仅当标题相似时才报（已由 _find_similar_pages 过滤）
            if new_ver and old_ver:
                return Contradiction(
                    claim=new_content[:200],
                    existing_page_id=existing_page.get("id"),
                    existing_page_title=existing_page.get("title", ""),
                    nature=f"版本号不一致：新={sorted(new_ver)[:3]} vs 旧={sorted(old_ver)[:3]}",
                )

        return None

    def _check_conflict_llm_sync(self, new_page: WikiPageDraft, existing_page: dict) -> Optional[Contradiction]:
        """在独立线程中调用 LLM 判断矛盾。"""
        if self.llm is None:
            return None

        def _run() -> Optional[Contradiction]:
            async def _inner() -> Optional[Contradiction]:
                return await self._check_conflict(new_page, existing_page)

            return asyncio.run(_inner())

        try:
            future = _llm_executor.submit(_run)
            return future.result(timeout=60)
        except Exception as e:
            logger.debug(f"Sync LLM conflict check skipped: {e}")
            return None

    def _extract_key_phrases(self, text: str) -> list[str]:
        """提取用于冲突比对的关键短语（中文 bigram + 英文单词）。"""
        text = text.lower()
        text = re.sub(r"[^\w\s一-鿿]", " ", text)
        phrases: list[str] = []
        for part in text.split():
            if re.search(r"[一-鿿]", part):
                for i in range(len(part) - 1):
                    phrases.append(part[i:i + 2])
            elif len(part) >= 3:
                phrases.append(part)
        return phrases

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
        text = re.sub(r"[^\w\s一-鿿-]", "", text)
        # 替换空白为连字符
        text = re.sub(r"\s+", "-", text.strip())
        return text.lower()[:100]
