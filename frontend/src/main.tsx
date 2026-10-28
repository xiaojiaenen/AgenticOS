import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';

// Apply stored theme on startup (before React hydration) to avoid FOUC
// 用 try-catch 包裹，防止某些浏览器隐私模式下 localStorage 抛异常导致白屏
(function applyStoredTheme() {
  try {
    const STORAGE_KEY = 'agenticos-theme';
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return;
    const root = document.documentElement;
    const resolved = stored === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : stored;
    if (resolved === 'light' || resolved === 'dark') {
      root.classList.add(resolved);
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
  if (!rootEl || rootEl.querySelector('[data-react-root]')) return;

  // 用 DOM API 而不是 innerHTML 拼字符串：错误消息里可能带 HTML 片段，
  // 拼进 innerHTML 就等于把它当标记解析（XSS），而且引号也会破坏 HTML 结构。
  const wrap = document.createElement('div');
  wrap.setAttribute('style', [
    'display:flex', 'align-items:center', 'justify-content:center', 'min-height:100vh',
    "font-family:'JetBrains Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, 'HarmonyOS Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    'color:#475569', 'text-align:center', 'padding:2rem',
  ].join(';'));

  const box = document.createElement('div');
  const title = document.createElement('h1');
  title.setAttribute('style', 'font-size:1.25rem;font-weight:600;margin-bottom:0.5rem;');
  title.textContent = 'AgenticOS';

  const desc = document.createElement('p');
  desc.setAttribute('style', 'font-size:0.875rem;');
  desc.textContent = '应用加载失败，请尝试刷新页面或使用最新版 Chrome / Edge 浏览器。';

  const detail = document.createElement('p');
  detail.setAttribute('style', 'font-size:0.75rem;margin-top:0.5rem;color:#94a3b8;');
  detail.textContent = `错误信息：${(event.error?.message || '未知错误').substring(0, 200)}`;

  const reload = document.createElement('button');
  reload.setAttribute('style', 'margin-top:1rem;padding:0.5rem 1.5rem;border:1px solid #cbd5e1;border-radius:0.5rem;background:white;cursor:pointer;font-size:0.875rem;');
  reload.textContent = '刷新页面';
  reload.addEventListener('click', () => location.reload());

  box.append(title, desc, detail, reload);
  wrap.append(box);
  rootEl.replaceChildren(wrap);
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
