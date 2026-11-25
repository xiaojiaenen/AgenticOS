"""SOPS 密钥加载层 + LiteLLM SDK 旁路 PoC 回归（战线 D / 3B.2 / 3F.0）。

SOPS：本地 CLI 解密加密 dotenv，合并进 os.environ（真实环境变量优先），
未配置/缺二进制/解密失败只 CRITICAL 告警不阻断启动。
LiteLLM：Python SDK（纯库）旁路 PoC 的映射契约（fake litellm 模块锁定
消息/工具/usage/finish_reason 双向对齐）；Proxy 形态按红线排除。
"""

from __future__ import annotations

import json
import stat
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

from app.core import secret_loader


# ── SOPS ──────────────────────────────────────────────────────────────


def _fake_sops_script(tmp_path, decrypted: str):
    """造一个可执行的假 sops：忽略参数，输出解密结果。"""
    script = tmp_path / "fake-sops"
    script.write_text("#!/bin/sh\ncat <<'EOF'\n" + decrypted + "\nEOF\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.fixture(autouse=True)
def _reset_loader_state():
    secret_loader._LOADED = False
    yield
    secret_loader._LOADED = False


def test_parse_dotenv_basic():
    text = "# comment\nexport A=1\nB = \"quoted value\"\nC='sq'\nD=with spaces\n"
    assert secret_loader._parse_dotenv(text) == {
        "A": "1",
        "B": "quoted value",
        "C": "sq",
        "D": "with spaces",
    }


def test_no_sops_file_is_noop():
    with patch.dict("os.environ", {"SOPS_FILE": ""}, clear=False):
        assert secret_loader.load_sops_secrets(force=True) == {}


def test_sops_merge_respects_real_env(monkeypatch, tmp_path):
    """真实环境变量优先：密文里的同名键不覆盖宿主显式配置。"""
    real = tmp_path / "real.env"
    real.write_text("SOPS_TEST_SECRET=from-vault\nSOPS_TEST_BOTH=vault-value\n")
    monkeypatch.setenv("SOPS_FILE", str(real))
    monkeypatch.setenv("SOPS_TEST_BOTH", "host-value")
    # 假 sops 输出「解密后的 dotenv」
    monkeypatch.setenv(
        "SOPS_BINARY",
        _fake_sops_script(tmp_path, "SOPS_TEST_SECRET=from-vault\nSOPS_TEST_BOTH=vault-value"),
    )

    merged = secret_loader.load_sops_secrets(force=True)
    assert merged == {"SOPS_TEST_SECRET": "from-vault"}
    import os

    assert os.environ["SOPS_TEST_BOTH"] == "host-value"
    assert os.environ["SOPS_TEST_SECRET"] == "from-vault"


def test_sops_missing_binary_loud_but_not_fatal(monkeypatch, tmp_path, caplog):
    real = tmp_path / "real.env"
    real.write_text("K=v\n")
    monkeypatch.setenv("SOPS_FILE", str(real))
    monkeypatch.delenv("SOPS_BINARY", raising=False)
    monkeypatch.setattr(secret_loader.shutil, "which", lambda name: None)

    with caplog.at_level("CRITICAL", logger="agenticos.secrets"):
        assert secret_loader.load_sops_secrets(force=True) == {}
    assert any("sops 可执行文件不可用" in r.message for r in caplog.records)


def test_sops_decrypt_failure_not_fatal(monkeypatch, tmp_path, caplog):
    real = tmp_path / "real.env"
    real.write_text("K=v\n")
    fail_script = tmp_path / "fail-sops"
    fail_script.write_text("#!/bin/sh\nexit 1\n")
    fail_script.chmod(fail_script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("SOPS_FILE", str(real))
    monkeypatch.setenv("SOPS_BINARY", str(fail_script))  # exit 1
    with caplog.at_level("CRITICAL", logger="agenticos.secrets"):
        assert secret_loader.load_sops_secrets(force=True) == {}
    assert any("sops 解密" in r.message for r in caplog.records)


# ── LiteLLM PoC ───────────────────────────────────────────────────────


class _FakeLiteLLM(ModuleType):
    """litellm 模块替身：捕获 completion 参数，返回脚本化响应。"""

    def __init__(self, response):
        super().__init__("litellm")
        self.calls: list[dict] = []
        self._response = response

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _fake_response():
    """OpenAI 风格 completion 响应（litellm 的返回形态）。"""
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="123*456 = 56088",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="calculate", arguments=json.dumps({"expression": "123*456"})
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        usage=usage,
        model="fake-model",
    )


def _setup_fake_module(monkeypatch, response):
    fake = _FakeLiteLLM(response)
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return fake


@pytest.mark.asyncio
async def test_litellm_gateway_maps_messages_tools_and_usage(monkeypatch):
    from app.services.agent.native.types import FunctionCall, HumanMessage, ToolCall
    from app.services.agent.native.tool_registry import Tool as WuweiTool, ToolParameters

    fake = _setup_fake_module(monkeypatch, _fake_response())

    from app.services.llm_providers.litellm_poc import LiteLLMGateway

    gateway = LiteLLMGateway(model="fake-model", api_key="sk-x", base_url="https://api.example.com/v1")
    messages = [HumanMessage(content="算一下")]
    async def _calc(expression: str) -> dict:
        return {"ok": True}

    tools = [
        WuweiTool(
            name="calculate",
            description="计算",
            parameters=ToolParameters(
                properties={"expression": {"type": "string"}}, required=["expression"]
            ),
            handler=_calc,
        )
    ]
    response = await gateway.generate(messages, tools=tools, stream=False)

    # 请求映射
    call = fake.calls[0]
    assert call["model"] == "fake-model"
    assert call["api_key"] == "sk-x"
    assert call["api_base"] == "https://api.example.com/v1"
    assert call["messages"][0] == {"role": "user", "content": "算一下"}
    assert call["tools"][0]["function"]["name"] == "calculate"

    # 响应映射回 wuwei LLMResponse
    assert response.content == "123*456 = 56088"
    assert response.finish_reason == "tool_calls"
    assert isinstance(response.tool_calls[0], ToolCall)
    assert response.tool_calls[0].function == FunctionCall(name="calculate", arguments={"expression": "123*456"})
    assert response.usage == {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}
    assert response.model == "fake-model"


@pytest.mark.asyncio
async def test_litellm_poc_stream_is_rejected(monkeypatch):
    """PoC 只做非流式；流式走主路径自研网关（明确报错而非静默降级）。"""
    from app.services.llm_providers.litellm_poc import LiteLLMGateway
    from app.services.llm_providers.spec import ProviderConfigError

    _setup_fake_module(monkeypatch, _fake_response())
    gateway = LiteLLMGateway(model="m")
    with pytest.raises(ProviderConfigError):
        await gateway.generate([], stream=True)


def test_litellm_missing_dependency_guides_install(monkeypatch):
    """未装 litellm extra → 明确指引（uv sync --extra litellm）。"""
    monkeypatch.setitem(sys.modules, "litellm", None)  # import 触发 ImportError
    from app.services.llm_providers.litellm_poc import litellm_chat_completion

    with pytest.raises(Exception, match="litellm"):
        litellm_chat_completion(messages=[], model="m")


def test_litellm_registered_as_provider_type():
    from app.services.llm_providers.spec import PROVIDER_TYPES

    assert "litellm" in PROVIDER_TYPES
