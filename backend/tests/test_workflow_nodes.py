"""工作流内置节点处理器测试（nodes.py 的副作用边界）。

- llm：走 llm_factory（monkeypatch 假网关，不起真实 LLM）
- http：SSRF 策略（intranet 默认禁止）先行、危险 header 剥除、method 白名单、
  响应体限额 —— 不发起真实网络请求
- knowledge：ACL 参数随触发者走（monkeypatch 检索服务）
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.services.workflow.engine import WorkflowNodeError
from app.services.workflow.nodes import (
    make_knowledge_handler,
    run_http,
    run_llm,
    run_template,
)


# ---------------------------------------------------------------------------
# llm 节点
# ---------------------------------------------------------------------------

class _FakeGateway:
    def __init__(self) -> None:
        self.calls: list[list] = []

    async def generate(self, messages, stream=False, **kwargs):
        self.calls.append(list(messages))
        return SimpleNamespace(message=SimpleNamespace(content="工作流回答"), model="fake-model")


class TestLlmNode:
    def test_builds_system_and_user_messages(self, monkeypatch):
        gateway = _FakeGateway()

        def fake_build_llm(*, role=None, model=None, max_tokens=None, timeout=None):
            assert role == "fast", "工作流节点默认吃 fast 档，不占对话主力模型"
            return gateway

        import app.services.llm_factory as lf

        monkeypatch.setattr(lf, "build_llm", fake_build_llm)
        # 变量解析是 executor 的职责：handler 收到的是已解析参数。
        # 这里直接调 handler，先按 executor 同款逻辑手动解析。
        from app.services.workflow.engine import resolve_value

        params = resolve_value(
            {"system": "你是检索助手", "prompt": "总结：{{inputs.text}}"},
            {"inputs": {"text": "长文"}, "nodes": {}},
        )
        out = asyncio.run(run_llm(params, {"inputs": {"text": "长文"}, "nodes": {}}))
        assert out == "工作流回答"
        assert len(gateway.calls[0]) == 2
        assert gateway.calls[0][0].role == "system"
        assert gateway.calls[0][1].content == "总结：长文"

    def test_empty_prompt_rejected(self):
        with pytest.raises(WorkflowNodeError, match="prompt"):
            asyncio.run(run_llm({"prompt": "  "}, {}))

    def test_llm_output_is_plain_text(self, monkeypatch):
        """llm 输出必须是字符串 —— 模板里 {{nodes.n.output}} 直接拼，不出 dict。"""
        gateway = _FakeGateway()
        import app.services.llm_factory as lf

        monkeypatch.setattr(lf, "build_llm", lambda **kw: gateway)
        out = asyncio.run(run_llm({"prompt": "hi"}, {}))
        assert isinstance(out, str)


# ---------------------------------------------------------------------------
# http 节点（不发起真实网络请求）
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status=200, body=b"ok", headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {"content-type": "text/plain"}

    @property
    def charset_encoding(self):
        return "utf-8"

    def aiter_bytes(self):
        async def _gen():
            yield self._body
        return _gen()


class _FakeStreamCtx:
    def __init__(self, response, recorder):
        self.response = response
        self.recorder = recorder

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        _FakeAsyncClient.last_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, headers=None, content=None):
        _FakeAsyncClient.last_kwargs["method"] = method
        _FakeAsyncClient.last_kwargs["url"] = url
        _FakeAsyncClient.last_kwargs["headers"] = headers
        _FakeAsyncClient.last_kwargs["content"] = content
        return _FakeStreamCtx(_FakeResponse(), self)


class TestHttpNode:
    def test_intranet_blocked_by_default_policy(self):
        """未配置 INTRANET_ALLOWED_CIDRS 时，内网目标一律拒绝（SSRF 防线）。"""
        with pytest.raises(WorkflowNodeError, match="访问策略"):
            asyncio.run(run_http({"url": "http://127.0.0.1:9/secret", "method": "GET"}, {}))

    def test_metadata_address_blocked(self):
        with pytest.raises(WorkflowNodeError):
            asyncio.run(run_http({"url": "http://169.254.169.254/latest/meta-data"}, {}))

    def test_bad_method_rejected(self):
        with pytest.raises(WorkflowNodeError, match="method"):
            asyncio.run(run_http({"url": "http://example.com", "method": "TRACE"}, {}))

    def test_blocked_headers_stripped(self, monkeypatch):
        """Authorization / Cookie 不允许借工作流出站（凭据不得转发到策略外目标）。

        跳过访问策略本身（拒绝语义已由 test_intranet_blocked_by_default_policy
        覆盖），这里聚焦 header 过滤与限额读取。
        """
        from app.services.intranet_policy import PolicyDecision

        monkeypatch.setattr(
            "app.services.intranet_policy.check_url",
            lambda url, **kw: PolicyDecision(True, "test allow"),
        )
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
        result = asyncio.run(run_http({
            "url": "http://example.com/api",
            "method": "POST",
            "headers": {"Authorization": "Bearer sk-1", "Cookie": "a=b", "X-Ok": "1"},
            "body": '{"k": 1}',
        }, {}))
        sent_headers = _FakeAsyncClient.last_kwargs["headers"]
        assert "Authorization" not in sent_headers and "Cookie" not in sent_headers
        assert sent_headers.get("X-Ok") == "1"
        assert result["status"] == 200
        assert result["body"] == "ok"

    def test_get_method_never_sends_body(self, monkeypatch):
        from app.services.intranet_policy import PolicyDecision

        monkeypatch.setattr(
            "app.services.intranet_policy.check_url",
            lambda url, **kw: PolicyDecision(True, "test allow"),
        )
        monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
        asyncio.run(run_http({"url": "http://example.com", "method": "GET", "body": "x"}, {}))
        assert _FakeAsyncClient.last_kwargs["content"] is None


# ---------------------------------------------------------------------------
# knowledge 节点
# ---------------------------------------------------------------------------

class TestKnowledgeNode:
    def test_acl_params_follow_trigger_user(self, monkeypatch):
        captured: dict = {}

        class FakeRetrieval:
            def __init__(self, db):
                captured["db"] = db

            def search(self, **kwargs):
                captured.update(kwargs)
                return [
                    SimpleNamespace(
                        page_id=7, title="制度", snippet="片段" * 300, content="全" * 5000,
                        page_type="concept", score=0.9, sources=["bm25"],
                        authority_level="L2",
                    )
                ]

        import app.db.session as db_mod
        import app.services.knowledge.retrieval as retrieval_mod

        monkeypatch.setattr(retrieval_mod, "KnowledgeRetrieval", FakeRetrieval)

        class FakeSession:
            def close(self):
                pass

        monkeypatch.setattr(db_mod, "SessionLocal", FakeSession)

        handler = make_knowledge_handler(user_id=42, is_admin=False)
        result = asyncio.run(handler(
            {"query": "报销制度", "kb_ids": [1, 2], "top_k": "3"}, {}
        ))
        assert captured["user_id"] == 42
        assert captured["is_admin"] is False
        assert captured["knowledge_base_ids"] == [1, 2]
        assert captured["max_results"] == 3
        assert result["count"] == 1
        # 片段要截断（1000 字符上限），不能把全量内容塞进输出
        assert len(result["results"][0]["content"]) <= 1000

    def test_top_k_clamped(self, monkeypatch):
        captured: dict = {}

        class FakeRetrieval:
            def __init__(self, db):
                pass

            def search(self, **kwargs):
                captured.update(kwargs)
                return []

        import app.db.session as db_mod
        import app.services.knowledge.retrieval as retrieval_mod

        monkeypatch.setattr(retrieval_mod, "KnowledgeRetrieval", FakeRetrieval)

        class FakeSession:
            def close(self):
                pass

        monkeypatch.setattr(db_mod, "SessionLocal", FakeSession)

        handler = make_knowledge_handler(user_id=None, is_admin=True)
        asyncio.run(handler({"query": "q", "top_k": 999}, {}))
        assert captured["max_results"] <= 20
        assert captured["is_admin"] is True

    def test_empty_query_rejected(self):
        handler = make_knowledge_handler(user_id=None, is_admin=False)
        with pytest.raises(WorkflowNodeError, match="query"):
            asyncio.run(handler({"query": ""}, {}))


class TestTemplateNode:
    def test_passthrough_and_type_check(self):
        assert asyncio.run(run_template({"template": "纯文本"}, {})) == "纯文本"
        with pytest.raises(WorkflowNodeError):
            asyncio.run(run_template({"template": 123}, {}))
