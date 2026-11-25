"""工具清点覆盖率：注册表里有的，后台列表必须有。

## 为什么需要这个测试

用户反复报「渲染 UI 工具咋没有在后台智能体工具列表」「为什么总是有遗漏的」。

根因是**工具注册有两条路径，而目录只跟了其中一条**：
1. per-mode registrar（`_MODE_TOOL_REGISTRARS`）—— 自动发现，不会漏
2. factory 直接 `registry.register(...)` —— 过去**完全不进目录**，
   导致 render_ui / render_form / generate_image / 文件工具全都不显示

修法是把第 2 类收进 `_GLOBAL_TOOL_REGISTRARS`。但"把 5 个模块加进一张表"
本身还是会漏 —— 所以这里做**反向校验**：真的起一个 ToolRegistry，按
factory 的真实顺序注册全部工具，然后断言每一个都在后台目录里。

以后任何人新增工具（无论走哪条路径）而忘了登记，这个测试就会红，
而且错误信息直接告诉他漏了哪个。
"""

from __future__ import annotations

import pytest


def _factory_registered_tools() -> set[str]:
    """按 factory 的真实顺序注册，得到"任何模式下都可用"的工具全量。

    这里刻意**照抄 factory 的注册清单**而不是只读 `_GLOBAL_TOOL_REGISTRARS`
    —— 测试要能发现"factory 加了工具但没登记到目录"，读同一张表就发现不了。
    """
    from app.services.agent.native.tool_registry import ToolRegistry

    registry = ToolRegistry()
    # 与 app/services/agent/factory.py 的全局注册段保持一致
    from app.tools.chart_render_tools import register_chart_render_tools
    from app.tools.data_analysis_tools import register_data_analysis_tools
    from app.services.a2ui import register_a2ui_tools
    from app.tools.image_gen_tools import register_image_gen_tools
    from app.tools.website_file_tools import register_website_file_tools

    register_chart_render_tools(registry)
    register_data_analysis_tools(registry)
    register_a2ui_tools(registry)
    register_image_gen_tools(registry)
    register_website_file_tools(registry)

    return {tool.name for tool in registry.list_tools()}


@pytest.fixture(scope="module")
def factory_tools() -> set[str]:
    return _factory_registered_tools()


class TestCatalogCoverage:
    def test_every_factory_tool_is_in_catalog(self, factory_tools):
        """factory 注册的全局工具，一个都不能不在目录里。

        失败时按工具名列出缺失项 —— 报错信息本身就是修复指引。
        """
        from app.services.tool_config_service import TOOL_CATALOG

        missing = sorted(t for t in factory_tools if t not in TOOL_CATALOG)
        assert not missing, (
            f"这些工具已注册但后台列表看不到（缺 TOOL_CATALOG 条目）：{missing}\n"
            "修法：在 tool_config_service.py 的 TOOL_CATALOG 里加条目"
            "（label 写中文名），并确认 _GLOBAL_TOOL_REGISTRARS 含其模块。"
        )

    def test_every_factory_tool_is_in_global_registrars(self, factory_tools):
        """同理，全局 registrar 表也要覆盖，否则默认工具表里没有它。"""
        from app.services.tool_config_service import discover_global_tools

        discovered = discover_global_tools()
        missing = sorted(t for t in factory_tools if t not in discovered)
        assert not missing, (
            f"这些工具注册了但未被发现（缺 _GLOBAL_TOOL_REGISTRARS 条目）：{missing}"
        )

    def test_factory_tool_appears_in_default_mode_tools(self, factory_tools):
        """每个全局工具都该在**所有**模式的默认工具表里（否则新智能体拿不到）。"""
        from app.services.tool_config_service import AGENT_MODES, DEFAULT_MODE_TOOLS

        for mode in AGENT_MODES:
            available = DEFAULT_MODE_TOOLS.get(mode, {})
            missing = sorted(t for t in factory_tools if t not in available)
            assert not missing, f"{mode} 模式的默认工具表缺少：{missing}"

    def test_render_ui_specifically_is_listed(self):
        """用户点名报障的那个工具：必须有中文名与描述。"""
        from app.services.tool_config_service import TOOL_CATALOG

        entry = TOOL_CATALOG.get("render_ui")
        assert entry is not None, "render_ui 不在目录里"
        assert entry["label"] == "生成界面"
        assert entry["description"], "render_ui 缺描述"


class TestCatalogQuality:
    def test_no_english_only_labels(self):
        """目录条目的 label 不该等于工具名（那说明只是兜底，没有中文名）。"""
        from app.services.tool_config_service import TOOL_CATALOG

        offenders = [
            name
            for name, item in TOOL_CATALOG.items()
            if str(item.get("label") or "") == name
        ]
        assert not offenders, (
            f"这些工具只有英文名、没有中文 label：{sorted(offenders)}"
        )

    def test_all_entries_have_description(self):
        from app.services.tool_config_service import TOOL_CATALOG

        missing = [
            name
            for name, item in TOOL_CATALOG.items()
            if not str(item.get("description") or "").strip()
        ]
        assert not missing, f"这些工具缺 description：{sorted(missing)}"

    def test_approval_scope_references_real_sub_tools(self):
        """approval_scope 里的名字必须真的出现在 sub_tools 或工具自身。"""
        from app.services.tool_config_service import TOOL_CATALOG

        for name, item in TOOL_CATALOG.items():
            scope = item.get("approval_scope") or []
            sub = item.get("sub_tools") or {}
            for entry in scope:
                assert entry in sub or entry == name, (
                    f"{name} 的 approval_scope 引用了不存在的子工具 {entry}"
                )
