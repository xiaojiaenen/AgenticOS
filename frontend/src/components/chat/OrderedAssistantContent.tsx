/**
 * 按序渲染助手消息：正文片段、工具调用、思考内容按真实发生顺序交错展示。
 *
 * 传统 AI 客户端（ChatGPT / Claude）的观感——"先想 → 调工具 → 再说结论"——
 * 依赖的是事件到达顺序。后端 SSE 本来就按序发出，前端把三类内容折叠进
 * text/reasoningText/toolCalls 三个字段时丢掉了这个顺序，本组件用
 * `message.blocks`（由 useChatStream 按序维护）把它还原。
 *
 * 没有 blocks 的历史消息由调用方继续走旧式三桶渲染，不受本组件影响。
 */
import React from 'react';
import { motion } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BrainCircuit, ChevronDownIcon, WrenchIcon } from 'lucide-react';
import { cn } from '../../lib/utils';
import { resolveBlocks, toolCallIdOf } from '../../lib/messageBlocks';
import type { Message, ToolCall } from '../../types';
import { ErrorBoundary } from '../ui/ErrorBoundary';
import { InlineErrorFallback } from '../ui/ErrorBoundary';
import {
  CodeBlock,
  MarkdownTable,
  MarkdownTableHead,
  MarkdownTableRow,
  ToolResultPreview,
} from './ChatMessageSubComponents';
import { TableCell, TableHeaderCell, processChildren } from './markdownRenderParts';

interface OrderedAssistantContentProps {
  message: Message;
  /** 搜索高亮计数器（跨消息累计，保证高亮 id 唯一） */
  counter: { current: number };
  searchQuery: string;
  activeMatchId: string | null;
  isAdmin: boolean;
  isStreaming: boolean;
  onOpenArtifact?: (artifact: never) => void;
}

const TOOL_STATUS_META: Record<ToolCall['status'], { label: string; className: string }> = {
  pending: { label: '等待中', className: 'bg-slate-100 text-slate-600' },
  approval_required: { label: '待审批', className: 'bg-amber-100 text-amber-700' },
  approved: { label: '已批准', className: 'bg-sky-100 text-sky-700' },
  rejected: { label: '已拒绝', className: 'bg-rose-100 text-rose-600' },
  success: { label: '已完成', className: 'bg-emerald-100 text-emerald-700' },
  error: { label: '失败', className: 'bg-rose-100 text-rose-600' },
};

/**
 * 思考组：ReAct 多轮会产生多段思考，这里合并为一个可折叠容器，
 * 内部按发生顺序分段展示——既保留时序，又避免一堆碎折叠条。
 */
const ReasoningGroup: React.FC<{ segments: string[] }> = ({ segments }) => (
  <details className="group my-1.5 rounded-xl px-3 py-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)]/60 [&_summary::-webkit-details-marker]:hidden">
    <summary className="flex cursor-pointer select-none items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]">
      <BrainCircuit size={13} />
      <span>思考过程{segments.length > 1 ? ` (${segments.length})` : ''}</span>
      <ChevronDownIcon size={12} className="ml-auto transition-transform duration-300 group-open:-rotate-180" />
    </summary>
    <div className="mt-2 max-h-40 space-y-2 overflow-y-auto border-t border-[var(--border-subtle)] pt-2">
      {segments.map((text, index) => (
        <p
          key={index}
          className="whitespace-pre-wrap break-words text-xs leading-relaxed italic"
        >
          {text}
        </p>
      ))}
    </div>
  </details>
);

/** 就地渲染的工具调用块：紧凑单行 + 可展开详情；待审批时高亮 */
const ToolBlock: React.FC<{ tool: ToolCall; isAdmin: boolean }> = ({ tool, isAdmin }) => {
  const meta = TOOL_STATUS_META[tool.status] ?? TOOL_STATUS_META.pending;
  const isPendingApproval = tool.status === 'approval_required';
  return (
    <motion.details
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'group my-2 overflow-hidden rounded-2xl border px-3 py-2 transition-colors [&_summary::-webkit-details-marker]:hidden',
        isPendingApproval
          ? 'border-amber-300 bg-amber-50/80'
          : 'border-[var(--border-subtle)] bg-[var(--surface-2)]/50 hover:bg-[var(--surface-2)]',
      )}
    >
      <summary className="flex cursor-pointer select-none items-center gap-2">
        <WrenchIcon size={12} className={cn('shrink-0', isPendingApproval ? 'text-amber-600' : 'text-[var(--muted-foreground)]')} />
        <span className="font-mono text-[11px] font-semibold tracking-wide text-[var(--foreground)]">
          {tool.name}
        </span>
        <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold', meta.className)}>
          {meta.label}
        </span>
        {tool.result && !isAdmin && (
          <span className="max-w-[12rem] truncate text-[11px] text-[var(--muted-foreground)]">
            {tool.result}
          </span>
        )}
        <ChevronDownIcon size={12} className="ml-auto shrink-0 text-[var(--muted-foreground)] transition-transform duration-300 group-open:-rotate-180" />
      </summary>
      <div className="mt-2 border-t border-[var(--border-subtle)] pt-2 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
        {tool.reason || tool.instruction ? (
          <p className="mb-2">{tool.reason || tool.instruction}</p>
        ) : null}
        {tool.result ? (
          <ToolResultPreview result={tool.result} isError={tool.status === 'error'} />
        ) : (
          <p>等待工具返回内容…</p>
        )}
      </div>
    </motion.details>
  );
};

