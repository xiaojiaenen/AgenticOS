"""表格能力的端到端测试：Python 工具 → Node 运行时 → 快照落盘 → 产物重建。

这些用例需要一个真实的 node 可执行文件和已安装的 sheet-runtime 依赖。
依赖缺失时整体跳过，而不是失败——CI 的后端 job 不装 Node。
"""

from __future__ import annotations

import json
import shutil

import pytest

from app.services.office import document_service as doc
from app.services.office import service as sheet
from app.services.office.runtime import NODE_MODULES, RUNTIME_DIR, SERVER_SCRIPT

RUNTIME_READY = (
    shutil.which("node") is not None
    and NODE_MODULES.is_dir()
    and SERVER_SCRIPT.is_file()
)

pytestmark = pytest.mark.skipif(
    not RUNTIME_READY, reason=f"办公运行时未就绪（node 或 {RUNTIME_DIR}/node_modules）"
)


@pytest.fixture
def session_id():
    sid = "sheet-test-session"
    yield sid
    sheet.forget_session(sid)


@pytest.mark.anyio
async def test_creates_workbook_and_computes_formulas(session_id):
    created = await sheet.create_workbook(session_id, 1, "季度销售", "汇总")
    assert created["sheetName"] == "汇总"
    assert created["sheets"] == ["汇总"]

    await sheet.set_range(session_id, "汇总", "A1:C1", [["季度", "销售额", "同比"]])
    await sheet.set_range(
        session_id, "汇总", "A2:C3", [["Q1", 120, 0.12], ["Q2", 150, 0.25]]
    )
    total = await sheet.set_formula(session_id, "汇总", "B4", "=SUM(B2:B3)")
    assert total["computed"] == 270

    verdict = await sheet.set_formula(
        session_id, "汇总", "C4", '=IF(B4>200,"达标","未达标")'
    )
    assert verdict["computed"] == "达标"

    read = await sheet.read_range(session_id, "汇总", "A1:C4")
    assert read["values"][0] == ["季度", "销售额", "同比"]
    assert read["values"][3][1] == 270


@pytest.mark.anyio
async def test_rejects_oversized_write(session_id):
    await sheet.create_workbook(session_id, 1, "溢出测试")
    with pytest.raises(sheet.SheetServiceError) as excinfo:
        await sheet.set_range(
            session_id, None, "A1:C1", [["太大", "太大", "太大"], ["x", "y", "z"]]
        )
    # 错误信息要能指导模型修正，所以必须带容量对比
    assert "容量" in str(excinfo.value)
    assert "A1:C10" in str(excinfo.value)


@pytest.mark.anyio
async def test_build_writes_snapshot_and_rebuilds_artifact(session_id, monkeypatch):
    from app.services.agent.artifacts import ArtifactFactory

    await sheet.create_workbook(session_id, 1, "构建测试", "汇总")
    await sheet.set_range(session_id, "汇总", "A1:B2", [["项目", "数量"], ["甲", 7]])
    await sheet.set_formula(session_id, "汇总", "B3", "=SUM(B2:B2)")

    built = await sheet.build(session_id)
    assert built["title"] == "构建测试"
    assert built["sheet_names"] == ["汇总"]

    directory = sheet.SHEETS_DIR / built["directory"]
    assert (directory / "workbook.json").is_file()

    artifact = await ArtifactFactory().build_sheet_artifact(session_id, directory)
    assert artifact is not None
    assert artifact["type"] == "spreadsheet"
    assert artifact["title"] == "构建测试"
    assert artifact["sheet_names"] == ["汇总"]
    # 公式结果要已经算好落进快照，用户打开就能看到数字
    snapshot = artifact["snapshot"]
    cells = snapshot["sheets"][snapshot["sheetOrder"][0]]["cellData"]
    assert cells["2"]["1"]["v"] == 7


@pytest.mark.anyio
async def test_operations_require_a_workbook(session_id):
    with pytest.raises(sheet.SheetServiceError) as excinfo:
        await sheet.read_range(session_id, None, "A1")
    assert "create_workbook" in str(excinfo.value)


@pytest.mark.anyio
async def test_add_sheet_and_describe(session_id):
    await sheet.create_workbook(session_id, 1, "多表", "汇总")
    added = await sheet.add_sheet(session_id, "明细")
    assert added["sheets"] == ["汇总", "明细"]

    await sheet.set_range(session_id, "明细", "A1:A2", [["订单号"], ["A-001"]])
    described = await sheet.describe(session_id)
    names = [s["name"] for s in described["sheets"]]
    assert names == ["汇总", "明细"]
    detail = next(s for s in described["sheets"] if s["name"] == "明细")
    assert detail["usedRange"] == "A1:A2"


@pytest.fixture
def doc_session_id():
    sid = "office-doc-test-session"
    yield sid
    doc.forget_session(sid)


