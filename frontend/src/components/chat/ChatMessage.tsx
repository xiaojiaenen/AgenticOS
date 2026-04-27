import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import mermaid from 'mermaid';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Message } from '../../types';
import { cn } from '../../lib/utils';
import { getAppConfig } from '../../services/configService';
import { UserAvatarIcon, MascotCool, CopyIcon, CheckIcon, WrenchIcon, ChevronDownIcon } from '../ui/AnimatedIcons';

interface ChatMessageProps {
  message?: Message;
  isTyping?: boolean;
  isStreaming?: boolean;
  wideLayout?: boolean;
  onOpenArtifact?: (code: string, language: 'html' | 'svg' | 'pptdeck') => void;
  index?: number;
  searchQuery?: string;
  activeMatchId?: string | null;
}

const TOOL_RESULT_PREVIEW_CHAR_LIMIT = 520;
const TOOL_RESULT_PREVIEW_LINE_LIMIT = 10;

function normalizeToolResult(result: string): string {
  return result
    .replace(
      /(data:image\/[a-zA-Z0-9.+-]+;base64,)[A-Za-z0-9+/=\n\r]{40,}/g,
      '$1...',
    )
    .replace(
      /(data:application\/[a-zA-Z0-9.+-]+;base64,)[A-Za-z0-9+/=\n\r]{40,}/g,
      '$1...',
    );
}

function buildToolResultPreview(result: string): { text: string; truncated: boolean } {
  if (result.length <= TOOL_RESULT_PREVIEW_CHAR_LIMIT) {
    const lineCount = result.split('\n').length;
    if (lineCount <= TOOL_RESULT_PREVIEW_LINE_LIMIT) {
      return { text: result, truncated: false };
    }
  }

  const lines = result.split('\n');
  const previewLines = lines.slice(0, TOOL_RESULT_PREVIEW_LINE_LIMIT);
  let preview = previewLines.join('\n');

  if (preview.length > TOOL_RESULT_PREVIEW_CHAR_LIMIT) {
    preview = `${preview.slice(0, TOOL_RESULT_PREVIEW_CHAR_LIMIT).trimEnd()}...`;
  } else if (lines.length > TOOL_RESULT_PREVIEW_LINE_LIMIT || result.length > preview.length) {
    preview = `${preview.trimEnd()}\n...`;
  }

  return { text: preview, truncated: true };
}

const ToolResultPreview = ({
  result,
  isError = false,
}: {
  result: string;
  isError?: boolean;
}) => {
  const [expanded, setExpanded] = useState(false);
  const normalizedResult = normalizeToolResult(result);
  const { text: previewText, truncated } = buildToolResultPreview(normalizedResult);
  const displayedText = expanded || !truncated ? normalizedResult : previewText;

  return (
    <div className="space-y-2">
      <div className="relative">
        <div
          className={cn(
            "rounded-xl px-3 py-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words",
            isError
              ? "border border-rose-200/90 bg-rose-50/90 text-rose-700"
              : "border border-slate-200/80 bg-slate-50/90 text-slate-500",
          )}
        >
          {displayedText}
        </div>
        {!expanded && truncated && (
          <div
            className={cn(
              "pointer-events-none absolute inset-x-0 bottom-0 h-16 rounded-b-xl",
              isError
                ? "bg-gradient-to-t from-rose-50/95 via-rose-50/70 to-transparent"
                : "bg-gradient-to-t from-slate-50/95 via-slate-50/70 to-transparent",
            )}
          />
        )}
      </div>
      {truncated && (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] transition-colors",
            isError
              ? "border-rose-200 bg-white text-rose-600 hover:bg-rose-50"
              : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50",
          )}
        >
          <span>{expanded ? '收起结果' : '展开结果'}</span>
          <ChevronDownIcon
            size={12}
            className={cn("transition-transform duration-300", expanded && "rotate-180")}
          />
        </button>
      )}
    </div>
  );
};