export const OrderedAssistantContent: React.FC<OrderedAssistantContentProps> = ({
  message,
  counter,
  searchQuery,
  activeMatchId,
  isAdmin,
  isStreaming,
  onOpenArtifact,
}) => {
  const blocks = resolveBlocks(message);
  const toolCalls = message.toolCalls ?? [];

  const renderText = (text: string, isLast: boolean) => (
    <div className="prose prose-slate prose-sm max-w-none break-words [overflow-wrap:anywhere] prose-p:my-0 prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:shadow-none prose-pre:border-none">
      <ErrorBoundary fallback={<InlineErrorFallback error="Markdown 渲染失败" />}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code: (props) => <CodeBlock {...props} onOpenArtifact={onOpenArtifact} />,
            pre: ({ children }) => <>{children}</>,
            p: ({ children }) => (
              <p>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</p>
            ),
            table: ({ children }) => <MarkdownTable>{children}</MarkdownTable>,
            thead: ({ children }) => <MarkdownTableHead>{children}</MarkdownTableHead>,
            tr: ({ children }) => <MarkdownTableRow>{children}</MarkdownTableRow>,
            th: ({ children }) => <TableHeaderCell>{children}</TableHeaderCell>,
            td: ({ children }) => (
              <TableCell
                counter={counter}
                searchQuery={searchQuery}
                activeMatchId={activeMatchId}
                messageId={message.id}
              >
                {children}
              </TableCell>
            ),
            li: ({ children }) => (
              <li>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</li>
            ),
            h1: ({ children }) => <h1>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</h1>,
            h2: ({ children }) => <h2>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</h2>,
            h3: ({ children }) => <h3>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</h3>,
            h4: ({ children }) => <h4>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</h4>,
            h5: ({ children }) => <h5>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</h5>,
            h6: ({ children }) => <h6>{processChildren(children, counter, searchQuery, activeMatchId, message.id)}</h6>,
          }}
        >
          {text}
        </ReactMarkdown>
      </ErrorBoundary>
      {isStreaming && isLast && (
        <motion.span
          className="inline-block w-[2px] h-[1.2em] bg-brand-500 rounded-full align-text-bottom ml-px"
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ duration: 0.8, repeat: Infinity }}
        />
      )}
    </div>
  );

  // 渲染：连续 reasoning 合并为一个思考组，其余按序渲染
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  while (cursor < blocks.length) {
    const block = blocks[cursor];

    if (block.kind === 'reasoning') {
      const segments: string[] = [];
      let next = cursor;
      while (next < blocks.length && blocks[next].kind === 'reasoning') {
        const segment = blocks[next];
        if (segment.kind === 'reasoning') segments.push(segment.text);
        next += 1;
      }
      nodes.push(<ReasoningGroup key={`rg-${cursor}`} segments={segments} />);
      cursor = next;
      continue;
    }

    if (block.kind === 'tool') {
      const toolIndex = toolCalls.findIndex(
        (call, i) => toolCallIdOf(call, i) === block.toolCallId,
      );
      const tool = toolIndex >= 0 ? toolCalls[toolIndex] : undefined;
      if (tool) nodes.push(<ToolBlock key={`tool-${block.toolCallId}`} tool={tool} isAdmin={isAdmin} />);
      cursor += 1;
      continue;
    }

    const isLast = cursor === blocks.length - 1;
    nodes.push(<div key={`text-${cursor}`}>{renderText(block.text, isLast)}</div>);
    cursor += 1;
  }

  return <>{nodes}</>;
};

/** 消息是否适合走按序渲染（有 blocks 且不止一个纯文本块） */
export function shouldUseOrderedRender(message: Message): boolean {
  if (!message.blocks || message.blocks.length === 0) return false;
  return message.blocks.some((b) => b.kind !== 'text');
}

/** 供搜索/复制等场景取全文（有序渲染下正文分散在多个 text 块） */
export function collectBlockText(message: Message): string {
  return resolveBlocks(message)
    .filter((b): b is Extract<typeof b, { kind: 'text' }> => b.kind === 'text')
    .map((b) => b.text)
    .filter(Boolean)
    .join('\n\n');
}

