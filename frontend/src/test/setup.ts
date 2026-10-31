/**
 * Vitest 全局 setup。
 *
 * jsdom 没有实现构造式样式表（`new CSSStyleSheet().replaceSync`），
 * 而 A2UI 的 lit 组件在 connectedCallback 里就会调用它 —— 不补这个桩，
 * 每次挂载 A2UI 都会抛一次未捕获异常，测试结果被污染成 "1 error"，
 * 掩盖真正的失败。
 */
import { beforeEach, afterEach, vi } from 'vitest';

// ── CSSStyleSheet 桩 ──
if (typeof globalThis.CSSStyleSheet === 'undefined') {
  class FakeCSSStyleSheet {
    cssRules: unknown[] = [];
    replaceSync(text: string) {
      this.cssRules = [{ cssText: text }];
    }
    replace(text: string) {
      this.replaceSync(text);
      return Promise.resolve(this);
    }
    insertRule(rule: string) {
      this.cssRules.push({ cssText: rule });
      return this.cssRules.length - 1;
    }
    deleteRule() {
      /* noop */
    }
  }
  (globalThis as unknown as { CSSStyleSheet: unknown }).CSSStyleSheet = FakeCSSStyleSheet;
} else if (
  typeof (globalThis.CSSStyleSheet.prototype as { replaceSync?: unknown }).replaceSync !== 'function'
) {
  (globalThis.CSSStyleSheet.prototype as { replaceSync: (t: string) => void }).replaceSync = function (
    this: { cssRules: unknown[] },
    text: string,
  ) {
    this.cssRules = [{ cssText: text }];
  };
}

// adoptedStyleSheets 同样是 jsdom 缺口（A2UI 的 light-DOM 样式注入会用到）
if (typeof document !== 'undefined' && !('adoptedStyleSheets' in document)) {
  Object.defineProperty(document, 'adoptedStyleSheets', {
    value: [],
    writable: true,
    configurable: true,
  });
}

// ResizeObserver：ECharts 挂载时会建它，jsdom 没有
if (typeof globalThis.ResizeObserver === 'undefined') {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// 每个用例后清理 DOM，避免用例间互相污染
afterEach(() => {
  if (typeof document !== 'undefined') document.body.innerHTML = '';
});

// 避免测试里忘记 mock 时真发网络请求
beforeEach(() => {
  if (typeof globalThis.fetch === 'function' && !vi.isMockFunction(globalThis.fetch)) {
    // 保留原始 fetch，只在用例内自行 mock
  }
});