const MermaidChart = React.memo(({ chart }: { chart: string }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [isRendering, setIsRendering] = useState(false);
  const [height, setHeight] = useState<number | 'auto'>('auto');

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: true,
      theme: 'neutral',
      fontFamily: 'Inter',
      securityLevel: 'loose',
    });

    const renderChart = async () => {
      if (containerRef.current) {
        setIsRendering(true);
        try {
          // 重绘时先锁定当前高度，避免闪动
          if (containerRef.current.offsetHeight > 50) {
            setHeight(containerRef.current.offsetHeight);
          }
          
          const { svg } = await mermaid.render(`mermaid-${Math.random().toString(36).substr(2, 9)}`, chart);
          setSvg(svg);
        } catch (e) {
          console.error('Mermaid render error:', e);
        } finally {
          setIsRendering(false);
          // 稍微延迟一下再恢复自适应高度
          setTimeout(() => setHeight('auto'), 100);
        }
      }
    };
    renderChart();
  }, [chart]);

  return (
    <div 
      ref={containerRef} 
      style={{ minHeight: height !== 'auto' ? `${height}px` : undefined }}
      className={cn(
        "bg-slate-50/30 p-6 rounded-2xl border border-slate-200/50 my-2 flex justify-center overflow-x-auto transition-opacity duration-300",
        isRendering ? "opacity-50" : "opacity-100"
      )}
      dangerouslySetInnerHTML={{ __html: svg }} 
    />
  );
});

