/**
 * 表格编辑器（Univer）的浏览器能力探测。
 *
 * Univer 官方支持线是 Chrome 88+，而本项目其余部分还兼容 Chrome 85（Win7）。
 * 这里不做 polyfill 硬扛——Univer 依赖 Intl.Segmenter（Chrome 87），且样式表
 * 大量使用 :where()（Chrome 88），其中大半是暗色模式规则；强行降级的结果是
 * 「部分功能直接抛错 + 深色模式花掉」，比明确拒绝更糟。
 *
 * 探测不通过时前端展示「请升级浏览器」并把快照数据以只读表格形式给出，
 * 保证内容不丢失。
 */

/** 阻断性检测：缺任何一项，编辑器都无法正常工作。 */
function detectUnsupported(): string | null {
  if (typeof CSS !== 'undefined' && typeof CSS.supports === 'function') {
    // :where() 是 Univer 样式表的基础（Chrome 88）
    if (!CSS.supports('selector(:where(*))')) {
      return '当前浏览器不支持 CSS :where() 选择器';
    }
  }
  // Univer 内部按 grapheme 切分文本，缺了会直接抛 TypeError
  if (typeof Intl === 'undefined' || typeof (Intl as { Segmenter?: unknown }).Segmenter !== 'function') {
    return '当前浏览器不支持 Intl.Segmenter';
  }
  if (typeof Array.prototype.at !== 'function') {
    return '当前浏览器不支持 Array.prototype.at';
  }
  return null;
}

let cached: string | null | undefined;

/** @returns 不支持的原因；null 表示支持。测试环境强制视为支持。 */
export function getUnsupportedReason(): string | null {
  if (cached !== undefined) return cached;
  if (import.meta.env?.MODE === 'test' || typeof window === 'undefined') {
    cached = null;
    return cached;
  }
  cached = detectUnsupported();
  return cached;
}

/** 建议的最低浏览器版本，用于给用户明确的行动指引。 */
export const MIN_BROWSER_HINT = 'Chrome 88 / Edge 88 / Firefox 90 / Safari 14.1 及以上';
