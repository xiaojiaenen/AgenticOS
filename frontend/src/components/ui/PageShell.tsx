/**
 * 独立页面统一外框 + 标准页头。
 *
 * 此前各页各写一套：智能体商店是「kicker + 32px 大标题 + 描述 + 右上操作」，
 * 反馈页只有一行 16px 小标题，两者并排看完全不像同一个产品。这里把页头
 * 固化为三段式（眉标 / 标题 / 描述，右侧可选操作），宽度收敛成两档。
 *
 * - `wide`：max-w-7xl —— 列表/卡片网格（商店、作品库）
 * - `narrow`：max-w-3xl —— 阅读型内容（反馈、表单）
 */
import type { ReactNode } from 'react';
import { ArrowLeft } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useGoBack } from '../../hooks/useGoBack';

export interface PageHeaderProps {
  /** 眉标（小号大写英文，如 AGENT STORE）；不传则不渲染 */
  kicker?: string;
  title: string;
  description?: string;
  /** 右上角操作区 */
  actions?: ReactNode;
  /** 是否显示返回按钮 */
  back?: boolean;
  /** 无历史时的回退目标 */
  backTo?: string;
}

export function PageHeader({ kicker, title, description, actions, back, backTo = '/chat' }: PageHeaderProps) {
  const goBack = useGoBack(backTo);
  return (
    <header className="mb-7 flex flex-col gap-4">
      {back ? (
        <button
          type="button"
          onClick={goBack}
          className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
        >
          <ArrowLeft size={14} /> 返回
        </button>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {kicker ? (
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              {kicker}
            </p>
          ) : null}
          <h1 className="text-[32px] font-bold leading-tight tracking-tight text-[var(--foreground)]">{title}</h1>
          {description ? (
            <p className="mt-2 max-w-2xl text-sm font-medium text-[var(--muted-foreground)]">{description}</p>
          ) : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}

export function PageShell({
  children,
  header,
  width = 'wide',
  className,
}: {
  children: ReactNode;
  /** 传 PageHeaderProps 对象即渲染标准页头；也可自行传节点 */
  header?: PageHeaderProps | ReactNode;
  width?: 'wide' | 'narrow';
  className?: string;
}) {
  const isHeaderProps = Boolean(header && typeof header === 'object' && 'title' in (header as object));
  const headerNode = isHeaderProps ? (
    <PageHeader {...(header as PageHeaderProps)} />
  ) : (
    (header as ReactNode)
  );

  return (
    <div className={cn('min-h-screen bg-[var(--surface-0)] text-[var(--foreground)]', className)}>
      <div
        className={cn(
          'mx-auto w-full px-5 pb-14 pt-8 md:px-8',
          width === 'narrow' ? 'max-w-3xl' : 'max-w-7xl',
        )}
      >
        {headerNode}
        {children}
      </div>
    </div>
  );
}
