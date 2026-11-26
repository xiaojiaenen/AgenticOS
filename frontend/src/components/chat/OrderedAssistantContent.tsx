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
import { toolLabel, useToolLabels } from '../../hooks/useToolLabels';
import {
  CodeBlock,
  MarkdownTable,
  MarkdownTableHead,
  MarkdownTableRow,
  ToolResultPreview,
} from './ChatMessageSubComponents';
import { OutputImage, TableCell, TableHeaderCell, processChildren, renderOutputImages } from './markdownRenderParts';

interface OrderedAssistantContentProps {
  message: Message;
  /** 搜索高亮计数器（跨消息累计，保证高亮 id 唯一） */
  counter: { current: number };
  searchQuery: string;
  activeMatchId: string | null;
  isAdmin: boolean;
  isStreaming: boolean;
  sessionId?: string;
  onOpenArtifact?: (artifact: never) => void;
}

const TOOL_STATUS_META: Record<ToolCall['status'], { label: string; className: string }> = {
  pending: { label: '等待中', className: 'bg-[var(--surface-3)] text-[var(--muted-foreground)]' },
  approval_required: { label: '待审批', className: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300' },
  approved: { label: '已批准', className: 'bg-sky-100 text-sky-800 dark:bg-sky-500/15 dark:text-sky-300' },
  responded: { label: '已代答', className: 'bg-violet-100 text-violet-800 dark:bg-violet-500/15 dark:text-violet-300' },
  rejected: { label: '已拒绝', className: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
  success: { label: '已完成', className: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-300' },
  error: { label: '失败', className: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300' },
};

/**
 * 思考组：ReAct 多轮会产生多段思考，这里合并为一个可折叠容器，
 * 内部按发生顺序分段展示——既保留时序，又避免一堆碎折叠条。
 */
const ReasoningGroup: React.FC<{ segments: string[]; isStreaming?: boolean }> = ({ segments, isStreaming }) => {
  const ref = React.useRef<HTMLDetailsElement>(null);
  // 流式期间强制展开且剥夺折叠权：思考段落还在增长，折叠会让视口反复跳动；
  // 结束后收起成一行。这里用 ref 显式同步 open —— React 对 open={undefined}
  // 不会移除 DOM 上已有的 open 属性（受控属性 true→undefined 时不清理），
  // 单靠 prop 会让 details 在流式结束后一直保持展开。effect 只在 isStreaming
  // 真正变化时写入，思考段落增长等其它重渲染不碰 open，保留用户手动展开意图。
  React.useLayoutEffect(() => {
    if (ref.current) ref.current.open = Boolean(isStreaming);
  }, [isStreaming]);

  return (
    <details
      ref={ref}
      className={cn(
        'group my-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]/50 px-3 py-2 text-[var(--muted-foreground)] transition-colors [&_summary::-webkit-details-marker]:hidden',
        isStreaming ? '[&_summary]:cursor-default' : 'hover:bg-[var(--surface-2)]',
      )}
    >
      <summary className="flex cursor-pointer select-none items-center gap-2 text-xs font-medium tracking-normal">
        <span className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--border-medium)] bg-[var(--surface-1)]">
          <BrainCircuit size={11} />
        </span>
        <span>{isStreaming ? '正在思考' : `思考过程 · ${segments.length} 段`}</span>
        {isStreaming ? (
          <span className="ml-1 flex items-center gap-[3px]" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="thinking-dot h-[3px] w-[3px] rounded-full bg-[var(--muted-foreground)]"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </span>
        ) : (
          <ChevronDownIcon size={12} className="ml-auto shrink-0 transition-transform duration-200 group-open:-rotate-180" />
        )}
      </summary>
      <div className="reasoning-body grid grid-rows-[1fr] transition-[grid-template-rows] duration-200 ease-[cubic-bezier(.19,1,.22,1)]">
        <div className="overflow-hidden">
          <div className="mt-2 space-y-2 border-t border-[var(--border-subtle)] pt-2">
            {segments.map((text, index) => (
              <p key={index} className="whitespace-pre-wrap break-words font-mono text-[11px] leading-[1.7] text-[var(--muted-foreground)]">
                {text}
              </p>
            ))}
          </div>
        </div>
      </div>
    </details>
  );
};

/** 就地渲染的工具调用块：紧凑单行 + 可展开详情；待审批时高亮 */
const ToolBlock: React.FC<{ tool: ToolCall; isAdmin: boolean; sessionId?: string }> = ({ tool, isAdmin, sessionId }) => {
  const meta = TOOL_STATUS_META[tool.status] ?? TOOL_STATUS_META.pending;
  const isPendingApproval = tool.status === 'approval_required';
  const labels = useToolLabels();
  const displayName = toolLabel(tool.name, labels);
  return (
    <motion.details
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'group my-2 overflow-hidden rounded-lg border px-3 py-2 transition-colors [&_summary::-webkit-details-marker]:hidden',
        isPendingApproval
          ? 'border-amber-300 bg-amber-50/80 dark:bg-amber-500/10'
          : 'border-[var(--border-subtle)] bg-[var(--surface-2)]/50 hover:bg-[var(--surface-2)]',
      )}
    >
      <summary className="flex cursor-pointer select-none items-center gap-2">
        <WrenchIcon size={12} className={cn('shrink-0', isPendingApproval ? 'text-amber-600' : 'text-[var(--muted-foreground)]')} />
        <span className="text-xs font-medium text-[var(--foreground)]">
          {displayName}
        </span>
        <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium', meta.className)}>
          {meta.label}
        </span>
        {tool.result && !isAdmin && (
          <span className="max-w-[12rem] truncate text-[11px] text-[var(--muted-foreground)]">
            {tool.result}
          </span>
        )}
        <ChevronDownIcon size={12} className="ml-auto shrink-0 text-[var(--muted-foreground)] transition-transform duration-200 group-open:-rotate-180" />
      </summary>
      <div className="mt-2 border-t border-[var(--border-subtle)] pt-2 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
        {tool.reason || tool.instruction ? (
          <p className="mb-2">{tool.reason || tool.instruction}</p>
        ) : null}
        {tool.result ? (
          <ToolResultPreview result={tool.result} isError={tool.status === 'error'} sessionId={sessionId} />
        ) : (
          <p>等待工具返回内容…</p>
        )}
      </div>
    </motion.details>
  );
};