@pytest.mark.anyio
async def test_creates_document_with_heading_levels(doc_session_id):
    created = await doc.create_document(
        doc_session_id, 1, "会议纪要",
        [
            {"type": "h1", "text": "季度复盘"},
            {"type": "paragraph", "text": "销售额同比增长 12%。"},
            {"type": "h2", "text": "风险"},
            {"type": "paragraph", "text": "供应链波动。"},
        ],
    )
    assert created["title"] == "会议纪要"
    assert created["blockCount"] == 4

    read = await doc.read_document(doc_session_id)
    kinds = [b["type"] for b in read["blocks"]]
    assert kinds == ["h1", "paragraph", "h2", "paragraph"]
    assert read["blocks"][0]["text"] == "季度复盘"


@pytest.mark.anyio
async def test_document_headings_carry_visual_styles(doc_session_id):
    """标题必须真的带上视觉样式，否则渲染出来跟正文一模一样。

    两个曾经踩中的坑，各锁一条断言：
    - Univer 1.0.3 不再读 paragraphStyle.headingLevel，要用 namedStyleType，
      而且枚举值不是 1/2/3/4（HEADING_1 起步是 4）。
    - 字号不来自段落样式，只来自 body.textRuns；namedStyleType 只管段间距。
    """
    await doc.create_document(
        doc_session_id, 1, "样式测试",
        [
            {"type": "h1", "text": "一级"},
            {"type": "h2", "text": "二级"},
            {"type": "h3", "text": "三级"},
            {"type": "h4", "text": "四级"},
            {"type": "paragraph", "text": "正文"},
        ],
    )
    snapshot = json.loads((await doc.build_document(doc_session_id))["snapshot"])
    body = snapshot["body"]

    styled = [
        p["paragraphStyle"].get("namedStyleType")
        for p in body["paragraphs"]
        if isinstance(p.get("paragraphStyle"), dict)
        and p["paragraphStyle"].get("namedStyleType") is not None
    ]
    assert styled == [4, 5, 6, 7]
    # 旧字段不能再出现：它没有任何消费方，留着只会让人误以为样式已生效
    assert "headingLevel" not in json.dumps(snapshot)

    # 字号必须落在 textRuns 上，且逐级递减
    sizes = [run["ts"]["fs"] for run in body["textRuns"]]
    assert sizes == [32, 24, 18, 16]
    assert sizes == sorted(sizes, reverse=True)
    # 区间要对得上「一级/二级/三级/四级」的文本长度
    assert body["textRuns"][0]["st"] == 0
    assert body["textRuns"][0]["ed"] == len("一级")
    # 正文不该被塞进 textRuns
    assert body["textRuns"][-1]["ed"] <= body["dataStream"].index("正文")


@pytest.mark.anyio
async def test_document_skips_empty_heading_text_run(doc_session_id):
    """空标题不占 textRuns 区间：normalizeTextRuns 会把 st === ed 直接丢弃。"""
    await doc.create_document(
        doc_session_id, 1, "空标题",
        [{"type": "h1", "text": "有字"}, {"type": "h2", "text": ""}],
    )
    body = json.loads((await doc.build_document(doc_session_id))["snapshot"])["body"]
    assert all(run["st"] != run["ed"] for run in body["textRuns"])


@pytest.mark.anyio
async def test_build_document_persists_snapshot(doc_session_id):
    from app.services.agent.artifacts import ArtifactFactory

    await doc.create_document(
        doc_session_id, 1, "落盘测试",
        [{"type": "h1", "text": "标题"}, {"type": "paragraph", "text": "正文内容"}],
    )
    built = await doc.build_document(doc_session_id)
    assert built["title"] == "落盘测试"
    assert built["char_count"] == 6  # 「标题」2 字 + 「正文内容」4 字

    directory = doc.DOCUMENTS_DIR / built["directory"]
    assert (directory / "document.json").is_file()

    artifact = await ArtifactFactory().build_document_artifact(doc_session_id, directory)
    assert artifact is not None
    assert artifact["type"] == "document"
    assert artifact["title"] == "落盘测试"
    assert artifact["char_count"] == 6


@pytest.mark.anyio
async def test_document_requires_content(doc_session_id):
    with pytest.raises(doc.DocumentServiceError) as excinfo:
        await doc.create_document(doc_session_id, 1, "空文档", [])
    assert "blocks" in str(excinfo.value)


@pytest.mark.anyio
async def test_document_operations_require_a_document(doc_session_id):
    with pytest.raises(doc.DocumentServiceError) as excinfo:
        await doc.read_document(doc_session_id)
    assert "create_document" in str(excinfo.value)


@pytest.mark.anyio
async def test_table_and_document_coexist(doc_session_id):
    """同一会话同时持有表格和文档 —— 办公场景「报告 + 附表」就是这种形态。"""
    await sheet.create_workbook(doc_session_id, 1, "附表", "数据")
    await sheet.set_range(doc_session_id, "数据", "A1:B1", [["项目", "值"]])
    await doc.create_document(
        doc_session_id, 1, "报告",
        [{"type": "h1", "text": "报告"}, {"type": "paragraph", "text": "见附表。"}],
    )
    described = await sheet.describe(doc_session_id)
    read = await doc.read_document(doc_session_id)
    assert [s["name"] for s in described["sheets"]] == ["数据"]
    assert read["blocks"][0]["text"] == "报告"
