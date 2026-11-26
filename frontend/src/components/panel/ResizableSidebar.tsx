/**
 * 可拖拽调整宽度的侧栏容器（桌面端）。
 *
 * **为什么需要**：侧栏固定 420px 时，PPT 产物面板的 5 个按钮（主题/风格/
 * 导出/公开/演示）被挤到文字竖排；改成换行又会让按钮跑出可视区。
 * 让用户自己拖最省事 —— 宽屏拖到 640 看完整工具栏，窄屏缩到 360 保对话区。
 *
 * 交互细节：
 * - 拖动期间用 `pointermove` 直改宽度（不走 React state 每帧 setState，
 *   否则流式输出时叠加 rAF 刷新会卡）；
 * - 松手时才写入 store（并持久化到 localStorage）；
 * - 双击分隔条恢复默认宽度；
 * - 键盘 ←/→ 每次 ±24px（可访问性）。
 *
 * 移动端（<md）：侧栏是覆盖式抽屉，不可拖拽（没有"并排"可言）。
 */
import * as React from 'react';
import { cn } from '../../lib/utils';

export interface ResizableSidebarProps {
  width: number;
  onWidthChange: (width: number) => void;
  min?: number;
  max?: number;
  defaultWidth?: number;
  className?: string;
  children: React.ReactNode;
}

const STEP = 24;

export const ResizableSidebar: React.FC<ResizableSidebarProps> = ({
  width,
  onWidthChange,
  min = 360,
  max = 900,
  defaultWidth = 520,
  className,
  children,
}) => {
  const asideRef = React.useRef<HTMLElement | null>(null);
  const [dragging, setDragging] = React.useState(false);
  // 拖动过程中的临时值：只在本地生效，松手才提交给 store
  const liveWidthRef = React.useRef(width);

  /**
   * 渲染用的实际宽度（单一数据源）。
   *
   * 之前这里同时用「DOM 直改 + state」两套，拖动松手后 React 重渲染会把
   * style 覆盖回旧值 —— 实测拖到 760 但界面仍是 660。现在只有 state 一个
   * 来源，拖动过程中的每帧都用 setState 提交（React 18 的自动批处理足够快，
   * 侧栏宽度变化只影响这一个 aside，不会重渲染整棵聊天树）。
   */
  const [effectiveWidth, setEffectiveWidth] = React.useState(width);

  React.useEffect(() => {
    setEffectiveWidth(width);
  }, [width]);

  /**
   * 窗口变窄时自动收窄：至少给对话区留 420px。
   *
   * 只在**窗口 resize** 时限制显示宽度，不改用户存的偏好值（窗口变宽后
   * 自动恢复）。用户主动拖动时不做这个限制 —— 那是他的明确意图。
   */
  React.useEffect(() => {
    const recompute = () => {
      const viewport = window.innerWidth;
      if (viewport < 768) return; // 覆盖式抽屉，不受此限
      const cap = Math.max(min, Math.min(max, viewport - 420));
      setEffectiveWidth((prev) => Math.min(prev, cap));
    };
    window.addEventListener('resize', recompute);
    return () => window.removeEventListener('resize', recompute);
  }, [min, max]);

  const applyLive = React.useCallback((next: number) => {
    // 拖动时也保护对话区：至少留 480px（比 resize 时的 420 更严，
    // 因为拖拽是用户主动行为，越界了会立刻把对话区压成竖排字）。
    const viewport = window.innerWidth;
    const dynamicMax = viewport >= 768 ? Math.min(max, viewport - 480) : max;
    const clamped = Math.min(dynamicMax, Math.max(min, Math.round(next)));
    liveWidthRef.current = clamped;
    setEffectiveWidth(clamped);
  }, [min, max]);

  const handlePointerDown = React.useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    // 从当前实际宽度起算（而不是 prop），避免拖动中途 prop 变化导致跳变
    const startWidth = asideRef.current?.getBoundingClientRect().width ?? width;
    setDragging(true);

    const onMove = (ev: PointerEvent) => {
      // 侧栏在右侧：鼠标向左移 → 变宽
      applyLive(startWidth + (startX - ev.clientX));
    };
    const onUp = () => {
      setDragging(false);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      // 松手：把最终值提交给 store（持久化到 localStorage）
      onWidthChange(liveWidthRef.current);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }, [applyLive, onWidthChange, width]);

  const handleDoubleClick = React.useCallback(() => {
    // 恢复默认宽度（同时受"给对话区留 420px"约束）
    const capped = Math.max(min, Math.min(defaultWidth, window.innerWidth - 420));
    applyLive(capped);
    onWidthChange(capped);
  }, [applyLive, defaultWidth, min, onWidthChange]);

  const handleKeyDown = React.useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    // 分隔条在侧栏左侧：← 变宽、→ 变窄
    const delta = e.key === 'ArrowLeft' ? STEP : -STEP;
    const next = Math.min(max, Math.max(min, effectiveWidth + delta));
    applyLive(next);
    onWidthChange(next);
  }, [applyLive, effectiveWidth, max, min, onWidthChange]);

  return (
    <aside
      ref={asideRef}
      style={{ width: effectiveWidth }}
      className={cn(
        // 移动端覆盖式抽屉（不可拖拽）；md+ 并排
        'absolute inset-0 z-30 flex h-full flex-col overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--surface-1)]',
        // 桌面端：与主区一致的悬浮圆角毛玻璃面板
        'md:relative md:inset-auto md:z-auto md:flex md:h-full md:shrink-0 md:rounded-2xl md:border md:border-[var(--border-subtle)] md:aos-glass-surface',
        className,
      )}
    >
      {/* 拖拽分隔条（仅桌面端可见）。放在侧栏左边缘，宽 5px，
          视觉上是一条细线，hover/拖动时高亮。 */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="拖动调整侧栏宽度（双击恢复默认）"
        aria-valuenow={width}
        aria-valuemin={min}
        aria-valuemax={max}
        tabIndex={0}
        onPointerDown={handlePointerDown}
        onDoubleClick={handleDoubleClick}
        onKeyDown={handleKeyDown}
        className={cn(
          'absolute left-0 top-0 z-40 hidden h-full w-[5px] cursor-col-resize md:block',
          'transition-colors hover:bg-[var(--ring)]/40 focus-visible:bg-[var(--ring)]/60 focus-visible:outline-none',
          dragging && 'bg-[var(--ring)]/60',
        )}
      />
      {children}
    </aside>
  );
};
