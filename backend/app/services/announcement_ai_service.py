from __future__ import annotations

import json

from wuwei.llm import LLMGateway, Message

from app.core.config import Settings, get_settings
from app.schemas.announcements import AnnouncementGenerateRequest


class AnnouncementAIService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def generate_draft(self, request: AnnouncementGenerateRequest) -> dict[str, object]:
        gateway = LLMGateway.from_env(max_tokens=self.settings.agent_max_tokens)
        prompt = self._build_prompt(request)

        messages = [
            Message(
                role="system",
                content=(
                    "你是一个产品公告文案助手，负责为 AI 平台撰写公告。\n"
                    "只返回 JSON，不要包含其他内容。\n"
                    "生成字段：eyebrow（眉标）, title（主标题）, subtitle（副标题）, body（正文）, cta_label（按钮文案）, cta_link（按钮链接）。\n"
                    "正文使用中文撰写。\n"
                    "不要用代码块包裹 markdown。\n"
                    "内容格式说明：\n"
                    "  - 如果内容格式是 markdown，body 必须用标准的 Markdown 语法编写，支持标题、列表、加粗、链接、引用等。\n"
                    "  - 如果内容格式是 html，body 必须是安全的 HTML 片段：可以使用 div、p、h1-h3、ul、ol、li、strong、em、a、pre、code、br、span、img 等标签，允许内联 style，但不能包含 <script>、<iframe>、<html>、<head>、<body>。"
                ),
            ),
            Message(role="user", content=prompt),
        ]

        try:
            response = await gateway.generate(
                messages=messages,
                stream=False,
                temperature=0.9,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            raise ValueError(f"AI generation failed: {exc}") from exc

        content = response.message.content
        if not content:
            raise ValueError("AI generation returned an empty response")

        from wuwei.parsers import JsonOutputParser
        parser = JsonOutputParser()
        try:
            generated = parser.parse(content)
        except Exception as exc:
            raise ValueError(f"AI generation returned invalid JSON: {exc}") from exc

        body = str(generated.get("body") or "").strip()
        if request.content_format == "html":
            lowered = body.lower()
            forbidden = ("<script", "<iframe", "<html", "<head", "<body")
            if any(token in lowered for token in forbidden):
                raise ValueError("AI generation returned unsafe HTML")

        return {
            "eyebrow": str(generated.get("eyebrow") or "系统公告").strip() or "系统公告",
            "title": str(generated.get("title") or "").strip(),
            "subtitle": str(generated.get("subtitle") or "").strip(),
            "body": body,
            "content_format": request.content_format,
            "theme": request.theme,
            "cta_label": self._clean_optional(generated.get("cta_label")),
            "cta_link": self._clean_optional(generated.get("cta_link")),
        }

    @staticmethod
    def _clean_optional(value: object) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _build_prompt(request: AnnouncementGenerateRequest) -> str:
        format_hint = (
            "正文使用 Markdown 语法编写，包含标题、列表、加粗等元素，风格清晰易读。"
            if request.content_format == "markdown"
            else "正文使用 HTML 片段编写，可以用内联样式实现丰富布局，风格精致有设计感。"
        )
        cta_hint = request.cta_goal or "如果需要，提供按钮文案和链接，引导用户操作。"
        return (
            f"主题：{request.theme}\n"
            f"内容格式：{request.content_format}\n"
            f"CTA 目标：{cta_hint}\n"
            "受众：进入 AI 智能体平台的用户\n"
            "语气：中文，专业、温暖、简洁、有品质感\n"
            f"{format_hint}\n"
            "标题要抓人、副标题要清晰、正文要方便扫读。\n"
            "需求描述：\n"
            f"{request.brief}"
        )
