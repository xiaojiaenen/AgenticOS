/**
 * Univer 无头表格运行时。
 *
 * FastAPI（Python）通过 stdio 驱动本进程：一行一个 JSON 请求进，一行一个
 * JSON 响应出。之所以常驻而不是每次起进程，是因为 agent 的一轮对话会连续
 * 调用「建表 → 写区域 → 设公式 → 构建」，工作簿状态必须跨调用保持。
 *
 * 协议
 *   → {"id":"r1","op":"create_workbook","args":{...}}
 *   ← {"id":"r1","ok":true,"result":{...}}
 *   ← {"id":"r1","ok":false,"error":"..."}
 *
 * 关键约束：stdout 只允许输出协议行。任何第三方库的 console 输出都会破坏
 * 协议，所以进来先把 console 全部改道 stderr。
 */

import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsNodeCorePreset } from '@univerjs/preset-sheets-node-core'
import zhCN from '@univerjs/preset-sheets-node-core/locales/zh-CN'

// ── stdout 保护 ──────────────────────────────────────────────────────────
// Univer 内部偶有 console 输出。这里把所有 console 方法改道 stderr，
// 保证 stdout 只有协议行。
for (const level of ['log', 'info', 'warn', 'error', 'debug', 'trace']) {
  console[level] = (...args) => process.stderr.write(`[univer:${level}] ${args.join(' ')}\n`)
}
process.on('unhandledRejection', (err) => {
  process.stderr.write(`[univer] unhandledRejection: ${err?.stack ?? err}\n`)
})
process.on('uncaughtException', (err) => {
  // 不能退出：进程由 Python 侧管理，死了会让后续所有工具调用失败。
  process.stderr.write(`[univer] uncaughtException: ${err?.stack ?? err}\n`)
})

// ── 运行时 ───────────────────────────────────────────────────────────────

/** @type {Map<string, {univer: any, univerAPI: any, workbook: any, title: string}>} */
const workbooks = new Map()

const { univer, univerAPI } = createUniver({
  locale: LocaleType.ZH_CN,
  locales: { [LocaleType.ZH_CN]: mergeLocales(zhCN) },
  presets: [UniverSheetsNodeCorePreset()],
})

/** 公式计算是异步的：写完必须显式驱动一次，否则读回的是未计算的缓存/null。 */
async function recalculate() {
  const formula = univerAPI.getFormula()
  formula.executeCalculation()
  await formula.onCalculationResultApplied()
}

function requireWorkbook(key) {
  const entry = workbooks.get(key)
  if (!entry) throw new Error(`工作簿不存在：${key}，请先调用 create_workbook`)
  return entry
}

/** sheet 参数可以是 sheetId 或表名；省略时用活动表。 */
function resolveSheet(entry, sheet) {
  const wb = entry.workbook
  if (!sheet) return wb.getActiveSheet()
  const byId = wb.getSheetBySheetId(sheet)
  if (byId) return byId
  const byName = wb.getSheetByName(sheet)
  if (byName) return byName
  throw new Error(`找不到工作表：${sheet}（现有：${wb.getSheets().map((s) => s.getSheetName()).join('、')}）`)
}

/** 区域记法 → {row, col, rowCount, colCount}，支持 A1 / A1:C3 / 整行整列。 */
function parseRange(a1) {
  const m = /^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/i.exec(String(a1).trim())
  if (!m) throw new Error(`区域格式不合法：${a1}（示例 A1、B2:D10）`)
  const toCol = (letters) => {
    let n = 0
    for (const ch of letters.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64)
    return n - 1
  }
  const startRow = parseInt(m[2], 10) - 1
  const startCol = toCol(m[1])
  return {
    row: startRow,
    col: startCol,
    rowCount: m[4] ? parseInt(m[4], 10) - startRow : 1,
    columnCount: m[3] ? toCol(m[3]) - startCol + 1 : 1,
  }
}

// ── 操作实现 ─────────────────────────────────────────────────────────────

