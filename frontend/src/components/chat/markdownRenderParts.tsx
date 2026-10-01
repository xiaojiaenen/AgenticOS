/**
 * Markdown 渲染的可复用片段：搜索高亮、表格单元格、children 递归处理。
 *
 * 从 ChatMessage 抽出，供按序渲染（OrderedAssistantContent）与旧式渲染共用，
 * 避免两条渲染路径各写一份、行为漂移。
 */
import React from 'react';
import { cn } from '../../lib/utils';

export const extractPlainText = (children: React.ReactNode): string =>
  React.Children.toArray(children).map((child) => {
    if (typeof child === 'string' || typeof child === 'number') return String(child).replace(/<br\s*\/?>/gi, '\n');
    if (React.isValidElement(child)) return extractPlainText((child.props as any).children);
    return '';
  }).join('').trim();

export const isNumericLike = (value: string): boolean => {
  const normalized = value.replace(/\s+/g, '').replace(/,/g, '');
  return /^[+-]?(?:[$¥€])?\d+(?:\.\d+)?(?:%|x|ms|s|m|h)?$/i.test(normalized);
};

export const isNumericHeader = (value: string): boolean =>
  /(数量|金额|价格|总计|占比|比例|得分|评分|次数|耗时|时长|rate|count|amount|price|total|score|percent|percentage|cost|time)$/i.test(value.trim());

// ── 模块级组件：稳定引用，React.memo 生效 ──
export const TableHeaderCell = React.memo(({ children }: { children: React.ReactNode }) => {
  const plainText = extractPlainText(children);
  const rightAligned = isNumericHeader(plainText);
  return <th className={cn('px-4 py-3.5 text-xs font-semibold uppercase tracking-[0.14em]', 'text-slate-200/95', rightAligned ? 'text-right' : 'text-left')}>
    <div className={cn('flex min-w-0 items-center gap-2', rightAligned ? 'justify-end' : 'justify-start')}><span className="truncate">{plainText || '字段'}</span></div>
  </th>;
});


export const TableCell = React.memo(({ children, counter, searchQuery, activeMatchId, messageId }: { children: React.ReactNode; counter: { current: number }; searchQuery: string; activeMatchId?: string | null; messageId?: string }) => {
  const plainText = extractPlainText(children);
  const rightAligned = isNumericLike(plainText);
  return <td className={cn('px-4 py-3.5 align-top leading-relaxed', 'text-slate-700', rightAligned && 'font-mono tabular-nums')}>
    {renderTableCellContent(children, counter, searchQuery, activeMatchId, messageId, { placeholder: '未填写', align: rightAligned ? 'right' : 'left', truncate: false })}
  </td>;
});

export const HighlightedText = React.memo(({ text, counter, searchQuery, activeMatchId, messageId }: { text: string; counter: { current: number }; searchQuery: string; activeMatchId?: string | null; messageId?: string }) => {
  if (!searchQuery?.trim()) return <>{text}</>;
  const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = text.split(new RegExp(`(${escapedQuery})`, 'gi'));
  return <>{parts.map((part, i) => {
    if (part.toLowerCase() === searchQuery.toLowerCase()) {
      const currentIdx = counter.current++;
      const elementId = `mark-${messageId}-${currentIdx}`;
      const isActive = elementId === activeMatchId;
      return <mark key={i} id={elementId} className={cn("rounded-[2px] px-0.5 font-semibold shadow-sm transition-all duration-300", isActive ? "bg-orange-500 text-white ring-2 ring-orange-600 z-10 scale-110 inline-block" : "bg-yellow-300 text-[var(--foreground)] ring-1 ring-yellow-400")}>{part}</mark>;
    }
    return part;
  })}</>;
});

export const processChildren = (children: any, counter: { current: number }, searchQuery: string, activeMatchId?: string | null, messageId?: string): any =>
  React.Children.map(children, child => {
    if (typeof child === 'string') {
      return child.split(/(<br\s*\/?>)/gi).map((segment, index) => {
        if (/^<br\s*\/?>$/i.test(segment)) return <br key={`br-${index}`} />;
        if (!segment) return null;
        return <HighlightedText key={`text-${index}`} text={segment} counter={counter} searchQuery={searchQuery} activeMatchId={activeMatchId} messageId={messageId} />;
      });
    }
    if (React.isValidElement(child) && (child.props as any).children) {
      return React.cloneElement(child, { ...(child.props as any), children: processChildren((child.props as any).children, counter, searchQuery, activeMatchId, messageId) });
    }
    return child;
  });

export const renderTableCellContent = (children: React.ReactNode, counter: { current: number }, searchQuery: string, activeMatchId?: string | null, messageId?: string, options: { placeholder?: string; align?: 'left' | 'right'; truncate?: boolean } = {}) => {
  const plainText = extractPlainText(children);
  if (plainText.length === 0) return <span className="inline-flex rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium tracking-wide text-gray-500">{options.placeholder ?? '未填写'}</span>;
  const processed = processChildren(children, counter, searchQuery, activeMatchId, messageId);
  const shouldTruncate = options.truncate === true && plainText.length > 64;
  const alignmentClass = options.align === 'right' ? 'items-end text-right' : 'items-start text-left';
  if (!shouldTruncate) return <div className={cn('flex min-w-0 flex-col whitespace-pre-wrap break-words', alignmentClass)}>{processed}</div>;
  return <div className={cn('flex min-w-0 flex-col', alignmentClass)} title={plainText}><span className="max-w-[18rem] overflow-hidden text-ellipsis whitespace-nowrap">{processed}</span></div>;
};
