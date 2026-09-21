import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
// @ts-ignore - liquid-glass CSS (package exports broken, direct import)
import '../node_modules/@xiaojiaenen/liquid-glass/dist/style.css';

// Apply stored theme on startup (before React hydration) to avoid FOUC
// 用 try-catch 包裹，防止某些浏览器隐私模式下 localStorage 抛异常导致白屏
(function applyStoredTheme() {
  try {
    const STORAGE_KEY = 'agenticos-theme';
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return;
    const root = document.documentElement;
    const isLiquidGlass = stored === 'liquid-glass';
    const resolved = isLiquidGlass ? 'dark' : (stored === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : stored);
    if (resolved === 'light' || resolved === 'dark') {
      root.classList.add(resolved);
    }
    if (isLiquidGlass) {
      root.classList.add('theme-liquid-glass');
    }
  } catch {
    // localStorage 不可用时静默降级
  }
})();

// React 挂载成功后移除降级提示
const fallbackMsg = document.getElementById('fallback-msg');
if (fallbackMsg) {
  fallbackMsg.remove();
}

// 全局错误捕获：React 渲染崩溃时显示友好提示而非白屏
window.addEventListener('error', (event) => {
  console.error('[AgenticOS] Uncaught error:', event.error);
  const rootEl = document.getElementById('root');
  if (rootEl && !rootEl.querySelector('[data-react-root]')) {
    rootEl.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:system-ui,sans-serif;color:#475569;text-align:center;padding:2rem;">
        <div>
          <h1 style="font-size:1.25rem;font-weight:600;margin-bottom:0.5rem;">AgenticOS</h1>
          <p style="font-size:0.875rem;">应用加载失败，请尝试刷新页面或使用最新版 Chrome / Edge 浏览器。</p>
          <p style="font-size:0.75rem;margin-top:0.5rem;color:#94a3b8;">错误信息：${(event.error?.message || '未知错误').substring(0, 200)}</p>
          <button onclick="location.reload()" style="margin-top:1rem;padding:0.5rem 1.5rem;border:1px solid #cbd5e1;border-radius:0.5rem;background:white;cursor:pointer;font-size:0.875rem;">刷新页面</button>
        </div>
      </div>
    `;
  }
});

const rootEl = document.getElementById('root');
if (rootEl) {
  // 标记 React 根节点已初始化
  rootEl.setAttribute('data-react-root', 'true');
  createRoot(rootEl).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
