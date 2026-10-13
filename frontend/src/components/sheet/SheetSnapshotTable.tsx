import React from 'react';
import { cn } from '../../lib/utils';

/**
 * 浏览器不支持 Univer 时的只读降级视图。
 *
 * 目标不是「复刻编辑器」，而是**不让用户白跑一趟**：内容照常展示（可滚动、
 * 可复制），并明确告诉他浏览器需要升级到哪个版本。
 */

type Snapshot = Record<string, unknown>;

/**
 * Univer 的 IWorkbookData 里，单元格是三层索引：
 * sheets[sheetId].cellData[行号字符串][列号字符串] = { v, t, f }
 * 曾经误写成 sheet.rows，导致降级视图永远渲染出一张空表。
 */
type Sheet = { id: string; name: string; cellData: Record<string, Record<string, Cell>> };

type Cell = { v?: unknown; f?: string };

function readSheets(snapshot: Snapshot): { order: string[]; sheets: Record<string, Sheet> } {
  const order = Array.isArray(snapshot.sheetOrder) ? (snapshot.sheetOrder as string[]) : [];
  const sheets = (snapshot.sheets ?? {}) as Record<string, Sheet>;
  return { order, sheets };
}

function cellText(cell: Cell | undefined): string {
  if (!cell) return '';
  if (cell.v !== undefined && cell.v !== null) return String(cell.v);
  return '';
}

function columnLabel(index: number): string {
  let n = index + 1;
  let label = '';
  while (n > 0) {
    const rem = (n - 1) % 26;
    label = String.fromCharCode(65 + rem) + label;
    n = Math.floor((n - 1) / 26);
  }
  return label;
}

export const SheetSnapshotTable: React.FC<{
  snapshot: Snapshot;
  reason: string;
  browserHint: string;
}> = ({ snapshot, reason, browserHint }) => {
  const { order, sheets } = readSheets(snapshot);
  const [active, setActive] = React.useState(order[0] ?? '');

  React.useEffect(() => {
    if (order.length && !order.includes(active)) setActive(order[0]);
  }, [order, active]);

  const sheet = sheets[active];

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-[var(--border-subtle)] bg-amber-50 px-5 py-3 text-sm text-amber-800">
        <p className="font-semibold">当前浏览器无法显示可编辑表格</p>
        <p className="mt-1 text-amber-700">
          {reason}。请升级到 {browserHint} 后重新打开，即可直接编辑。
          以下为只读内容，数据没有丢失。
        </p>
      </div>

      {order.length > 1 && (
        <div className="flex shrink-0 gap-1.5 border-b border-[var(--border-subtle)] px-4 py-2">
          {order.map((id) => (
            <button
              key={id}
              type="button"
              onClick={() => setActive(id)}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm transition-colors',
                id === active
                  ? 'bg-[var(--surface-2)] font-medium text-[var(--foreground)]'
                  : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]',
              )}
            >
              {sheets[id]?.name ?? id}
            </button>
          ))}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-auto">
        {sheet ? (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-[var(--surface-1)]">
              <tr>
                <th className="w-10 border-b border-r border-[var(--border-subtle)] px-2 py-1.5 text-xs font-medium text-[var(--muted-foreground)]" />
                {Array.from({ length: 8 }, (_, i) => (
                  <th
                    key={i}
                    className="w-32 border-b border-r border-[var(--border-subtle)] px-2 py-1.5 text-left text-xs font-medium text-[var(--muted-foreground)]"
                  >
                    {columnLabel(i)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(sheet.cellData ?? {})
                .sort((a, b) => Number(a[0]) - Number(b[0]))
                .slice(0, 200)
                .map(([rowIndex, cells]) => (
                  <tr key={rowIndex}>
                    <td className="border-b border-r border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1.5 text-xs text-[var(--muted-foreground)]">
                      {Number(rowIndex) + 1}
                    </td>
                    {Array.from({ length: 8 }, (_, colIndex) => {
                      const cell = cells[String(colIndex)];
                      const text = cellText(cell);
                      return (
                        <td
                          key={colIndex}
                          className="border-b border-r border-[var(--border-subtle)] px-2 py-1.5 align-top"
                        >
                          {text}
                          {cell?.f && (
                            <span className="ml-1 text-[10px] text-[var(--muted-foreground)]">
                              {cell.f}
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
            </tbody>
          </table>
        ) : (
          <p className="p-6 text-sm text-[var(--muted-foreground)]">表格内容为空。</p>
        )}
      </div>
    </div>
  );
};
