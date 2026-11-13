"""注入 catalog 的剥离与会话标题清洗 回归。

两个真实故障（用户报告）：

1. **PPT 会话的用户消息把 skill 文档展示出来了** —— inject_design_catalog
   是 ``message + catalog`` 裸拼接、没有 marker，strip_injected_catalog 只认
   website 的边界 → 「222 主题 + 工作流顺序 + CURRENT TIME」整段落库回显，
   用户刷新就看到自己"发了一整段 skill 文档"。
2. **会话列表标题变成半截 skill 文档** —— 标题从首条用户消息派生
   （_first_user_text），源头没剥 → 「做一个…培训 --- ## ⚠️ 工作流顺序…」。
"""
from __future__ import annotations

from app.services.agent.prompts import (
    DESIGN_CATALOG_MARKER,
    WEBSITE_CATALOG_MARKER,
    inject_design_catalog,
    inject_website_catalog,
    strip_injected_catalog,
)


class TestStripCatalog:
    def test_design_marker_roundtrip(self):
        """PPT 注入 → strip 后只留用户原文（新格式 marker）。"""
        raw = "做一个 2 页的演示文稿"
        injected = inject_design_catalog(raw)
        assert injected.startswith(raw)
        assert DESIGN_CATALOG_MARKER in injected
        assert "CURRENT TIME" in injected

        assert strip_injected_catalog(injected) == raw

    def test_website_marker_roundtrip(self):
        import asyncio

        raw = "做一个最简单的vue网站"
        injected = asyncio.run(inject_website_catalog(raw))
        assert strip_injected_catalog(injected) == raw

    def test_legacy_design_injection_is_stripped(self):
        """存量脏数据（无 marker 时代拼接的）按 legacy head 截断。"""
        dirty = (
            "做一个 2 页的演示文稿，主题「测试技能加载」\n---\n\n"
            "## ⚠️ 工作流顺序（严格遵守）\n\n核心原则：先消化文档…\n"
        )
        assert strip_injected_catalog(dirty) == "做一个 2 页的演示文稿，主题「测试技能加载」"

    def test_clean_text_untouched(self):
        """没有注入段的普通消息不能被误伤（正文里提到'主题选择'等词）。"""
        clean = "帮我选一个 PPT 主题，工作流顺序是什么？"
        assert strip_injected_catalog(clean) == clean

    def test_both_markers_present_takes_first(self):
        """极端情况两种注入都有：剥到最早的边界。"""
        text = "原始输入" + WEBSITE_CATALOG_MARKER + "website 速查" + DESIGN_CATALOG_MARKER + "design 速查"
        assert strip_injected_catalog(text) == "原始输入"


class TestSessionTitleClean:
    def test_first_user_text_strips_injection(self):
        """标题派生源（首条用户消息）必须剥掉注入段。"""
        from app.services.session_storage import _first_user_text
        import json

        raw = "做一个 2 页的演示文稿，主题「测试技能加载」"
        injected = inject_design_catalog(raw)
        payload = json.dumps({"role": "user", "text": injected}, ensure_ascii=False)
        result = _first_user_text(payload)
        assert result == raw

    def test_clean_session_title_truncates(self):
        from app.services.session_storage import _clean_session_title

        dirty = "做一个 2 页的演示文稿，主题「测试技能加载」\n---\n\n## ⚠️ 工作流顺序（严格遵守） 详细内容很多很多"
        cleaned = _clean_session_title(dirty)
        assert "工作流顺序" not in cleaned
        assert len(cleaned) <= 40
        assert cleaned.startswith("做一个 2 页的演示文稿")