export const ChatMessage = React.memo(({ message, isTyping, isStreaming, wideLayout = false, onOpenArtifact, index = 0, searchQuery = "", activeMatchId }: ChatMessageProps) => {
  const isUser = message?.role === 'user';
  const hasStructuredContent = !isUser && /```|(?:^|\n)\|.+\|/.test(message?.text || '');
  const [isCopied, setIsCopied] = useState(false);
  const config = getAppConfig();
  const sessionCounter = useRef({ current: 0 });
  sessionCounter.current.current = 0;

  const extractPlainText = (children: React.ReactNode): string =>
    React.Children.toArray(children)
      .map((child) => {
        if (typeof child === 'string' || typeof child === 'number') {
          return String(child).replace(/<br\s*\/?>/gi, '\n');
        }
        if (React.isValidElement(child)) {
          return extractPlainText((child.props as any).children);
        }
        return '';
      })
      .join('')
      .trim();

  const isNumericLike = (value: string): boolean => {
    const normalized = value.replace(/\s+/g, '').replace(/,/g, '');
    return /^[+-]?(?:[$¥€])?\d+(?:\.\d+)?(?:%|x|ms|s|m|h)?$/i.test(normalized);
  };

  const isNumericHeader = (value: string): boolean =>
    /(数量|金额|价格|总计|占比|比例|得分|评分|次数|耗时|时长|rate|count|amount|price|total|score|percent|percentage|cost|time)$/i.test(
      value.trim(),
    );

  const renderTableCellContent = (
    children: React.ReactNode,
    counter: { current: number },
    options: { placeholder?: string; align?: 'left' | 'right'; truncate?: boolean } = {},
  ) => {
    const plainText = extractPlainText(children);
    const isEmpty = plainText.length === 0;

    if (isEmpty) {
      return (
        <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium tracking-wide text-slate-400">
          {options.placeholder ?? '未填写'}
        </span>
      );
    }

    const processed = processChildren(children, counter);
    const shouldTruncate = options.truncate === true && plainText.length > 64;
    const alignmentClass = options.align === 'right' ? 'items-end text-right' : 'items-start text-left';

    if (!shouldTruncate) {
      return (
        <div className={cn('flex min-w-0 flex-col whitespace-pre-wrap break-words', alignmentClass)}>
          {processed}
        </div>
      );
    }

    return (
      <div className={cn('flex min-w-0 flex-col', alignmentClass)} title={plainText}>
        <span className="max-w-[18rem] overflow-hidden text-ellipsis whitespace-nowrap">{processed}</span>
      </div>
    );
  };

  const HighlightedText = ({ text, counter }: { text: string, counter: { current: number } }) => {
    if (!searchQuery?.trim()) return <>{text}</>;
    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${escapedQuery})`, 'gi'));

    return (
      <>
        {parts.map((part, i) => {
          if (part.toLowerCase() === searchQuery.toLowerCase()) {
            const currentIdx = counter.current++;
            const elementId = `mark-${message?.id}-${currentIdx}`;
            const isActive = elementId === activeMatchId;

            return (
              <mark 
                key={i} 
                id={elementId}
                className={cn(
                  "rounded-[2px] px-0.5 font-bold shadow-sm transition-all duration-300",
                  isActive 
                    ? "bg-orange-500 text-white ring-2 ring-orange-600 z-10 scale-110 inline-block" 
                    : "bg-yellow-300 text-zinc-900 ring-1 ring-yellow-400"
                )}
              >
                {part}
              </mark>
            );
          }
          return part;
        })}
      </>
    );
  };

  // 递归处理 React 子节点，确保全文高亮搜索命中
  const processChildren = (children: any, counter: { current: number }): any => {
    return React.Children.map(children, child => {
      if (typeof child === 'string') {
        const segments = child.split(/(<br\s*\/?>)/gi);
        return segments.map((segment, index) => {
          if (/^<br\s*\/?>$/i.test(segment)) {
            return <br key={`br-${index}`} />;
          }
          if (!segment) {
            return null;
          }
          return <HighlightedText key={`text-${index}`} text={segment} counter={counter} />;
        });
      }
      if (React.isValidElement(child) && (child.props as any).children) {
        return React.cloneElement(child, {
          ...(child.props as any),
          children: processChildren((child.props as any).children, counter)
        });
      }
      return child;
    });
  };

  const handleCopy = React.useCallback(() => {
    if (message?.text) {
      navigator.clipboard.writeText(message.text);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  }, [message?.text]);

  const CodeBlock = ({ inline, className, children, ...props }: any) => {
    const [isBlockCopied, setIsBlockCopied] = useState(false);
    const match = /language-(\w+)/.exec(className || '');
    const codeString = String(children).replace(/\n$/, '');

    // Mermaid 图表单独渲染
    if (!inline && match && match[1] === 'mermaid' && config.enableMermaid) {
      return <MermaidChart chart={codeString} />;
    }

    const handleBlockCopy = () => {
      navigator.clipboard.writeText(codeString);
      setIsBlockCopied(true);
      setTimeout(() => setIsBlockCopied(false), 2000);
    };

    if (!inline && match) {
      if (match[1] === 'widget') {
        try {
          const widgetData = JSON.parse(codeString);
          if (widgetData.type === 'weather') {
            return (
              <div className="bg-gradient-to-br from-blue-400 to-cyan-300 rounded-3xl p-6 text-white my-4 w-72 transform hover:scale-[1.02] transition-transform">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <div className="text-sm font-bold opacity-80 uppercase tracking-widest">{widgetData.data.city}</div>
                    <div className="text-5xl font-display font-bold mt-1 tracking-tighter">{widgetData.data.temp}</div>
                  </div>
                  <div className="text-5xl drop-shadow-lg">{widgetData.data.icon}</div>
                </div>
                <div className="mt-2 text-base font-bold bg-white/20 backdrop-blur-md px-3 py-1 rounded-full w-fit">{widgetData.data.condition}</div>
              </div>
            );
          }
        } catch (e) {
          // 解析失败时退回普通代码块
        }
      }

      const isArtifactable = ['html', 'svg', 'pptdeck'].includes(match[1]) && config.enableArtifacts;

      return (
        <div className="relative group my-5 overflow-hidden rounded-[1.75rem] border border-slate-800/80 bg-zinc-950 shadow-[0_20px_50px_rgba(15,23,42,0.22)] ring-1 ring-white/5">
          {/* 仿 macOS 风格代码块头部 */}
          <div className="flex items-center border-b border-white/8 bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(30,41,59,0.88))] px-4 py-3 backdrop-blur-sm">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
              <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
              <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
            </div>
            <div className="ml-4 text-[10px] font-bold uppercase tracking-[0.24em] text-slate-400/90 select-none">{match[1]}</div>
            <div className="ml-auto flex items-center gap-4">
              {isArtifactable && onOpenArtifact && (
                <button
                  onClick={() => onOpenArtifact(codeString, match[1] as 'html' | 'svg' | 'pptdeck')}
                  className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-cyan-300 transition-colors hover:text-cyan-200"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>
                  <span>可视化预览</span>
                </button>
              )}
              <button
                onClick={handleBlockCopy}
                className="flex items-center justify-center rounded-lg p-1.5 text-slate-400 transition-all hover:bg-white/10 hover:text-white active:scale-90"
                title={isBlockCopied ? '已复制' : '复制代码'}
              >
                <AnimatePresence mode="wait" initial={false}>
                  {isBlockCopied ? (
                    <motion.div
                      key="ok"
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.8, opacity: 0 }}
                    >
                      <CheckIcon size={14} className="text-green-400" />
                    </motion.div>
                  ) : (
                    <motion.div
                      key="copy"
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.8, opacity: 0 }}
                    >
                      <CopyIcon size={14} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </button>
            </div>
          </div>
          <div className="text-sm">
            <SyntaxHighlighter
              style={vscDarkPlus}
              language={match[1]}
              PreTag="div"
              customStyle={{ 
                margin: 0, 
                padding: '1.35rem 1.4rem',
                background: 'transparent',
                fontSize: '0.85rem',
                lineHeight: '1.7'
              }}
              {...props}
            >
              {codeString}
            </SyntaxHighlighter>
          </div>
        </div>
      );
    }
    return (
      <code className={cn("bg-slate-100 text-teal-800 px-1.5 py-0.5 rounded-md text-sm font-mono font-medium", className)} {...props}>
        {children}
      </code>
    );
  };

  const Table = ({ children }: { children: React.ReactNode }) => (
    <div className="my-5 overflow-hidden rounded-[1.75rem] border border-slate-200/90 bg-white/88 shadow-[0_18px_45px_rgba(148,163,184,0.18)] ring-1 ring-white/65">
      <div className="h-2 bg-[linear-gradient(90deg,rgba(15,23,42,0.9),rgba(30,41,59,0.85),rgba(34,211,238,0.75))]" />
      <div className="visible-scrollbar overflow-x-auto px-1 pb-2">
        <table className="w-max min-w-full border-collapse text-left text-sm text-slate-700">
          {children}
        </table>
      </div>
    </div>
  );

  const TableHead = ({ children }: { children: React.ReactNode }) => (
    <thead className="bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(30,41,59,0.92))] text-slate-100">
      {children}
    </thead>
  );

  const TableRow = ({ children }: { children: React.ReactNode }) => (
    <tr className="border-b border-slate-200/80 transition-colors even:bg-slate-50/70 hover:bg-sky-50/50 last:border-b-0">
      {children}
    </tr>
  );

  const TableHeaderCell = ({ children }: { children: React.ReactNode }) => {
    const plainText = extractPlainText(children);
    const rightAligned = isNumericHeader(plainText);

    return (
      <th
        className={cn(
          'px-4 py-3.5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-200/95',
          rightAligned ? 'text-right' : 'text-left',
        )}
      >
        <div className={cn('flex min-w-0 items-center gap-2', rightAligned ? 'justify-end' : 'justify-start')}>
          <span className="truncate">{plainText || '字段'}</span>
        </div>
      </th>
    );
  };

  const TableCell = ({ children }: { children: React.ReactNode }) => {
    const plainText = extractPlainText(children);
    const rightAligned = isNumericLike(plainText);

    return (
      <td
        className={cn(
          'px-4 py-3.5 align-top leading-relaxed text-slate-700',
          rightAligned && 'font-mono tabular-nums text-slate-800',
        )}
      >
        {renderTableCellContent(children, sessionCounter.current, {
          placeholder: '未填写',
          align: rightAligned ? 'right' : 'left',
          truncate: false,
        })}
      </td>
    );
  };

  const ToolTimelineStep = ({
    title,
    state,
    body,
  }: {
    title: string;
    state: 'done' | 'active' | 'idle';
    body: React.ReactNode;
  }) => (
    <div className="grid grid-cols-[1rem_1fr] gap-3">
      <div className="flex flex-col items-center">
        <div
          className={cn(
            "mt-1 h-3 w-3 rounded-full border-2 transition-colors",
            state === 'done' && "border-emerald-500 bg-emerald-500",
            state === 'active' && "border-sky-500 bg-white shadow-[0_0_0_4px_rgba(56,189,248,0.15)]",
            state === 'idle' && "border-slate-300 bg-white",
          )}
        />
        <div
          className={cn(
            "mt-2 h-full min-h-5 w-px",
            state === 'done' ? "bg-emerald-300/80" : "bg-slate-200",
          )}
        />
      </div>
      <div className="pb-3">
        <div
          className={cn(
            "text-[11px] font-bold uppercase tracking-[0.14em]",
            state === 'done' && "text-emerald-600",
            state === 'active' && "text-sky-600",
            state === 'idle' && "text-slate-400",
          )}
        >
          {title}
        </div>
        <div className="mt-1 text-xs leading-relaxed text-slate-600">{body}</div>
      </div>
    </div>
  );

  return (
    <motion.div
      id={message?.id ? `msg-${message.id}` : undefined}
      initial={{ opacity: 0, y: 30, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ 
        duration: 0.6, 
        delay: Math.min(index * 0.08, 0.8),
        ease: [0.16, 1, 0.3, 1] 
      }}
      layout="position"
      className={cn(
        "flex mx-auto w-full items-start group/msg",
        wideLayout ? "max-w-[92rem] gap-8 px-8" : "max-w-4xl gap-4",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      <motion.div 
        whileHover={{ scale: 1.1, rotate: [0, -5, 5, 0] }}
        className={cn(
          "w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm z-10 cursor-help transition-all",
          isUser ? "bg-zinc-900 text-white" : "bg-white border border-slate-200 text-zinc-800"
        )}
      >
        {isUser ? <UserAvatarIcon size={20} /> : <MascotCool size={20} />}
      </motion.div>
      
      <div className={cn("flex flex-col gap-1", wideLayout ? "max-w-[78%]" : "max-w-[80%]", isUser ? "items-end" : "items-start")}>
        {/* Tool Calls Rendering */}
        {!isUser && message?.toolCalls && message.toolCalls.length > 0 && config.enableSearch && (
          <div className="mb-1 w-full text-left">
            <details className="group [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 bg-white/60 hover:bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-sm w-fit cursor-pointer transition-all select-none">
                <WrenchIcon size={12} className="text-zinc-600" />
                <span>工具链调用历史 ({message.toolCalls.length})</span>
                <ChevronDownIcon size={12} className="transition-transform duration-300 group-open:-rotate-180" />
              </summary>
              <div className="mt-3 flex flex-col gap-3 transition-all">
                {message.toolCalls.map((tool, idx) => (
                  <motion.div 
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: idx * 0.1 }}
                    key={idx} 
                    className="max-w-[34rem] rounded-[1.35rem] border border-slate-200/90 bg-white/88 px-4 py-3 text-xs text-slate-600 shadow-[0_10px_24px_rgba(148,163,184,0.14)] backdrop-blur-sm"
                  >
                    {(() => {
                      const isSuccess = tool.status === 'success';
                      const isError = tool.status === 'error';
                      const needsApproval = tool.status === 'approval_required';
                      const wasApproved = tool.status === 'approved';
                      const wasRejected = tool.status === 'rejected';
                      const statusClass = isSuccess
                        ? "bg-emerald-50 text-emerald-600"
                        : isError
                          ? "bg-rose-50 text-rose-600"
                          : needsApproval
                            ? "bg-amber-50 text-amber-700"
                            : wasRejected
                              ? "bg-rose-50 text-rose-600"
                              : wasApproved
                                ? "bg-sky-50 text-sky-600"
                                : "bg-sky-50 text-sky-600";
                      const statusLabel = isSuccess
                        ? '已完成'
                        : isError
                          ? '失败'
                          : needsApproval
                            ? '待审批'
                            : wasRejected
                              ? '已拒绝'
                              : wasApproved
                                ? '已批准'
                                : '执行中';
                      const executionState = isSuccess ? 'done' : isError || wasRejected ? 'idle' : 'active';
                      const executionBody = isSuccess
                        ? '工具执行完成。'
                        : isError
                          ? '工具执行失败，请查看返回结果中的错误说明。'
                          : needsApproval
                            ? '该工具需要人工确认后才会执行。'
                            : wasApproved
                              ? '审批已通过，等待工具返回结果。'
                              : wasRejected
                                ? '审批已拒绝，工具不会执行。'
                                : '工具正在处理中，请稍候。';
                      const resultDotClass = isSuccess
                        ? "border-emerald-500 bg-emerald-500"
                        : isError
                          ? "border-rose-500 bg-rose-500"
                          : tool.result
                            ? "border-emerald-500 bg-emerald-500"
                            : "border-slate-300 bg-white";
                      const resultTitleClass = isSuccess
                        ? "text-emerald-600"
                        : isError
                          ? "text-rose-600"
                          : tool.result
                            ? "text-emerald-600"
                            : "text-slate-400";
                      return (
                        <>
                    <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
                      <div className="flex items-center gap-2">
                        <WrenchIcon size={13} className="text-zinc-700" />
                        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-900">
                          {tool.name}
                        </span>
                      </div>
                      <span className={cn("rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em]", statusClass)}>
                        {statusLabel}
                      </span>
                    </div>

                    <div className="flex flex-col">
                      <ToolTimelineStep
                        title="调用中"
                        state="done"
                        body="已向工具发起调用，请求参数已发送。"
                      />
                      <ToolTimelineStep
                        title="执行状态"
                        state={executionState}
                        body={executionBody}
                      />
                      <div className="grid grid-cols-[1rem_1fr] gap-3">
                        <div className="flex justify-center">
                          <div
                            className={cn("mt-1 h-3 w-3 rounded-full border-2", resultDotClass)}
                          />
                        </div>
                        <div>
                          <div className={cn("text-[11px] font-bold uppercase tracking-[0.14em]", resultTitleClass)}>
                            返回结果
                          </div>
                          <div className="mt-1">
                            {tool.result ? (
                              <ToolResultPreview result={tool.result} isError={isError} />
                            ) : (
                              <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/60 px-3 py-2 text-[11px] text-slate-400">
                                等待工具返回内容
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                        </>
                      );
                    })()}
                  </motion.div>
                ))}
              </div>
            </details>
          </div>
        )}

        <div 
          id={message?.id ? `bubble-${message.id}` : undefined}
          className={cn(
          "px-5 py-3 rounded-[2rem] relative group max-w-full transition-colors duration-300",
          hasStructuredContent ? "w-full" : "w-fit",
          !isUser && isStreaming && "min-h-[3.5rem] min-w-[10rem]",
          isUser 
            ? "bg-zinc-900 text-white rounded-tr-none shadow-[0_8px_30px_rgba(0,0,0,0.15)] hover:shadow-[0_12px_40px_rgba(0,0,0,0.2)]" 
            : "bg-white/80 backdrop-blur-2xl text-slate-800 rounded-tl-none border border-slate-100 hover:bg-white"
        )}>
          {/* AI 气泡尾巴 */}
          {!isUser && (
            <svg className="absolute top-0 -left-[8px] w-3 h-4 text-white/90" viewBox="0 0 8 12" fill="currentColor">
              <path d="M8 0H0L8 12V0Z" />
            </svg>
          )}
          {/* Tail for User */}
          {isUser && (
            <svg className="absolute top-0 -right-[8px] w-3 h-4 text-zinc-900" viewBox="0 0 8 12" fill="currentColor">
              <path d="M0 0H8L0 12V0Z" />
            </svg>
          )}

          {/* Message Actions */}
          {!isTyping && (
            <div className={cn(
              "absolute bottom-0 opacity-0 group-hover/msg:opacity-100 transition-all duration-500 flex items-center gap-1 bg-white/95 backdrop-blur-md border border-slate-200 rounded-2xl p-1.5 shadow-xl z-20",
              isUser ? "right-full mr-4 mb-2" : "left-full ml-4 mb-2"
            )}>
              <button 
                onClick={handleCopy}
                className="p-2 text-slate-400 hover:text-sky-600 hover:bg-sky-50 rounded-xl transition-all active:scale-95 flex items-center justify-center"
                title="复制内容"
              >
                <AnimatePresence mode="wait" initial={false}>
                  {isCopied ? (
                    <motion.div
                      key="checked"
                      initial={{ scale: 0.5, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.5, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <CheckIcon size={16} className="text-green-500" />
                    </motion.div>
                  ) : (
                    <motion.div
                      key="copy"
                      initial={{ scale: 0.5, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.5, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <CopyIcon size={16} />
                    </motion.div>
                  )}
                </AnimatePresence>
              </button>
            </div>
          )}

          {isTyping ? (
            <div className="flex items-center gap-2 h-6 px-1">
              <motion.span 
                className="w-2 h-2 bg-zinc-300 rounded-full shadow-sm"
                animate={{ y: [0, -6, 0], scale: [1, 1.2, 1] }}
                transition={{ duration: 1, repeat: Infinity, ease: "easeInOut", delay: 0 }}
              />
              <motion.span 
                className="w-2 h-2 bg-zinc-300 rounded-full shadow-sm"
                animate={{ y: [0, -6, 0], scale: [1, 1.2, 1] }}
                transition={{ duration: 1, repeat: Infinity, ease: "easeInOut", delay: 0.2 }}
              />
              <motion.span 
                className="w-2 h-2 bg-zinc-300 rounded-full shadow-sm"
                animate={{ y: [0, -6, 0], scale: [1, 1.2, 1] }}
                transition={{ duration: 1, repeat: Infinity, ease: "easeInOut", delay: 0.4 }}
              />
            </div>
          ) : isUser ? (
            <div className="flex flex-col gap-3">
              {message?.attachments && message.attachments.length > 0 && (
                <div className="flex flex-wrap gap-3 mb-1">
                  {message.attachments.map((att, i) => (
                    <motion.div 
                      whileHover={{ scale: 1.05 }}
                      key={i} 
                      className="max-w-[240px] rounded-2xl overflow-hidden border border-white/20 shadow-lg ring-4 ring-white/5"
                    >
                      {att.type.startsWith('image/') ? (
                        <img src={att.url} alt={att.name} className="w-full h-auto object-cover max-h-52" />
                      ) : (
                        <div className="bg-white/10 p-3 flex items-center gap-3">
                          <WrenchIcon size={16} />
                          <span className="text-xs font-bold truncate">{att.name}</span>
                        </div>
                      )}
                    </motion.div>
                  ))}
                </div>
              )}
              <p className="whitespace-pre-wrap leading-relaxed tracking-tight font-medium">
                <HighlightedText text={message?.text || ''} counter={sessionCounter.current} />
              </p>
            </div>
          ) : (
            <div className="prose prose-slate prose-sm max-w-none prose-p:my-0 prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:shadow-none prose-pre:border-none">
              <ReactMarkdown 
                remarkPlugins={[remarkGfm, ...(config.enableLaTeX ? [remarkMath] : [])]}
                rehypePlugins={[...(config.enableLaTeX ? [rehypeKatex] : [])]}
                components={{
                  code: CodeBlock,
                  pre: ({ children }) => <>{children}</>,
                  p: ({ children }) => <p>{processChildren(children, sessionCounter.current)}</p>,
                  table: ({ children }) => <Table>{children}</Table>,
                  thead: ({ children }) => <TableHead>{children}</TableHead>,
                  tr: ({ children }) => <TableRow>{children}</TableRow>,
                  th: ({ children }) => <TableHeaderCell>{children}</TableHeaderCell>,
                  td: ({ children }) => <TableCell>{children}</TableCell>,
                  li: ({ children }) => <li>{processChildren(children, sessionCounter.current)}</li>,
                  h1: ({ children }) => <h1>{processChildren(children, sessionCounter.current)}</h1>,
                  h2: ({ children }) => <h2>{processChildren(children, sessionCounter.current)}</h2>,
                  h3: ({ children }) => <h3>{processChildren(children, sessionCounter.current)}</h3>,
                  h4: ({ children }) => <h4>{processChildren(children, sessionCounter.current)}</h4>,
                  h5: ({ children }) => <h5>{processChildren(children, sessionCounter.current)}</h5>,
                  h6: ({ children }) => <h6>{processChildren(children, sessionCounter.current)}</h6>,
                }}
              >
                {message?.text || ''}
              </ReactMarkdown>
            </div>
          )}
        </div>
        
        {/* Timestamp */}
        {message?.id && !isTyping && (
          <div className="text-[9px] font-black uppercase tracking-[0.1em] text-slate-400/70 px-2 mt-1.5 flex items-center gap-2">
            <span>{new Date(parseInt(message.id)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
            {!isUser && message.text && (
              <motion.span 
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="opacity-0 group-hover/msg:opacity-100 transition-opacity"
              >
                · {message.text.length} 字
              </motion.span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
});
