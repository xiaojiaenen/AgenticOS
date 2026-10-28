/**
 * 自绘浮层（非 shadcn Dialog）的无障碍基建：
 * - Esc 关闭
 * - 打开时聚焦面板内首个可聚焦元素，关闭时焦点归还触发元素
 * - Tab 焦点圈禁在面板内
 * - 打开期间锁定 body 滚动
 *
 * 用法：把面板 DOM 的 ref 传进来，open 为 true 期间生效。
 * onClose 通过 ref 读取最新值，不进入 effect 依赖，避免调用方传内联函数导致反复重挂。
 */
import * as React from 'react';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function useOverlayA11y(
  open: boolean,
  onClose: () => void,
  panelRef: React.RefObject<HTMLElement | null>,
) {
  const onCloseRef = React.useRef(onClose);
  onCloseRef.current = onClose;

  React.useEffect(() => {
    if (!open) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;

    // 聚焦面板内首个可聚焦元素；没有则聚焦面板本身
    const focusFirst = () => {
      const first = panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      if (first) {
        first.focus();
      } else {
        panel?.focus();
      }
    };
    focusFirst();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !panel) return;

      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (node) => node.offsetParent !== null || node === document.activeElement,
      );
      if (focusable.length === 0) return;

      const firstNode = focusable[0];
      const lastNode = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (!panel.contains(active)) {
        event.preventDefault();
        firstNode.focus();
      } else if (!event.shiftKey && active === lastNode) {
        event.preventDefault();
        firstNode.focus();
      } else if (event.shiftKey && active === firstNode) {
        event.preventDefault();
        lastNode.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);

    return () => {
      document.removeEventListener('keydown', handleKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open, panelRef]);
}
