"""守护「全站只有一个 LLM 构建入口」这条硬规则。

背景：``LLMGateway.from_env()`` 直连 ``.env`` 里的 ``OPENAI_*``，绕过管理端
配置的 AI 提供商。历史上记忆抽取、知识摄入、PPT 多智能体、公告生成四条链路
就是这么被漏掉的 —— 管理员在界面上切了提供商，这四条链路仍然打老网关，
界面显示已切换、实际一半流量没走新提供商，而且**没有任何日志提示**。

这个测试用 AST 扫描（不是字符串 grep），所以注释和文档字符串里提到
``LLMGateway.from_env`` 不会误报，但真调用一定拦得住。
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.services import llm_factory
from app.services.llm_providers import spec as spec_module

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _python_files() -> list[Path]:
    return sorted(APP_DIR.rglob("*.py"))


def _llmgateway_calls(tree: ast.AST) -> list[int]:
    """找出所有 ``LLMGateway(...)`` / ``LLMGateway.from_env(...)`` 调用行号。"""
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "LLMGateway":
            hits.append(node.lineno)
        elif isinstance(func, ast.Attribute) and func.attr == "from_env":
            target = func.value
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            if name == "LLMGateway":
                hits.append(node.lineno)
    return hits


def test_app_never_constructs_llmgateway_directly() -> None:
    """``app/`` 里不允许直接构造网关，必须经过 llm_factory。

    直接 ``LLMGateway(...)`` 构造和 ``from_env()`` 一样会绕过提供商层
    （拿不到 base_url / Cookie / 用途绑定），所以一并禁掉。
    """
    offenders: list[str] = []
    for path in _python_files():
        # utf-8-sig：容忍仓库里个别带 BOM 的历史文件（BOM 会被 ast.parse 拒绝）
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for lineno in _llmgateway_calls(tree):
            offenders.append(f"{path.relative_to(APP_DIR)}:{lineno}")

    assert not offenders, (
        "以下位置绕过了提供商层，请改用 app.services.llm_factory.build_llm：\n"
        + "\n".join(offenders)
    )


def test_llm_factory_exposes_three_builders() -> None:
    """工厂必须提供这三种构建方式，缺一个就会有人去写旁路。"""
    assert callable(llm_factory.build_llm)
    assert callable(llm_factory.build_llm_for_user)
    assert callable(llm_factory.build_llm_optional)


def test_build_llm_optional_returns_none_instead_of_raising(monkeypatch) -> None:
    """降级构建失败时返回 None 并告警，不抛异常炸掉调用方。"""
    def _boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(llm_factory, "build_llm", _boom)
    assert llm_factory.build_llm_optional(purpose="测试") is None


def test_build_llm_resolves_role_model_from_provider(monkeypatch) -> None:
    """传 role 时按提供商的用途绑定取模型，而不是回落到全局默认模型。"""
    class _Spec:
        model = "main-model"
        extra = {"roles": {"fast": "fast-model", "chat": "chat-model"}}

    captured: dict[str, object] = {}

    def _fake_build(*, max_tokens, timeout, model):
        captured["model"] = model
        captured["max_tokens"] = max_tokens
        captured["timeout"] = timeout
        return object()

    import app.services.llm_providers.runtime as runtime_module

    monkeypatch.setattr(spec_module, "resolve_active_provider", lambda: _Spec())
    monkeypatch.setattr(
        runtime_module, "build_gateway_for_active_provider", _fake_build
    )

    llm_factory.build_llm(role="fast")
    assert captured["model"] == "fast-model"

    # 没绑定这个用途时退回 chat，而不是退回空
    llm_factory.build_llm(role="unknown-role")
    assert captured["model"] == "chat-model"

    # 显式指定模型时以调用方为准
    llm_factory.build_llm(role="fast", model="pinned-model")
    assert captured["model"] == "pinned-model"


def test_build_llm_uses_global_defaults_for_tokens_and_timeout(monkeypatch) -> None:
    """max_tokens / timeout 留空时取全局默认，避免各调用点各写一份。"""
    from app.core.config import get_settings

    captured: dict[str, object] = {}

    def _fake_build(*, max_tokens, timeout, model):
        captured["max_tokens"] = max_tokens
        captured["timeout"] = timeout
        return object()

    import app.services.llm_providers.runtime as runtime_module

    monkeypatch.setattr(
        runtime_module, "build_gateway_for_active_provider", _fake_build
    )

    settings = get_settings()
    llm_factory.build_llm()
    assert captured["max_tokens"] == settings.agent_max_tokens
    assert captured["timeout"] == settings.llm_timeout
