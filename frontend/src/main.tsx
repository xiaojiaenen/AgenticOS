import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';
// @ts-ignore - liquid-glass CSS (package exports broken, direct import)
import '../node_modules/@xiaojiaenen/liquid-glass/dist/style.css';

// Apply stored theme on startup (before React hydration) to avoid FOUC
(function applyStoredTheme() {
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
})();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
