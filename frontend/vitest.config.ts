import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    // jsdom 缺 CSSStyleSheet.replaceSync / ResizeObserver，
    // A2UI 的 lit 组件挂载时会用到 —— 不补齐会让用例挂上未捕获异常
    setupFiles: ['./src/test/setup.ts'],
    // A2UI 会注册自定义元素并注入全局样式，单线程更稳
    pool: 'threads',
    poolOptions: { threads: { singleThread: true } },
  },
});
