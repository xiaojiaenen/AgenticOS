/**
 * 独立页面统一外框（非聊天类页面：作品库 / 反馈 / 智能体商店 / 编辑器…）。
 *
 * 此前每个页面各自写 `mx-auto max-w-{3xl,4xl,5xl,7xl,1400px} px-{4,5,6,8} py-*`，
 * 同一产品里出现五种内容宽度与四种内边距，切换页面时标题基线、左右边距都
 * 在跳。这里收敛成两档 widths：
 *   - `wide`（默认）：max-w-7xl —— 列表/卡片网格（商店、作品库）
 *   - `narrow`：max-w-3xl —— 阅读型内容（反馈、单列表单）
 *
 * 只统一外框，不接管各页自己的 header/hero —— 那属于页面语义。
 */
import type { ReactNode } from 'react';
import { cn } from '../../lib/utils';

export function PageShell({
  children,
  width = 'wide',
  className,
}: {
  children: ReactNode;
  width?: 'wide' | 'narrow';
  className?: string;
}) {
  return (
    <div className={cn('min-h-screen bg-[var(--surface-0)] text-[var(--foreground)]', className)}>
      <div
        className={cn(
          'mx-auto w-full px-5 pb-14 pt-6 md:px-8',
          width === 'narrow' ? 'max-w-3xl' : 'max-w-7xl',
        )}
      >
        {children}
      </div>
    </div>
  );
}
