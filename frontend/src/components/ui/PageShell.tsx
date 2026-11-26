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

export function PageHeader({ kicker, title, description, actions, back, backTo = '/' }: PageHeaderProps) {
  const goBack = useGoBack(backTo);
  return (
    <header className="mb-6">
      <div className="aos-glass-surface relative overflow-hidden rounded-2xl px-6 py-5">
        <svg
          className="pointer-events-none absolute -right-10 -top-10 h-44 w-64 opacity-40"
          viewBox="0 0 260 180"
          fill="none"
          aria-hidden="true"
        >
          <ellipse cx="180" cy="70" rx="110" ry="42" stroke="#EA580C" strokeOpacity="0.24" strokeWidth="1" className="aos-svg-flow" />
          <ellipse cx="195" cy="95" rx="80" ry="28" stroke="#0284C7" strokeOpacity="0.2" strokeWidth="1" strokeDasharray="3 6" />
        </svg>
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              {back ? (
                <button
                  type="button"
                  onClick={goBack}
                  aria-label="返回"
                  className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--secondary)] text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)] cursor-pointer"
                >
                  <ArrowLeft size={14} />
                </button>
              ) : null}
              {kicker ? (
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
                  {kicker}
                </p>
              ) : null}
            </div>
            <h1 className="mt-1.5 text-2xl sm:text-[28px] font-bold leading-tight tracking-tight text-[var(--foreground)]">
              {title}
            </h1>
            {description ? (
              <p className="mt-1.5 max-w-2xl text-sm text-[var(--muted-foreground)]">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
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
    <div className={cn('relative h-full w-full overflow-y-auto text-[var(--foreground)]', className)}>
      <div
        className={cn(
          'relative z-10 mx-auto w-full px-4 pb-14 pt-4 md:px-7',
          width === 'narrow' ? 'max-w-3xl' : 'max-w-7xl',
        )}
      >
        {headerNode}
        {children}
      </div>
    </div>
  );
}
