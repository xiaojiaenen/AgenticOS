import { useEffect, useState } from 'react';

/**
 * 视口宽度判定。
 *
 * 抽出来是因为同一个「< 768px 算移动端」的判断散落在好几个文件里，各自
 * 写一遍 `window.innerWidth < 768`，断点一旦要改就得全仓找 —— 而且很容易
 * 漏掉某个组件，导致同一个页面里「面板按移动端排版、内容按桌面端排版」。
 *
 * 用 matchMedia 而不是 resize 事件：后者每次像素变化都触发回调，在拖拽窗口
 * 时会高频执行；matchMedia 只在跨越断点时触发一次。
 */
export function useIsMobile(breakpoint = 768): boolean {
  const query = `(max-width: ${breakpoint - 1}px)`;

  const [isMobile, setIsMobile] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setIsMobile(event.matches);
    setIsMobile(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, [query]);

  return isMobile;
}
