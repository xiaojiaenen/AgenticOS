"""部署/发布链路的三处修复回归。

用户报障：「AI 评审显示未配置可用模型」「AI 生成名字不行」
「网站审批通过预览也 404」。三个都是**代码层面的缺口**：

1. **AI 生成名字根本没实现** —— 发布弹窗输入框写着"留空则由 AI 根据对话
   自动生成"，后端 `request_deploy` 却是 `title=(title or "").strip() or None`，
   留空就存 None，最终展示成一串 `u3_s1794..._v2` 机器 ID。

2. **AI 评审报错不可操作** —— 只说"未配置可用模型"，而实际常见原因是
   模型名无效/密钥失效，管理员会照着"去配模型"白折腾。

3. **短链对目录请求 404** —— `/s/<code>/` 302 到 `/sites/<slug>/`，
   而 `alias` + `try_files $uri/` 对"目录 → index"的解析依赖 `index` 指令，
   缺省时可能直接 404。显式补 `index.html` 最稳。
"""

from __future__ import annotations

import inspect

import pytest


class TestTitleCleaning:
    """模型输出清理：这是"AI 生成名字"能用的前提。"""

    @staticmethod
    def clean(raw: str) -> str:
        from app.services.website_title_service import _clean_title

        return _clean_title(raw)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("「季度销售数据看板」。", "季度销售数据看板"),
            ('"团队协作流程说明"', "团队协作流程说明"),
            ("《年度经营分析》", "年度经营分析"),
            ("# 项目周报", "项目周报"),
            ("  产品路线图  ", "产品路线图"),
            ("看板。", "看板"),
            ("数据看板\n\n这个名字体现了核心功能", "数据看板"),
        ],
    )
    def test_strips_wrappers_and_punctuation(self, raw, expected):
        assert self.clean(raw) == expected

    def test_strips_code_fence(self):
        assert self.clean("```\n团队协作流程说明\n```") == "团队协作流程说明"

    def test_strips_fence_with_language_tag(self):
        assert self.clean("```json\n数据看板\n```") == "数据看板"

    def test_wrapped_quote_plus_period_order(self):
        """顺序陷阱：`「标题」。` 若先按引号配对会失败（结尾是 」。）。"""
        assert self.clean("「标题」。") == "标题"

    def test_keeps_plain_text_untouched(self):
        assert self.clean("销售数据看板") == "销售数据看板"


class TestTitleGeneration:
    def test_entry_point_is_async(self):
        """必须是 async —— 端点里要 await。"""
        from app.services.website_title_service import generate_site_title

        assert inspect.iscoroutinefunction(generate_site_title)

    @pytest.mark.asyncio
    async def test_returns_none_when_no_model(self, monkeypatch):
        """拿不到网关时返回 None（调用方退回 slug 兜底，不阻断发布）。"""
        from app.services import website_title_service as svc

        monkeypatch.setattr(svc, "build_llm_optional", lambda **kwargs: None)
        result = await svc.generate_site_title(
            conversation=[{"role": "user", "text": "做个销售看板"}],
            files=[{"path": "index.html"}],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_rejects_overlong_title(self, monkeypatch):
        """过长的输出说明模型没照做，宁可兜底也不要一长串。"""
        from app.services import website_title_service as svc

        class _Msg:
            content = "这" * 60

        class _Resp:
            message = _Msg()

        class _LLM:
            async def generate(self, messages):
                return _Resp()

        monkeypatch.setattr(svc, "build_llm_optional", lambda **kwargs: _LLM())
        result = await svc.generate_site_title(conversation=[])
        assert result is None


class TestDeployEndpointWiring:
    def test_request_deploy_is_async(self):
        """端点是 async —— 内部要 await 标题生成。"""
        from app.api.v1.endpoints.website import request_deploy

        assert inspect.iscoroutinefunction(request_deploy)

    def test_title_helper_exists_and_async(self):
        from app.api.v1.endpoints.website import _generate_title_for_project

        assert inspect.iscoroutinefunction(_generate_title_for_project)


class TestAiReviewMessage:
    def test_unavailable_reason_is_actionable(self):
        """不可用原因必须给出可操作步骤，而不是笼统的"未配置模型"。"""
        import re

        src = open(
            "app/services/website_review_service.py", encoding="utf-8"
        ).read()
        # 找出新的文案块
        assert "AI 提供商" in src, "评审不可用文案未提到去后台检查提供商"
        assert re.search(r"模型名|密钥|登录态", src), "文案未给出具体排查方向"


class TestShortlinkIndex:
    def test_public_target_gets_explicit_index(self):
        """空 suffix 要显式指向 index.html（见 shortlinks.py 注释）。"""
        src = open(
            "app/api/v1/endpoints/shortlinks.py", encoding="utf-8"
        ).read()
        assert "suffix or 'index.html'" in src or 'suffix or "index.html"' in src, (
            "短链对目录的跳转未补 index.html，nginx 的 alias+try_files 可能 404"
        )

    def test_nginx_declares_index_in_sites_location(self):
        """nginx 的 /sites/ 块要显式声明 index（不依赖 server 级继承）。"""
        from pathlib import Path

        # 测试 cwd 是 backend/，nginx.conf 在仓库根的 deploy/ 下 —— 两种都试
        candidates = [
            Path("deploy/nginx/nginx.conf"),
            Path("../deploy/nginx/nginx.conf"),
        ]
        conf = next((p for p in candidates if p.is_file()), None)
        assert conf is not None, f"找不到 nginx.conf（试过 {[str(c) for c in candidates]}）"
        src = conf.read_text(encoding="utf-8")
        # 定位 /sites/ 块
        start = src.index("location /sites/ {")
        block = src[start : start + 600]
        assert "index index.html;" in block, (
            "nginx /sites/ 未声明 index，目录访问可能 404"
        )
