/**
 * 灵动岛紧凑槽文案宽度回归。
 *
 * 背景：紧凑胶囊的 leading/trailing 槽各只有 72px（metrics.compact.maxSlotWidth），
 * 15pt semibold 下 4 个汉字 = 60px、5 个汉字 = 75px —— **多写一个字就会被省略成
 * "生成幻…"**。这个约束看不见（jsdom 没有排版），所以用一份保守的字宽表把它钉死：
 * 汉字按 15px 计（实测 15.0）、数字/字母按 8.6px（实测 8.5–9）、符号按 6px。
 *
 * 这是刻意从严的估算（真机某些字体更窄），宁可少写一个字也不要在生产里被裁。
 */
import { describe, expect, it } from 'vitest';

/** 槽位上限，与 lib/island/metrics.ts 的 compact.maxSlotWidth 一致。 */
const MAX_SLOT = 72;

/**
 * 保守字宽估算（15pt semibold）：
 * - 汉字/全角标点 15px（实测 60/4 字 = 15.0）
 * - 数字 9px、字母 9px（实测 "12.3k" 36.6 → 平均 7.3，取 9 更保守）
 * - 空格 4px、符号（% / 等）6px
 */
function estimateWidth(text: string): number {
  let width = 0;
  for (const ch of text) {
    if (/[\u4e00-\u9fff\u3000-\u303f]/.test(ch)) width += 15;
    else if (/[0-9A-Za-z]/.test(ch)) width += 9;
    else if (ch === ' ') width += 4;
    else width += 6;
  }
  return width;
}

/**
 * 各岛紧凑槽的文案生成器 —— 与各组件里的实现保持同形。
 * 覆盖最坏情况（最大数字），不是随便挑一个值。
 */
const cases: { island: string; text: string; note: string }[] = [
  // 运行岛：带步数（两字词）与不带步数（四字词）两种
  { island: 'agent-run 思考', text: '思考 3/10', note: 'thinking + 步数' },
  { island: 'agent-run 回复', text: '回复 3/10', note: 'streaming + 步数' },
  { island: 'agent-run 做PPT', text: 'PPT 3/10', note: 'generating_ppt（用 PPT 缩写，不用"做PPT"）' },
  { island: 'agent-run 渲染', text: '渲染 3/10', note: 'rendering_ppt + 步数' },
  { island: 'agent-run 建站', text: '建站 3/10', note: 'rendering_website + 步数' },
  { island: 'agent-run 上传', text: '上传 3/10', note: '上传中 + 步数' },
  { island: 'agent-run 读取', text: '读取 3/10', note: '读取文档 + 步数' },
  { island: 'agent-run 无步数', text: '正在思考', note: '无步数时用四字词' },
  { island: 'agent-run 无步数', text: '正在回复', note: '无步数时用四字词' },
  { island: 'agent-run 无步数', text: '生成PPT', note: '四字含字母' },
  { island: 'agent-run 无步数', text: '渲染中', note: '三字' },
  { island: 'agent-run 完成', text: '12.3k 字', note: 'token 用量（单位当词，比"用量"短）' },
  { island: 'agent-run 完成', text: '999k 字', note: 'token 用量上限' },
  // 上传岛：两位百分比 + 三位百分比
  { island: 'file-upload', text: '上传 63%', note: '两位数百分比' },
  { island: 'file-upload', text: '上传 99%', note: '封顶后最大形态' },
  // 导出岛
  { island: 'ppt-export', text: '导出 45s', note: '两位数秒' },
  { island: 'ppt-export', text: '导出 99+', note: '秒数封顶' },
  // 发布岛
  { island: 'site-deploy', text: '发布 2/4', note: '阶段序号' },
  { island: 'site-deploy', text: '发布 4/4', note: '末阶段' },
  // 输入岛
  { island: 'draft-typing', text: '输入 12 字', note: '两位数' },
  { island: 'draft-typing', text: '输入 99 字', note: '封顶后最大形态' },
  // 常驻时钟岛（含秒是最宽形态：冒号按符号 6px 估，比实测 58.7px 更保守）
  { island: 'idle-clock', text: '14:32:07', note: '时分秒' },
  { island: 'idle-clock', text: '23:59:59', note: '全数字最宽' },
];

describe('紧凑槽文案宽度', () => {
  for (const { island, text, note } of cases) {
    it(`${island} "${text}" 不超出 ${MAX_SLOT}px（${note}）`, () => {
      const width = estimateWidth(text);
      expect(width, `"${text}" 估算 ${width}px，上限 ${MAX_SLOT}px —— 超出会被省略成 "…"`).toBeLessThanOrEqual(
        MAX_SLOT,
      );
    });
  }

  it('汉字密度检查：4 字能放、5 字会被裁（守住这条边界）', () => {
    expect(estimateWidth('正在思考')).toBeLessThanOrEqual(MAX_SLOT);
    expect(estimateWidth('生成幻灯片')).toBeGreaterThan(MAX_SLOT);
  });
});
