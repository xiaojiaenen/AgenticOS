"""表格能力的端到端测试：Python 工具 → Node 运行时 → 快照落盘 → 产物重建。

这些用例需要一个真实的 node 可执行文件和已安装的 sheet-runtime 依赖。
依赖缺失时整体跳过，而不是失败——CI 的后端 job 不装 Node。
"""

from __future__ import annotations

import shutil

import pytest

from app.services.sheet import service as sheet
from app.services.sheet.runtime import NODE_MODULES, RUNTIME_DIR, SERVER_SCRIPT

RUNTIME_READY = (
    shutil.which("node") is not None
    and NODE_MODULES.is_dir()
    and SERVER_SCRIPT.is_file()
)

pytestmark = pytest.mark.skipif(
    not RUNTIME_READY, reason=f"表格运行时未就绪（node 或 {RUNTIME_DIR}/node_modules）"
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
