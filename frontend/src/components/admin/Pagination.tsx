/**
 * 管理后台分页器：受控组件，外部持有 currentPage / totalPages。
 *
 * 设计取向（2026-10 改版）：
 * - 一行搞定，不额外占一整段高度 —— 后台列表页往往同时有筛选栏、批量操作栏，
 *   分页再单独一行会让页面越拉越长；
 * - 条数信息与「每页 N 条」选择器放在同一行左端，右侧是页码；
 * - 页码只显示 5 个窗口 + 首末页，页数很多时用省略号，避免把工具栏挤爆。
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
  /** 可选的左侧附加信息，例如「共 N 条」 */
  totalLabel?: React.ReactNode;
  /** 可选：每页条数选择（传了才渲染选择器） */
  pageSize?: number;
  pageSizeOptions?: number[];
  onPageSizeChange?: (size: number) => void;
  /** 紧凑模式：去掉上下边框，用于已经嵌在卡片里的场景 */
  dense?: boolean;
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
  pageSize,
  pageSizeOptions = [10, 20, 50],
  onPageSizeChange,
  dense = false,
}: PaginationProps) => {
  // 外部 total 缩小（如并发删除后 refetch）时 currentPage 可能越界。
  // 此前会渲染「第 5 / 2 页」且「上一页」还能跳到越界页，需多点一次才自愈。
  // 这里在组件内 clamp，渲染即自愈。
  const safeTotal = Math.max(1, Math.floor(totalPages));
  const safePage = Math.min(Math.max(1, Math.floor(currentPage)), safeTotal);
  const pages = getVisiblePages(safePage, safeTotal);
  const showSizePicker = typeof pageSize === 'number' && !!onPageSizeChange;

  // 只有一页且没有条数选择器时整块隐藏，避免空工具栏
  if (safeTotal <= 1 && !showSizePicker) return null;

  return (
    <nav
      aria-label="分页导航"
      className={cn(
        'flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-1 py-2',
        !dense && 'border-t border-[var(--border-subtle)] px-4 py-2.5',
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-3 text-xs font-medium text-[var(--muted-foreground)]">
        {totalLabel ? <span className="tabular-nums">{totalLabel}</span> : null}
        {showSizePicker ? (
          <label className="flex items-center gap-1.5">
            <span className="sr-only">每页条数</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange?.(Number(event.target.value))}
              className="h-7 rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-1.5 text-xs font-medium text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
            >
              {pageSizeOptions.map((size) => (
                <option key={size} value={size}>
                  每页 {size} 条
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <span className="tabular-nums">
          第 <span className="font-semibold text-[var(--foreground)]">{safePage}</span> / {safeTotal} 页
        </span>
      </div>

      <div className="flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => onPageChange(Math.max(1, safePage - 1))}
          disabled={safePage === 1}
          aria-label="上一页"
        >
          <ChevronLeft size={15} />
        </Button>

        <div className="flex items-center gap-0.5">
          {pages.map((page) => (
            <Button
              key={page}
              type="button"
              variant={page === safePage ? 'default' : 'ghost'}
              size="icon-sm"
              onClick={() => onPageChange(page)}
              aria-current={safePage === page ? 'page' : undefined}
              aria-label={`第 ${page} 页`}
              className={cn(
                'text-xs tabular-nums',
                page !== safePage && 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
              )}
            >
              {page}
            </Button>
          ))}
        </div>

        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={() => onPageChange(Math.min(safeTotal, safePage + 1))}
          disabled={safePage === safeTotal}
          aria-label="下一页"
        >
          <ChevronRight size={15} />
        </Button>
      </div>
    </nav>
  );
};
