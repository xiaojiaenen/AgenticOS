"""模式注册一致性守卫。

新增一个 agent mode 要改 5 个地方（AGENT_MODES / _MODE_TOOL_REGISTRARS /
两处 Pydantic 正则 / MODE_DEFAULT_PROMPTS / BUILTIN_AGENT_PROFILES /
factory 的注册分支）。漏改任何一处都只有一种表现：模式在某一层"不存在"，
而且通常是静默的 —— 比如漏了 stream 请求体的正则，前端表现是"发了消息
什么都没发生"，排查起来很贵。

这里把「这些地方必须覆盖同一组模式」变成断言。
"""

from __future__ import annotations

import re

import pytest

from app.services.agent_profile_service import (
    BUILTIN_AGENT_PROFILES,
    MODE_DEFAULT_PROMPTS,
)
from app.services.tool_config_service import AGENT_MODES

#: 后端必须认识的全部模式
EXPECTED_MODES = {"general", "ppt", "website", "email", "bigdata", "sheet"}

PATTERN_FILES = [
    "app/schemas/agent.py",
    "app/schemas/agent_profiles.py",
]


def _extract_pattern_modes(source: str) -> set[str]:
    """从 `pattern="^(a|b|c)$"` 里取出模式集合。"""
    modes: set[str] = set()
    for match in re.finditer(r'pattern="\^?\((?P<alts>[^)]*)\)\$?"', source):
        modes.update(alt.strip() for alt in match.group("alts").split("|") if alt.strip())
    return modes


def test_agent_modes_covers_expected_set():
    assert set(AGENT_MODES) == EXPECTED_MODES


@pytest.mark.parametrize("path", PATTERN_FILES)
def test_schema_patterns_cover_every_mode(path: str):
    """每个 schema 的 response_mode 正则都要包含全部模式。

    漏改的典型症状：请求被 422 挡掉，前端表现为"发了消息没反应"。
    """
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    found = _extract_pattern_modes(source)
    missing = EXPECTED_MODES - found
    assert not missing, f"{path} 的 response_mode 正则漏了模式：{sorted(missing)}"


def test_every_mode_has_a_default_prompt():
    assert set(MODE_DEFAULT_PROMPTS) == EXPECTED_MODES


def test_every_mode_has_default_tools():
    from app.services.tool_config_service import DEFAULT_MODE_TOOLS

    assert set(DEFAULT_MODE_TOOLS) == EXPECTED_MODES


def test_builtin_profiles_use_known_modes():
    for slug, profile in BUILTIN_AGENT_PROFILES.items():
        assert profile["response_mode"] in EXPECTED_MODES, (
            f"内置 profile {slug} 用了未注册的模式 {profile['response_mode']}"
        )


def test_sheet_mode_registers_its_tools():
    """表格模式必须真的挂上表格工具，否则模型会对着空气回答。"""
    from app.services.tool_config_service import (
        _MODE_TOOL_REGISTRARS,
        DEFAULT_MODE_TOOLS,
    )

    assert "sheet" in _MODE_TOOL_REGISTRARS
    assert _MODE_TOOL_REGISTRARS["sheet"] == [
        ("app.tools.sheet_tools", "register_sheet_tools")
    ]
    enabled = {
        name
        for name, config in DEFAULT_MODE_TOOLS["sheet"].items()
        if isinstance(config, dict) and config.get("enabled")
    }
    for required in ("create_workbook", "set_range", "set_formula", "build_sheet"):
        assert required in enabled, f"表格模式缺少必需工具 {required}"


def test_factory_registers_sheet_tools_for_sheet_mode():
    """factory 的注册分支和 _MODE_TOOL_REGISTRARS 都要有 sheet。"""
    from pathlib import Path

    factory = Path("app/services/agent/factory.py").read_text(encoding="utf-8")
    assert 'profile.response_mode == "sheet"' in factory
    assert "register_sheet_tools" in factory
