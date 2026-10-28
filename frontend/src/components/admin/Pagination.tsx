/**
 * 管理后台分页器：基于 shadcn Button 组合实现。
 * 受控组件：外部持有 currentPage / totalPages。
 */
import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { cn } from '@/lib/utils';

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
  /** 可选的右侧附加信息，例如「共 N 条」 */
  totalLabel?: React.ReactNode;
}

function getVisiblePages(currentPage: number, totalPages: number): number[] {
  if (totalPages <= 5) return Array.from({ length: totalPages }, (_, index) => index + 1);
  if (currentPage <= 3) return [1, 2, 3, 4, 5];
  if (currentPage >= totalPages - 2) {
    return [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  return [currentPage - 2, currentPage - 1, currentPage, currentPage + 1, currentPage + 2];
}

export const Pagination = ({
  currentPage,
  totalPages,
  onPageChange,
  className,
  totalLabel,
}: PaginationProps) => {
  if (totalPages <= 1) return null;

  // 外部 total 缩小（如并发删除后 refetch）时 currentPage 可能越界。
  // 此前会渲染"第 5 / 2 页"且"上一页"还能跳到越界页 4，需多点一次才自愈。
  // 这里在组件内 clamp，渲染即自愈。
  const safeTotal = Math.max(1, Math.floor(totalPages));
  const safePage = Math.min(Math.max(1, Math.floor(currentPage)), safeTotal);
  const pages = getVisiblePages(safePage, safeTotal);

  return (
    <nav
      aria-label="分页导航"
      className={cn(
        'flex flex-col gap-3 border-t border-[var(--border-subtle)] px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between',
        className,
      )}
    >
      <span className="text-xs font-medium text-[var(--muted-foreground)]">
        第 <span className="font-semibold text-[var(--foreground)]">{safePage}</span> / {safeTotal} 页
        {totalLabel ? <span className="ml-2">{totalLabel}</span> : null}
      </span>

      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(Math.max(1, safePage - 1))}
          disabled={safePage === 1}
          aria-label="上一页"
          className="gap-1"
        >
          <ChevronLeft size={14} />
          上一页
        </Button>

        <div className="hidden items-center gap-1 sm:flex">
          {pages.map((page) => (
            <Button
              key={page}
              type="button"
              variant={page === safePage ? 'default' : 'ghost'}
              size="icon-sm"
              onClick={() => onPageChange(page)}
              aria-current={safePage === page ? 'page' : undefined}
              className={cn(
                'text-xs',
                page !== safePage && 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
              )}
            >
              {page}
            </Button>
          ))}
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(Math.min(safeTotal, safePage + 1))}
          disabled={safePage === safeTotal}
          aria-label="下一页"
          className="gap-1"
        >
          下一页
          <ChevronRight size={14} />
        </Button>
      </div>
    </nav>
  );
};