const ops = {
  ping() {
    return { pong: true, workbooks: workbooks.size }
  },

  create_workbook({ key, id, name, sheetName, rows = 200, columns = 26 }) {
    const existing = workbooks.get(key)
    if (existing) {
      // disposeUnit 挂在 univerAPI 上，不在 univer 上
      univerAPI.disposeUnit(existing.workbook.getId())
    }
    const firstSheetId = `${key}-sh-1`
    const created = univerAPI.createWorkbook({
      id,
      name,
      sheetOrder: [firstSheetId],
      sheets: {
        [firstSheetId]: {
          id: firstSheetId,
          name: sheetName || 'Sheet1',
          rowCount: rows,
          columnCount: columns,
          cellData: {},
        },
      },
    })
    workbooks.set(key, { univer, univerAPI, workbook: created, title: name })
    return {
      key,
      sheetId: firstSheetId,
      sheetName: created.getActiveSheet().getSheetName(),
      sheets: created.getSheets().map((s) => s.getSheetName()),
    }
  },

  add_sheet({ key, name, rows = 200, columns = 26, index }) {
    const { workbook } = requireWorkbook(key)
    const sheet = workbook.insertSheet(name, rows, index)
    if (columns) sheet.setColumnCount(columns)
    return { sheets: workbook.getSheets().map((s) => s.getSheetName()), added: name }
  },

  rename_sheet({ key, sheet, name }) {
    const { workbook } = requireWorkbook(key)
    resolveSheet({ workbook }, sheet).setName(name)
    return { sheets: workbook.getSheets().map((s) => s.getSheetName()) }
  },

  async set_range({ key, sheet, range, values }) {
    const entry = requireWorkbook(key)
    const ws = resolveSheet(entry, sheet)
    if (!Array.isArray(values) || values.length === 0) {
      throw new Error('values 必须是非空二维数组，例如 [["季度","销售额"],["Q1",120]]')
    }
    const shape = parseRange(range)
    if (values.length > shape.rowCount || Math.max(...values.map((r) => r.length)) > shape.columnCount) {
      throw new Error(
        `数据超出区域 ${range} 的容量（${shape.rowCount} 行 × ${shape.columnCount} 列），` +
        `收到 ${values.length} 行 × ${Math.max(...values.map((r) => r.length))} 列。` +
        '请扩大区域记法（如 A1:C10）或减少数据。',
      )
    }
    ws.getRange(range).setValues(values)
    await recalculate()
    return { written: `${range} (${values.length} 行)`, sheet: ws.getSheetName() }
  },

  async set_formula({ key, sheet, range, formula }) {
    const entry = requireWorkbook(key)
    const ws = resolveSheet(entry, sheet)
    ws.getRange(range).setFormula(formula)
    await recalculate()
    return { formula, computed: ws.getRange(range).getValue(), sheet: ws.getSheetName() }
  },

  async read_range({ key, sheet, range }) {
    const entry = requireWorkbook(key)
    const ws = resolveSheet(entry, sheet)
    const target = range ? ws.getRange(range) : ws.getDataRange()
    const notation = range ?? target.getA1Notation()
    await recalculate()
    return {
      sheet: ws.getSheetName(),
      range: notation,
      values: target.getValues(),
      display: range ? target.getDisplayValues?.() ?? target.getValues() : undefined,
    }
  },

  set_layout({ key, sheet, columnWidths, frozenRows, rowHeights }) {
    const entry = requireWorkbook(key)
    const ws = resolveSheet(entry, sheet)
    if (frozenRows) ws.setFrozenRows(frozenRows)
    if (columnWidths) {
      for (const [col, width] of Object.entries(columnWidths)) {
        ws.setColumnWidth(parseInt(col, 10), width)
      }
    }
    if (rowHeights) {
      for (const [row, height] of Object.entries(rowHeights)) {
        ws.setRowHeight(parseInt(row, 10), height)
      }
    }
    return { sheet: ws.getSheetName(), frozenRows: ws.getFrozenRows() }
  },

  ensure_size({ key, sheet, rows, columns }) {
    const entry = requireWorkbook(key)
    const ws = resolveSheet(entry, sheet)
    if (rows && rows > ws.getMaxRows()) ws.setRowCount(rows)
    if (columns && columns > ws.getMaxColumns()) ws.setColumnCount(columns)
    return { rows: ws.getMaxRows(), columns: ws.getMaxColumns() }
  },

  describe({ key }) {
    const { workbook } = requireWorkbook(key)
    return {
      title: workbook.getName(),
      sheets: workbook.getSheets().map((s) => ({
        sheetId: s.getSheetId(),
        name: s.getSheetName(),
        usedRange: s.getDataRange()?.getA1Notation?.() ?? null,
        rows: s.getMaxRows(),
        columns: s.getMaxColumns(),
      })),
    }
  },

  /** 产出可持久化的快照。返回的是 IWorkbookData 原始 JSON。 */
  build({ key }) {
    const { workbook } = requireWorkbook(key)
    return { snapshot: workbook.save(), title: workbook.getName() }
  },

  discard({ key }) {
    const entry = workbooks.get(key)
    if (entry) {
      univerAPI.disposeUnit(entry.workbook.getId())
      workbooks.delete(key)
    }
    return { discarded: key, remaining: workbooks.size }
  },
}

// ── 请求循环 ─────────────────────────────────────────────────────────────

let chain = Promise.resolve()

function send(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`)
}

async function handle(req) {
  const fn = ops[req.op]
  if (!fn) throw new Error(`未知操作：${req.op}（可用：${Object.keys(ops).join('、')}）`)
  return await fn(req.args ?? {})
}

// stdin 在非 TTY 下以 Buffer 逐块吐出，这里自己按行切分并解码。
let buffer = ''
process.stdin.setEncoding('utf8')
process.stdin.on('data', (chunk) => {
  buffer += chunk
  let index
  while ((index = buffer.indexOf('\n')) >= 0) {
    const line = buffer.slice(0, index).trim()
    buffer = buffer.slice(index + 1)
    if (line) enqueue(line)
  }
})
process.stdin.on('end', () => {
  const rest = buffer.trim()
  if (rest) enqueue(rest)
  chain.finally(() => process.exit(0))
})

function enqueue(raw) {
  // 串行处理：Univer 的工作簿状态不是并发安全的，且 agent 工具本就是顺序调用。
  chain = chain.then(async () => {
    let req
    try {
      req = JSON.parse(raw)
    } catch {
      send({ id: null, ok: false, error: '请求不是合法 JSON' })
      return
    }
    try {
      send({ id: req.id, ok: true, result: await handle(req) })
    } catch (err) {
      send({ id: req.id, ok: false, error: err?.message ?? String(err) })
    }
  })
}