/**
 * 连续同名工具组：Agent 常连续调用几十次 read_file / grep，逐条渲染会堆成
 * "工具墙"（截图里 20+ 行 read_file 把正文挤到屏幕外）。参考 Cursor：
 * 默认折叠成一行「读取文件 ×20」，展开后仍逐条可见，不丢信息。
 * 流式期间强制展开（与思考组一致，避免视口跳动）。
 */
const ToolGroup: React.FC<{ tools: ToolCall[]; isAdmin: boolean; isStreaming: boolean; sessionId?: string }> = ({ tools, isAdmin, isStreaming, sessionId }) => {
  const labels = useToolLabels();
  const name = tools[0].name;
  const display = toolLabel(name, labels);
  const failed = tools.filter((t) => t.status === 'error').length;
  const pending = tools.filter((t) => t.status === 'pending' || t.status === 'approval_required').length;
  const ref = React.useRef<HTMLDetailsElement>(null);
  // 同 ReasoningGroup：流式期间或有待审批/执行中的工具时展开，结束后收起。
  // 受控 open prop 的 true→undefined 不会被 React 清理，改用 ref 显式同步，
  // 且只在流式状态真正变化时写入，不覆盖用户手动展开。
  React.useLayoutEffect(() => {
    if (ref.current) ref.current.open = isStreaming || pending > 0;
  }, [isStreaming, pending]);

  return (
    <details
      ref={ref}
      className="group my-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)]/40 px-3 py-1.5 text-xs text-[var(--muted-foreground)] [&_summary::-webkit-details-marker]:hidden"
    >
      <summary className="flex cursor-pointer select-none items-center gap-2 py-0.5">
        <span className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--border-medium)] bg-[var(--surface-1)]">
          <WrenchIcon size={11} />
        </span>
        <span className="font-medium text-[var(--foreground)]">{display}</span>
        <span className="tabular-nums">×{tools.length}</span>
        {failed > 0 && <span className="rounded-full bg-rose-100 px-1.5 py-0.5 text-[10px] text-rose-700 dark:bg-rose-500/15 dark:text-rose-300">{failed} 失败</span>}
        <ChevronDownIcon size={12} className="ml-auto shrink-0 transition-transform duration-200 group-open:-rotate-180" />
      </summary>
      <div className="mt-1.5 space-y-1 border-t border-[var(--border-subtle)] pt-1.5">
        {tools.map((tool, i) => <ToolBlock key={`${tool.id || i}-${i}`} tool={tool} isAdmin={isAdmin} sessionId={sessionId} />)}
      </div>
    </details>
  );
};

export const OrderedAssistantContent: React.FC<OrderedAssistantContentProps> = ({
  message,
  counter,
  searchQuery,
  activeMatchId,
  isAdmin,
  isStreaming,
  sessionId,
  onOpenArtifact,
}) => {
  const blocks = resolveBlocks(message);
  const toolCalls = message.toolCalls ?? [];

  const renderText = (text: string, isLast: boolean) => (
    <div className="prose break-words [overflow-wrap:anywhere] prose-p:my-0 prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:shadow-none prose-pre:border-none">
      <ErrorBoundary fallback={<InlineErrorFallback error="Markdown 渲染失败" />}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            code: (props) => <CodeBlock {...props} onOpenArtifact={onOpenArtifact} />,
            pre: ({ children }) => <>{children}</>,
            // 同 ChatMessage：工作区相对路径的图片要重写成带鉴权的端点
            img: ({ src, alt }) => <OutputImage src={src} alt={alt} sessionId={sessionId} />,
            p: ({ children }) => (
              <p>{renderOutputImages(processChildren(children, counter, searchQuery, activeMatchId, message.id), sessionId)}</p>
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
      {isStreaming && isLast && <span className="stream-caret" aria-hidden="true" />}
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
      nodes.push(<ReasoningGroup key={`rg-${cursor}`} segments={segments} isStreaming={isStreaming} />);
      cursor = next;
      continue;
    }

    if (block.kind === 'tool') {
      // 收集连续的同名工具块：>=3 个折叠成一行，少于 3 个保持逐条展示。
      const run: ToolCall[] = [];
      let next = cursor;
      while (next < blocks.length && blocks[next].kind === 'tool') {
        const b = blocks[next];
        if (b.kind !== 'tool') break;
        const idx = toolCalls.findIndex((call, i) => toolCallIdOf(call, i) === b.toolCallId);
        const t = idx >= 0 ? toolCalls[idx] : undefined;
        if (!t || (run.length > 0 && t.name !== run[0].name)) break;
        run.push(t);
        next += 1;
      }
      if (run.length >= 3) {
        nodes.push(<ToolGroup key={`tg-${cursor}`} tools={run} isAdmin={isAdmin} isStreaming={isStreaming} sessionId={sessionId} />);
      } else {
        for (const t of run) {
          nodes.push(<ToolBlock key={`tool-${t.id || t.name}-${cursor}`} tool={t} isAdmin={isAdmin} sessionId={sessionId} />);
        }
      }
      cursor = next;
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

