"""
模板注册表
完整对标 html-video 原版 TemplateRegistry
"""

import os
import re
from pathlib import Path
from typing import Optional

import yaml

from .types import TemplateMetadata, TemplateSearchResult
from .errors import HtmlVideoError, ErrorCode


class TemplateRegistry:
    """模板注册表 - 扫描、搜索、解析模板"""

    def __init__(self):
        self._templates: dict[str, TemplateMetadata] = {}

    async def scan(self, root_dir: str) -> list[TemplateMetadata]:
        """
        扫描 templates/ 下每个子目录：
        1. 检查 template.html-video.yaml 是否存在
        2. 解析 YAML 为 TemplateMetadata
        3. 设置 _dir 为目录绝对路径
        4. 存入 _templates 字典（key = meta.id）
        """
        root_path = Path(root_dir)
        if not root_path.exists():
            return []

        templates = []
        for subdir in sorted(root_path.iterdir()):
            if not subdir.is_dir():
                continue

            manifest_path = subdir / "template.html-video.yaml"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                # 处理嵌套的 output 字段
                if "output" in data and isinstance(data["output"], dict):
                    data["output"] = data["output"]

                # 处理 license 字段
                if "license" in data and isinstance(data["license"], dict):
                    data["license"] = data["license"]

                meta = TemplateMetadata(**data)
                meta.template_dir = str(subdir)

                self._templates[meta.id] = meta
                templates.append(meta)
            except Exception as e:
                # 跳过解析失败的模板
                print(f"Warning: Failed to parse template {subdir.name}: {e}")
                continue

        return templates

    def get(self, template_id: str) -> TemplateMetadata:
        """获取模板，不存在抛出 HtmlVideoError"""
        template = self._templates.get(template_id)
        if not template:
            raise HtmlVideoError(
                code=ErrorCode.TEMPLATE_NOT_FOUND,
                message=f"Template not found: {template_id}",
                context={"template_id": template_id},
            )
        return template

    def has(self, template_id: str) -> bool:
        """检查模板是否存在"""
        return template_id in self._templates

    def list_all(self) -> list[TemplateMetadata]:
        """列出所有模板"""
        return list(self._templates.values())

    def search(
        self,
        intent: str = "",
        aspect: Optional[str] = None,
        license_allow: Optional[list[str]] = None,
        engines_available: Optional[list[str]] = None,
        top: int = 5,
    ) -> list[TemplateSearchResult]:
        """
        语义搜索（完全对标原版算法）：
        1. 分词 intent（按非字母数字分割，过滤长度<=2）
        2. 构建 haystack = tags + best_for + name + description + category + subcategory
        3. 匹配 token → score += matched_count * 0.2
        4. aspect 匹配 → +0.15，不匹配 → -0.1
        5. license/engine 硬过滤
        6. 按 score 降序返回 top N
        """
        results: list[TemplateSearchResult] = []

        # 分词
        tokens = _tokenize_intent(intent)

        for template in self._templates.values():
            # License 硬过滤
            if license_allow and template.license.spdx not in license_allow:
                continue

            # Engine 硬过滤
            if engines_available and template.engine not in engines_available:
                continue

            score = 0.0
            matched_tags: list[str] = []

            # 构建 haystack
            haystack = (
                template.tags
                + template.best_for
                + [template.name, template.description, template.category]
                + ([template.subcategory] if template.subcategory else [])
            )
            haystack_lower = [h.lower() for h in haystack]

            # Token 匹配
            if tokens:
                for token in tokens:
                    for h in haystack_lower:
                        if token in h:
                            score += 0.2
                            if h not in matched_tags:
                                matched_tags.append(h)
                            break

            # Aspect 匹配
            if aspect:
                # 检查输出能力中的分辨率
                output = template.output
                if output and hasattr(output, "resolution"):
                    res = output.resolution
                    # 简单的 aspect 匹配逻辑
                    if aspect in str(res):
                        score += 0.15
                    else:
                        score -= 0.1

            if score > 0 or not tokens:  # 无搜索词时返回所有模板
                results.append(TemplateSearchResult(
                    template=template,
                    score=score,
                    matched_tags=matched_tags,
                ))

        # 按 score 降序排序
        results.sort(key=lambda x: x.score, reverse=True)

        return results[:top]


def _tokenize_intent(intent: str) -> list[str]:
    """
    分词 intent
    按非字母数字分割，过滤长度<=2
    """
    if not intent:
        return []
    tokens = re.split(r"[^a-zA-Z0-9一-鿿]+", intent)
    return [t.lower() for t in tokens if len(t) > 2]
