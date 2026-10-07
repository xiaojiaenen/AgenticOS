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
import { UniverDocsNodeCorePreset } from '@univerjs/preset-docs-node-core'
import zhCN from '@univerjs/preset-sheets-node-core/locales/zh-CN'
import docsZhCN from '@univerjs/preset-docs-node-core/locales/zh-CN'
import { UniverInstanceType } from '@univerjs/core'

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

const { univer, univerAPI } = createUniver({
  locale: LocaleType.ZH_CN,
  locales: { [LocaleType.ZH_CN]: mergeLocales(zhCN, docsZhCN) },
  presets: [UniverSheetsNodeCorePreset(), UniverDocsNodeCorePreset()],
})

/** @type {Map<string, {univer: any, univerAPI: any, workbook: any, title: string}>} */
const workbooks = new Map()
/** @type {Map<string, {model: any, title: string}>} 文档单元，独立于表格 key 空间 */
const documents = new Map()

// ── 表格：单元寻址与区域解析 ──────────────────────────────────────────
// 这一组是表格所有写操作的前置依赖（requireWorkbook → resolveSheet →
// parseRange）。办公化改造时曾整块丢失，node --check 查不出来（未定义标识符
// 只在运行时炸），表现为建表成功、一写数据就 "requireWorkbook is not defined"。

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

// ── 文档：结构化块 → Univer 的 IDocumentData ──────────────────────────
//
// 关键教训：**不要手搓 IDocumentData。**
// Univer 的文档模型需要 body.textRuns / blockRanges / customBlocks 等一整套
// 派生结构，以及每个段落的 paragraphId、每个分节的 sectionId。自己拼出来
// 只有 dataStream + paragraphs 时，模型能加载（状态栏字数正确）、工具栏也
// 正常，但正文页画布只画个背景，一个字都不显示——极难排查。
//
// 正确做法：先让 Univer 建一份空文档拿到规范化模板，再把内容覆盖上去。

/**
 * 块类型 → Univer `NamedStyleType`。
 *
 * **不是 1/2/3/4。** 这是个很容易踩的坑：0.5 时代文档标题写
 * `paragraphStyle.headingLevel = 1`，1.0.3 里这个字段已经没有任何消费方
 * （全仓只有 docs-ui 的 HTML 导出和工具栏读它），渲染层完全不看，写了等于
 * 没写。真正的字段是 `paragraphStyle.namedStyleType`，取值来自
 * `NamedStyleType` 枚举，而枚举里 1~3 是 NORMAL_TEXT/TITLE/SUBTITLE，
 * HEADING_1 起步就是 4。
 */
const NAMED_STYLE_TYPE = {
  h1: 4, // HEADING_1
  h2: 5, // HEADING_2
  h3: 6, // HEADING_3
  h4: 7, // HEADING_4
}

/**
 * 标题的字号与字重。
 *
 * `namedStyleType` 本身**只管段间距**（见 core 里的 NAMED_STYLE_SPACE_MAP，
 * 它只有 spaceAbove/spaceBelow），字号一个都不给。所以光设 namedStyleType
 * 的话，标题只是「上方空了一段」，字号粗细跟正文一模一样 —— 视觉上等于没生效。
 *
 * 字号必须走 `body.textRuns`：那是字素级样式（st/ed 区间 + ts 里的 fs/bl），
 * 渲染器只认它。段落级的 `paragraphStyle.textStyle` 实测同样无效，别用。
 */
const HEADING_TEXT_STYLE = {
  h1: { fs: 32, bl: 1 },
  h2: { fs: 24, bl: 1 },
  h3: { fs: 18, bl: 1 },
  h4: { fs: 16, bl: 1 },
}

/** 由块数组拼出 dataStream、段落元数据与字素样式（其余字段沿用模板）。 */
function composeBlocks(blocks) {
  const chunks = []
  const paragraphs = []
  const textRuns = []
  let offset = 0
  for (const block of blocks) {
    const text = String(block.text ?? '')
    const para = { startIndex: offset }
    const namedStyleType = NAMED_STYLE_TYPE[block.type]
    if (namedStyleType) para.paragraphStyle = { namedStyleType }
    paragraphs.push(para)
    const textStyle = HEADING_TEXT_STYLE[block.type]
    // 空标题不必占一个空区间：normalizeTextRuns 会把 st === ed 的直接丢掉
    if (textStyle && text.length > 0) {
      textRuns.push({ st: offset, ed: offset + text.length, ts: { ...textStyle } })
    }
    chunks.push(text, '\r')
    offset += text.length + 1
  }
  // Univer 的 dataStream 约定：`\r` 结束一个段落，末尾还必须跟一个 `\n` 收尾。
  // 只写到 `\r` 时模型照样装载、状态栏字数也对，但渲染器判定这份文档是空的
  // ——正文页只剩「请输入文字」占位提示，一个字都不画。这个 `\n` 省不得。
  return { dataStream: `${chunks.join('')}\n`, paragraphs, textRuns, endIndex: offset }
}

