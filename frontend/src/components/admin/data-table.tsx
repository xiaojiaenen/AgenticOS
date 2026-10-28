/**
 * 管理后台通用数据表格：TanStack Table + shadcn Table 样式。
 * - 加载态渲染骨架行
 * - 空态渲染传入的 emptyState（默认用统一的 EmptyState）
 * - 列定义支持 enableSorting 开启排序（表头可点击、键盘可达、带 aria-sort）
 * - 分页由外部受控（配合 <Pagination /> 使用）
 *
 * 列元信息（columnDef.meta）支持：
 * - `align: 'right'` —— 单元格右对齐（数字列用）
 * - `numeric: true` —— 等宽数字（tabular-nums），避免刷新时数字左右跳动
 *
 * 注意：本组件只对「当前传入的 data」做客户端排序。配服务端分页时，
 * 排序仅作用于当前页数据，调用方应在 UI 上注明（见各管理页表头说明）。
 */
import * as React from 'react';
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  RowData,
  SortingState,
  useReactTable,
} from '@tanstack/react-table';
import { ChevronDown, ChevronUp } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/shadcn/table';
import { Skeleton } from '@/components/shadcn/skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { cn } from '@/lib/utils';

/**
 * 列元信息扩展：数字列声明右对齐 + 等宽数字。
 *
 * 声明式比在每个 cell 里手写 class 好 —— 一列有 10 处用法时，忘一处就会
 * 出现「同一列有的对齐有的不对齐」。
 */
declare module '@tanstack/react-table' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    align?: 'left' | 'right';
    numeric?: boolean;
  }
}

export interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[];
  data: TData[];
  isLoading?: boolean;
  emptyState?: React.ReactNode;
  /** 空态标题，配合 emptyState 一起给 */
  emptyTitle?: string;
  emptyDescription?: string;
  className?: string;
  skeletonRows?: number;
}

export function DataTable<TData>({
  columns,
  data,
  isLoading = false,
  emptyState,
  emptyTitle = '暂无数据',
  emptyDescription,
  className,
  skeletonRows = 8,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    state: { sorting },
    onSortingChange: setSorting,
  });

  const columnCount = columns.length;

  return (
    <div className={cn('w-full overflow-x-auto', className)}>
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id} className="bg-[var(--surface-2)] hover:bg-[var(--surface-2)]">
              {headerGroup.headers.map((header) => {
                const canSort = header.column.getCanSort();
                const sorted = header.column.getIsSorted();
                const meta = header.column.columnDef.meta;
                const align = meta?.align ?? 'left';
                return (
                  <TableHead
                    key={header.id}
                    className={cn(
                      'text-xs font-semibold tracking-wide text-[var(--muted-foreground)]',
                      align === 'right' && 'text-right',
                      canSort && 'cursor-pointer select-none hover:text-[var(--foreground)]',
                    )}
                    onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                    // 键盘可达：Tab 聚焦表头后 Enter/Space 触发排序
                    tabIndex={canSort ? 0 : undefined}
                    role={canSort ? 'button' : undefined}
                    aria-sort={
                      sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : canSort ? 'none' : undefined
                    }
                    onKeyDown={
                      canSort
                        ? (e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              header.column.getToggleSortingHandler()?.(e);
                            }
                          }
                        : undefined
                    }
                  >
                    <span
                      className={cn(
                        'inline-flex items-center gap-1',
                        align === 'right' && 'flex-row-reverse',
                      )}
                    >
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {/* 排序指示用图标而不是 ↑↓ 字符：字符在表头里跟正文挤在一起，
                          而且读屏会把它念成「上箭头」而不是「升序」。 */}
                      {sorted === 'asc' ? (
                        <ChevronUp size={13} className="text-[var(--foreground)]" aria-hidden />
                      ) : sorted === 'desc' ? (
                        <ChevronDown size={13} className="text-[var(--foreground)]" aria-hidden />
                      ) : null}
                      {sorted ? (
                        <span className="sr-only">
                          {sorted === 'asc' ? '（升序）' : '（降序）'}
                        </span>
                      ) : null}
                    </span>
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: skeletonRows }).map((_, rowIndex) => (
              <TableRow key={`skeleton-${rowIndex}`}>
                {table.getAllLeafColumns().map((column, colIndex) => (
                  <TableCell key={`${column.id}-${colIndex}`}>
                    <Skeleton className="h-4 w-full max-w-[180px]" />
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : table.getRowModel().rows.length > 0 ? (
            table.getRowModel().rows.map((row, rowIndex) => (
              <TableRow
                key={row.id}
                // 斑马纹：长表格纵向扫读时，没有行底色几乎无法对齐到同一行。
                // 之前骨架屏做了深浅区分、真实数据反而没有，看着像「加载完样式丢了」。
                className={cn(
                  'transition-colors',
                  rowIndex % 2 === 1 && 'bg-[var(--surface-2)]/60',
                  'hover:bg-[var(--surface-2)]',
                )}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta;
                  return (
                    <TableCell
                      key={cell.id}
                      className={cn(
                        meta?.align === 'right' && 'text-right',
                        // 等宽数字：数值变化时字宽不变，不会左右跳动
                        meta?.numeric && 'tabular-nums',
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))
          ) : (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={columnCount} className="p-0">
                {emptyState ?? (
                  <EmptyState size="compact" title={emptyTitle} description={emptyDescription} />
                )}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
