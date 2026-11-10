"""回归测试：办公产物 / 网站构建 / 私密站点签名，覆盖本次修掉的真实缺陷。

这些用例都来自「真的去对话、真的看产物」时暴露的问题，不是接口形状测试：

1. 办公工具必须真的在 profile 里启用（create_document 等曾被 catalog 过滤掉）
2. sandbox 成功退出必须报 exit_code=0（曾被 `or -1` 改写成失败）
3. 构建前必须修好 index.html 的 type="module" 与绝对路径
4. 私密站点的 CSS/JS 子资源必须能取到（相对 URL 会丢 ?t=，改用 cookie）
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


# ── 1. 办公工具必须启用 ────────────────────────────────────────────────


def test_office_profile_has_document_and_sheet_tools():
    """办公助手必须真的启用文档/表格工具。

    早先 TOOL_CATALOG 里没有 create_document / create_workbook，
    `_ensure_profile_tools` 只遍历 TOOL_CATALOG，这些工具永远不会有行；
    而 `_merge_tools_with_catalog` 又把不在 catalog 里的行过滤掉，
    于是用户让办公助手写 Word 只能得到「文档工具不可用」。
    """
    from app.db.session import SessionLocal
    from app.db.models import AgentProfileModel
    from app.services.agent_profile_service import AgentProfileService
    from app.services.tool_config_service import DEFAULT_MODE_TOOLS

    db = SessionLocal()
    try:
        profile = (
            db.query(AgentProfileModel).filter(AgentProfileModel.slug == "office").one_or_none()
        )
        assert profile is not None, "内置办公助手 profile 必须存在"

        payload = AgentProfileService()._serialize_profiles(db, [profile])
        enabled = {t["tool_name"] for t in payload[0]["tools"] if t["enabled"]}

        for tool in ("create_document", "build_document", "create_workbook", "set_range", "build_sheet"):
            assert tool in enabled, f"办公助手缺少启用的工具：{tool}"
    finally:
        db.close()

    # 这些工具必须同时出现在默认值里，否则新环境种子后仍然是关的
    office_defaults = DEFAULT_MODE_TOOLS["office"]
    for tool in ("create_document", "create_workbook"):
        assert office_defaults.get(tool, {}).get("enabled") is True


def test_tool_catalog_contains_office_tools():
    """办公工具必须登记进 TOOL_CATALOG，管理界面才能看到并切换。"""
    from app.services.tool_config_service import TOOL_CATALOG

    for tool in (
        "create_document",
        "read_document",
        "build_document",
        "create_workbook",
        "set_range",
        "set_formula",
        "read_range",
        "add_sheet",
        "set_layout",
        "build_sheet",
        "describe_workbook",
    ):
        assert tool in TOOL_CATALOG, f"TOOL_CATALOG 缺少 {tool}"


def test_create_document_accepts_structured_blocks():
    """仿真模型真实写法：列表和表格块不能被校验打回。

    早先 blocks 只允许 h1~h4 / paragraph，模型写 bullets 或 table 时整块被拒，
    只能把要点塞进散文，成品质量明显下降。
    """
    from app.tools.doc_tools import _normalize_blocks

    blocks = [
        {"type": "h1", "text": "本周工作总结"},
        {"type": "h2", "text": "本周完成"},
        {"type": "bullets", "items": ["完成登录模块", "修复3个缺陷"]},
        {"type": "ordered", "items": ["第一步", "第二步"]},
        {"type": "table", "header": ["月份", "金额"], "rows": [["1月", "100"]]},
        {"type": "quote", "text": "一句话重点"},
        {"type": "paragraph", "text": "正文段落"},
    ]
    cleaned, errors = _normalize_blocks(blocks)

    assert errors == [], f"结构化块不应报错：{errors}"
    kinds = [b["type"] for b in cleaned]
    assert "bullets" in kinds and "table" in kinds and "quote" in kinds
    # 列表块的 items 必须原样保留，不能被抹成 text=""
    bullets = next(b for b in cleaned if b["type"] == "bullets")
    assert bullets["items"] == ["完成登录模块", "修复3个缺陷"]


def test_normalize_blocks_rejects_empty_bullets():
    """空列表要报错：静默放行会让模型以为写成功了。"""
    from app.tools.doc_tools import _normalize_blocks

    _, errors = _normalize_blocks([{"type": "bullets", "items": []}])
    assert errors, "空 items 必须报错"


# ── 2. sandbox 退出码 ──────────────────────────────────────────────────


def test_sandbox_reports_zero_exit_code_on_success(tmp_path):
    """成功命令必须报 exit_code=0。

    早先写的是 `exit_code=proc.returncode or -1`，`0` 被当成假值改写成 -1，
    于是 `npm install` 成功也被判成「失败（退出码 -1）」，构建流程反复清
    node_modules 重来，网站永远构建不出来。
    """
    from app.services.sandbox import Sandbox

    async def run() -> None:
        sandbox = Sandbox(workspace=tmp_path, timeout=30)
        result = await sandbox.execute("echo ok", timeout=30)
        assert result.success is True
        assert result.exit_code == 0, f"成功命令被报成 exit_code={result.exit_code}"
        assert "ok" in result.stdout

    asyncio.run(run())


# ── 3. index.html 构建前修复 ───────────────────────────────────────────


def test_normalize_index_html_restores_module_and_relative_paths(tmp_path):
    """模型重写 HTML 时常丢掉 type="module"、写成绝对路径。

    丢了 module：Vite 不打包该脚本，线上 404，交互全失效。
    绝对路径：站点挂在 /sites/<project>/ 子路径下，样式和脚本 404。
    """
    from app.tools.website_tools import _normalize_index_html

    html = (
        "<html><head>"
        '<link rel="stylesheet" href="/css/style.css">'
        "</head><body>"
        '<script src="/js/main.js" defer></script>'
        "</body></html>"
    )
    (tmp_path / "index.html").write_text(html, encoding="utf-8")

    notes = _normalize_index_html(tmp_path)
    out = (tmp_path / "index.html").read_text(encoding="utf-8")

    assert 'type="module"' in out, "必须补回 type=module"
    assert 'href="./css/style.css"' in out, "绝对路径必须改成相对路径"
    assert 'src="./js/main.js"' in out
    assert notes, "发生改动时应该返回说明"


def test_normalize_index_html_leaves_good_html_untouched(tmp_path):
    """已经正确的 HTML 不应被改动（避免每次构建都写盘）。"""
    from app.tools.website_tools import _normalize_index_html

    html = (
        '<html><head><link rel="stylesheet" href="./css/style.css"></head>'
        '<body><script type="module" src="./js/main.js"></script></body></html>'
    )
    (tmp_path / "index.html").write_text(html, encoding="utf-8")

    notes = _normalize_index_html(tmp_path)
    assert notes == []
    assert (tmp_path / "index.html").read_text(encoding="utf-8") == html


def test_normalize_index_html_skips_external_scripts(tmp_path):
    """CDN 脚本不能加 type=module，否则会被当成本地模块处理。"""
    from app.tools.website_tools import _normalize_index_html

    html = '<html><head><script src="https://cdn.example.com/lib.js"></script></head></html>'
    (tmp_path / "index.html").write_text(html, encoding="utf-8")

    _normalize_index_html(tmp_path)
    out = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'type="module"' not in out


# ── 4. tool_calls 配对修复 ────────────────────────────────────────────


def test_tool_pair_repair_fills_missing_results():
    """残缺历史必须被补齐，否则上游每次都 400。

    DeepSeek 要求每个 tool_call 都有配对的 tool 消息。并发批处理被取消、
    审批超时、达到步数上限都会留下残缺历史，一旦落库，这个会话此后
    每次都报 `insufficient tool messages following tool_calls`。
    """
    from wuwei.core.message import AIMessage, FunctionCall, HumanMessage, ToolCall, ToolMessage

    from app.services.agent.factory import ToolPairRepairMiddleware

    def call(cid: str, name: str) -> ToolCall:
        return ToolCall(id=cid, type="function", function=FunctionCall(name=name, arguments={}))

    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[call("c1", "calc"), call("c2", "time")]),
        ToolMessage(content="ok", tool_call_id="c1", name="calc"),
    ]

    class _State:
        def __init__(self, msgs):
            self.messages = msgs

    class _Ctx:
        def __init__(self, msgs):
            self.state = _State(msgs)

    ctx = asyncio.run(ToolPairRepairMiddleware().before_llm(_Ctx(messages)))
    out = ctx.state.messages

    declared = {c.id for m in out for c in (getattr(m, "tool_calls", None) or [])}
    answered = {m.tool_call_id for m in out if getattr(m, "role", None) == "tool"}
    assert declared == answered, f"仍有未配对的调用：{declared - answered}"
    # 补出来的结果必须带工具名（ToolMessage.name 是必填）
    filled = [m for m in out if m.tool_call_id == "c2"]
    assert filled and filled[0].name == "time"


def test_tool_pair_repair_drops_orphan_results():
    """没有对应 tool_call 的孤立结果必须删掉，上游同样会因此报错。"""
    from wuwei.core.message import HumanMessage, ToolMessage

    from app.services.agent.factory import ToolPairRepairMiddleware

    messages = [
        HumanMessage(content="hi"),
        ToolMessage(content="stray", tool_call_id="ghost", name="ghost"),
    ]

    class _State:
        def __init__(self, msgs):
            self.messages = msgs

    class _Ctx:
        def __init__(self, msgs):
            self.state = _State(msgs)

    ctx = asyncio.run(ToolPairRepairMiddleware().before_llm(_Ctx(messages)))
    assert [m for m in ctx.state.messages if getattr(m, "role", None) == "tool"] == []


def test_tool_pair_repair_is_noop_on_healthy_history():
    """健康历史不应有任何改动（热路径零开销）。"""
    from wuwei.core.message import AIMessage, FunctionCall, HumanMessage, ToolCall, ToolMessage

    from app.services.agent.factory import ToolPairRepairMiddleware

    call = ToolCall(id="c1", type="function", function=FunctionCall(name="calc", arguments={}))
    messages = [
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content="ok", tool_call_id="c1", name="calc"),
    ]

    class _State:
        def __init__(self, msgs):
            self.messages = msgs

    class _Ctx:
        def __init__(self, msgs):
            self.state = _State(msgs)

    ctx = asyncio.run(ToolPairRepairMiddleware().before_llm(_Ctx(messages)))
    assert ctx.state.messages == messages
