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

#: 后端必须认识的全部模式。
#: office 是统一的办公智能体（Excel + Word）；sheet 已并入其中，
#: 专业 PPT 由独立的 ppt 模式负责（SVG→PPTX 自研管线，非 Univer）。
EXPECTED_MODES = {"general", "ppt", "website", "email", "bigdata", "office"}

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


def test_office_mode_registers_both_toolsets():
    """办公模式必须同时挂上表格与文档工具，否则其中一个能力是空气。"""
    from app.services.tool_config_service import (
        _MODE_TOOL_REGISTRARS,
        DEFAULT_MODE_TOOLS,
    )

    assert _MODE_TOOL_REGISTRARS["office"] == [
        ("app.tools.sheet_tools", "register_sheet_tools"),
        ("app.tools.doc_tools", "register_doc_tools"),
    ]
    enabled = {
        name
        for name, config in DEFAULT_MODE_TOOLS["office"].items()
        if isinstance(config, dict) and config.get("enabled")
    }
    for required in (
        "create_workbook", "set_range", "set_formula", "build_sheet",
        "create_document", "build_document",
    ):
        assert required in enabled, f"办公模式缺少必需工具 {required}"


def test_office_prompt_rejects_ppt_requests():
    """办公智能体不得越界做 PPT —— 那是独立 PPT 智能体的职责。

    开源版 Univer 没有 Slides preset（npm 404），也没有导出能力；
    把 PPT 混进办公智能体只会产出拿不走的东西。提示词必须把 PPT 请求
    引导去专业 PPT 智能体。
    """
    from app.services.agent_profile_service import MODE_DEFAULT_PROMPTS

    prompt = MODE_DEFAULT_PROMPTS["office"]
    assert "PPT" in prompt and "PPT 设计师" in prompt


def test_factory_registers_office_toolsets():
    """factory 的注册分支必须同时挂表格与文档 registrar。"""
    from pathlib import Path

    factory = Path("app/services/agent/factory.py").read_text(encoding="utf-8")
    assert 'profile.response_mode == "office"' in factory
    assert "register_sheet_tools" in factory
    assert "register_doc_tools" in factory


def test_sheet_artifact_keys_match_orchestrator_reader():
    """产物字典的键必须和 orchestrator 读取时用的键一致。

    踩过的坑：产物字段从 artifactId 改成 artifact_id（与 website 对齐）后，
    orchestrator 仍在取旧键 → reference 变成 None → 版本索引从不落盘 →
    版本条静默不显示。字段名对不上时没有任何报错，只能靠这个断言兜住。
    """
    import inspect
    from pathlib import Path

    import app.services.agent.artifacts as artifacts_mod

    source = inspect.getsource(artifacts_mod.ArtifactFactory.build_sheet_artifact)
    produced = set(re.findall(r'"([a-z_]+)":', source))
    assert {"artifact_id", "title", "snapshot"} <= produced, (
        f"表格产物字段缺失，实际产出：{sorted(produced)}"
    )

    orchestrator = Path("app/services/agent/orchestrator.py").read_text(encoding="utf-8")
    branch = orchestrator.split("if sheet_mode:")[-1]
    assert 'artifact.get("artifact_id")' in branch, (
        "orchestrator 的表格分支没有用 artifact_id 读产物，版本快照会静默失效"
    )
    assert 'artifact.get("artifactId")' not in branch, (
        "orchestrator 还在用旧的驼峰键读表格产物"
    )
