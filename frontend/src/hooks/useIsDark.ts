import React from 'react';

/**
 * 跟踪应用当前的暗色状态。
 *
 * 不能在渲染时一次性算 `document.documentElement.classList.contains('dark')`：
 * 那是个快照，用户切主题时不会触发重渲染，编辑器会一直停在旧主题。
 * 这里直接观察 html 上的 class —— useTheme 的应用方式就是往 html 写 class
 * （含 system 模式跟随系统时的变化），所以这是唯一可靠的信号源。
 */
export function useIsDark(): boolean {
  const [isDark, setIsDark] = React.useState(() =>
    typeof document !== 'undefined'
      ? document.documentElement.classList.contains('dark')
      : false,
  );

  React.useEffect(() => {
    const root = document.documentElement;
    const sync = () => setIsDark(root.classList.contains('dark'));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  return isDark;
}
