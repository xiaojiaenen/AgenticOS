import { useState, useEffect, useCallback } from 'react';

export type Theme = 'light' | 'dark' | 'system' | 'liquid-glass';

const STORAGE_KEY = 'agenticos-theme';

function getSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getStoredTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === 'light' || stored === 'dark' || stored === 'system' || stored === 'liquid-glass') return stored;
  return 'system';
}

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  const isLiquidGlass = theme === 'liquid-glass';
  const resolved = isLiquidGlass ? 'dark' : (theme === 'system' ? getSystemTheme() : theme);

  root.classList.remove('light', 'dark', 'theme-liquid-glass');
  root.classList.add(resolved);
  if (isLiquidGlass) {
    root.classList.add('theme-liquid-glass');
  }

  // Update meta theme-color for mobile browser chrome
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.setAttribute('content', resolved === 'dark' ? '#0f172a' : '#e1f1f7');
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);

  const setTheme = useCallback((newTheme: Theme) => {
    localStorage.setItem(STORAGE_KEY, newTheme);
    setThemeState(newTheme);
    applyTheme(newTheme);
  }, []);

  const toggleTheme = useCallback(() => {
    const order: Theme[] = ['light', 'dark', 'liquid-glass', 'system'];
    const idx = order.indexOf(theme);
    setTheme(order[(idx + 1) % order.length]);
  }, [theme, setTheme]);

  // Apply on mount
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Listen for system theme changes when in 'system' or 'liquid-glass' mode
  useEffect(() => {
    if (theme !== 'system' && theme !== 'liquid-glass') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => applyTheme(theme);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  return { theme, setTheme, toggleTheme };
}