let docIdCounter = 0

/** 借空文档拿到一份完整、规范化过的快照作为模板。 */
function normalizedDocumentTemplate() {
  const probeId = `__template_${++docIdCounter}`
  const probe = univer.createUnit(UniverInstanceType.UNIVER_DOC, { id: probeId })
  const template = JSON.parse(JSON.stringify(probe.getSnapshot()))
  // disposeUnit 在 univerAPI 上，不在 univer 上
  univerAPI.disposeUnit(probeId)
  return template
}

function blocksToDocumentData({ id, title, blocks }) {
  const { dataStream, paragraphs, textRuns, endIndex } = composeBlocks(blocks)
  const data = normalizedDocumentTemplate()

  data.id = id
  data.title = title
  data.body.dataStream = dataStream
  data.body.paragraphs = paragraphs.map((para, index) => ({
    ...para,
    // 段落/分节都要有稳定 id，缺了渲染器会跳过该段
    paragraphId: `${id}_para_${index}`,
  }))
  // 字素级样式：标题的字号/粗细只能靠它，段落级样式渲染器不读
  data.body.textRuns = textRuns
  data.body.sectionBreaks = (data.body.sectionBreaks ?? [{}]).map((section, index) => ({
    ...section,
    sectionId: `${id}_section_${index}`,
    // endIndex 是不含收尾 `\n` 的长度，正好是那个 `\n` 在新 dataStream 里的下标，
    // 与空文档模板的取值语义一致
    startIndex: Math.max(endIndex, 0),
  }))
  return data
}

/** 读回纯文本 + 块结构，供模型核对内容。 */
/**
 * Univer 的 `namedStyleType` → 我们的块类型（h1~h4）。
 * 与 NAMED_STYLE_TYPE 反向对应；不在表里的（TITLE/SUBTITLE 等）当正文处理。
 */
const NAMED_STYLE_TO_BLOCK = { 4: 'h1', 5: 'h2', 6: 'h3', 7: 'h4' }

function documentDataToBlocks(snapshot) {
  const stream = snapshot.body?.dataStream ?? ''
  const paragraphs = snapshot.body?.paragraphs ?? []
  return paragraphs
    .map((para) => {
      const start = para.startIndex ?? 0
      const end = stream.indexOf('\r', start)
      const text = stream.slice(start, end === -1 ? undefined : end)
      // 读回时 paragraphStyle 可能被模型规范化成 null，别直接解构
      const style = para.paragraphStyle ?? {}
      const named = style.namedStyleType
      // 兼容两种来源：新版写 namedStyleType，历史快照仍是 headingLevel
      const type = NAMED_STYLE_TO_BLOCK[named] ?? (style.headingLevel ? `h${style.headingLevel}` : 'paragraph')
      return { type, text }
    })
    .filter((block) => block.text.length > 0)
}

// ── 操作实现 ─────────────────────────────────────────────────────────────

const ops = {
  ping() {
    return { pong: true, workbooks: workbooks.size, documents: documents.size }
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

  // ── 文档操作 ──────────────────────────────────────────────────────────

  create_document({ key, id, title, blocks }) {
    const existing = documents.get(key)
    if (existing) {
      univerAPI.disposeUnit(existing.model.getUnitId?.() ?? id)
    }
    const data = blocksToDocumentData({ id, title, blocks: blocks ?? [] })
    const model = univer.createUnit(UniverInstanceType.UNIVER_DOC, data)
    documents.set(key, { model, title })
    return { title, blockCount: (blocks ?? []).length, unitId: data.id }
  },

  read_document({ key }) {
    const entry = documents.get(key)
    if (!entry) throw new Error(`文档不存在：${key}，请先调用 create_document`)
    const snapshot = entry.model.getSnapshot()
    return { title: snapshot.title, blocks: documentDataToBlocks(snapshot) }
  },

  build_document({ key }) {
    const entry = documents.get(key)
    if (!entry) throw new Error(`文档不存在：${key}，请先调用 create_document`)
    const snapshot = entry.model.getSnapshot()
    return { snapshot, title: snapshot.title }
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
    const doc = documents.get(key)
    if (doc) {
      univerAPI.disposeUnit(doc.model.getUnitId?.() ?? doc.model.getId?.())
      documents.delete(key)
    }
    return { discarded: key, remaining: workbooks.size + documents.size }
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
