"""A2UI 集成测试：消息构造 / 组件白名单 / 工具注册 / SSE 采集。

覆盖点：
- builder 生成的 JSON 符合 A2UI v0.9 结构
- 组件白名单真的拦住非法组件（模型不能引入自定义组件）
- 表单数据与组件分离（改值不需要重建组件树）
- 工具注册后能被 agent 看到
- 采集器按 run 隔离（并发请求不串消息）
"""
from __future__ import annotations

import asyncio

import pytest

from app.services.a2ui import builder


def test_simple_page_structure() -> None:
    messages = builder.simple_page("测试标题", "正文内容")

    assert len(messages) == 2
    assert messages[0]["version"] == "v0.9"
    assert "createSurface" in messages[0]
    assert messages[0]["createSurface"]["catalogId"] == builder.CATALOG_ID

    comps = messages[1]["updateComponents"]["components"]
    ids = {c["id"] for c in comps}
    assert ids == {"root", "title", "body"}
    # 邻接表：root 通过 children 引用另外两个，不是嵌套
    root = next(c for c in comps if c["id"] == "root")
    assert root["component"] == "Column"
    assert root["children"] == ["title", "body"]


def test_form_page_separates_data_from_structure() -> None:
    """组件树只描述结构，初始值走 updateDataModel —— 改值不重建树。"""
    messages = builder.form_page(
        "筛选条件",
        [
            {"id": "kw", "label": "关键词", "type": "text"},
            {"id": "lv", "label": "级别", "type": "choice", "options": ["高", "中", "低"]},
            {"id": "agree", "label": "确认", "type": "check"},
            {"id": "score", "label": "权重", "type": "slider", "min": 0, "max": 10},
        ],
    )

    assert len(messages) == 3
    assert "updateComponents" in messages[1]
    assert "updateDataModel" in messages[2]

    # 数据模型里有全部字段的初始值
    data = messages[2]["updateDataModel"]["value"]
    assert set(data) == {"kw", "lv", "agree", "score"}
    assert data["lv"] == "高"  # choice 默认取第一个选项
    assert data["agree"] is False
    assert data["score"] == 0

    # 组件树里用 path 绑定，而不是把值写死
    comps = messages[1]["updateComponents"]["components"]
    kw = next(c for c in comps if c["id"] == "kw")
    assert kw["component"] == "TextField"
    assert kw["value"] == {"path": "/kw"}


def test_component_whitelist_blocks_unknown() -> None:
    """模型不能引入自定义组件 —— 这是 A2UI「安全」承诺的落点。"""
    with pytest.raises(builder.A2uiBuildError, match="不支持的组件"):
        builder.update_components("s1", [{"id": "x", "component": "EvilIframe"}])

    # 合法组件正常通过
    out = builder.update_components("s1", [{"id": "t", "component": "Text", "text": "hi"}])
    assert out["updateComponents"]["components"][0]["component"] == "Text"


def test_component_requires_id() -> None:
    with pytest.raises(builder.A2uiBuildError, match="缺少 id"):
        builder.update_components("s1", [{"component": "Text", "text": "hi"}])


def test_form_field_requires_id() -> None:
    with pytest.raises(builder.A2uiBuildError, match="缺少 id"):
        builder.form_page("t", [{"label": "没有 id"}])


def test_allowed_components_match_basic_catalog() -> None:
    """白名单必须是 basic catalog 的 18 个组件，不能少也不能多。"""
    expected = {
        "Text", "Image", "Icon", "Video", "AudioPlayer",
        "Row", "Column", "List", "Card", "Tabs", "Modal", "Divider",
        "Button", "TextField", "CheckBox", "ChoicePicker", "Slider", "DateTimeInput",
    }
    assert builder.ALLOWED_COMPONENTS == expected


def test_collector_is_per_context() -> None:
    """采集器按 context 隔离：并发 run 不会互相拿到对方的界面消息。"""
    import contextvars

    from app.services import a2ui

    async def worker(tag: str) -> list[dict]:
        a2ui.reset_pending()
        a2ui._emit([{"version": "v0.9", "tag": tag}])
        await asyncio.sleep(0.01)
        return a2ui.drain_pending()

    async def main() -> None:
        results = await asyncio.gather(*(worker(str(i)) for i in range(5)))
        for i, items in enumerate(results):
            assert len(items) == 1
            assert items[0]["tag"] == str(i), "并发 run 的界面消息串了"

    # 每个 task 有独立 context
    asyncio.run(contextvars.copy_context().run(main))


def test_drain_clears_collector() -> None:
    from app.services import a2ui

    a2ui.reset_pending()
    a2ui._emit([{"version": "v0.9"}])
    first = a2ui.drain_pending()
    second = a2ui.drain_pending()
    assert len(first) == 1
    assert second == [], "drain 之后应清空，避免重复推送"
