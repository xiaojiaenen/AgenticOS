import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { BrainCircuit } from 'lucide-react';
import { Artifact, Message, ToolCall } from '../../types';
import { APP_TIME_ZONE } from '../../lib/datetime';
import { cn, copyToClipboard } from '../../lib/utils';
import { getAppConfig } from '../../services/configService';
import { UserAvatarIcon, MascotCool, CopyIcon, CheckIcon, WrenchIcon, ChevronDownIcon } from '../ui/AnimatedIcons';
import {
  CodeBlock,
  MermaidChart,
  PptArtifactCard,
  WebsiteArtifactCard,
  AnimatedDots,
  AssistantWaitingIndicator,
  LiveToolCall,
  ToolResultPreview,
  ToolTimelineStep,
  MarkdownTable,
  MarkdownTableHead,
  MarkdownTableRow,
  buildToolMetaItems,
  isToolActive,
} from './ChatMessageSubComponents';

interface ChatMessageProps {
  message?: Message;
  isTyping?: boolean;
  isStreaming?: boolean;
  wideLayout?: boolean;
  isAdmin?: boolean;
  onOpenArtifact?: (artifact: Artifact) => void;
  index?: number;
  searchQuery?: string;
  activeMatchId?: string | null;
}

export const ChatMessage = React.memo(({ message, isTyping, isStreaming, wideLayout = false, isAdmin = false, onOpenArtifact, index = 0, searchQuery = "", activeMatchId }: ChatMessageProps) => {
  const isUser = message?.role === 'user';
  const rawText = message?.text || '';
  const visibleText = rawText;
  const reasoningText = message?.reasoningText || '';
  const hasPptArtifact = !isUser && Boolean(message?.pptArtifact);
  const hasWebsiteArtifact = !isUser && Boolean(message?.websiteArtifact);
  const shouldRenderBubble = isTyping || isUser || visibleText.trim().length > 0 || reasoningText.trim().length > 0 || (!hasPptArtifact && !hasWebsiteArtifact);
  const hasStructuredContent = !isUser && /```|(?:^|\n)\|.+\|/.test(visibleText);
  const showAssistantWaiting = !isUser && Boolean(isStreaming) && !visibleText.trim() && !reasoningText.trim() && !isTyping;
  const shouldAutoOpenReasoning = !isUser && Boolean(isStreaming) && reasoningText.trim().length > 0 && !visibleText.trim();
  const canCopyMessage = visibleText.trim().length > 0;
  const [isCopied, setIsCopied] = useState(false);
  const [isReasoningOpen, setIsReasoningOpen] = useState(false);
  const config = getAppConfig();
  const sessionCounter = useRef({ current: 0 });
  const wasReasoningAutoOpened = useRef(false);
  sessionCounter.current.current = 0;

  useEffect(() => {
    if (shouldAutoOpenReasoning) { setIsReasoningOpen(true); wasReasoningAutoOpened.current = true; return; }
    if (wasReasoningAutoOpened.current) { setIsReasoningOpen(false); wasReasoningAutoOpened.current = false; }
  }, [shouldAutoOpenReasoning]);

  const extractPlainText = (children: React.ReactNode): string =>
    React.Children.toArray(children).map((child) => {
      if (typeof child === 'string' || typeof child === 'number') return String(child).replace(/<br\s*\/?>/gi, '\n');
      if (React.isValidElement(child)) return extractPlainText((child.props as any).children);
      return '';
    }).join('').trim();

  const isNumericLike = (value: string): boolean => {
    const normalized = value.replace(/\s+/g, '').replace(/,/g, '');
    return /^[+-]?(?:[$¥€])?\d+(?:\.\d+)?(?:%|x|ms|s|m|h)?$/i.test(normalized);
  };

  const isNumericHeader = (value: string): boolean =>
    /(数量|金额|价格|总计|占比|比例|得分|评分|次数|耗时|时长|rate|count|amount|price|total|score|percent|percentage|cost|time)$/i.test(value.trim());

  const renderTableCellContent = (children: React.ReactNode, counter: { current: number }, options: { placeholder?: string; align?: 'left' | 'right'; truncate?: boolean } = {}) => {
    const plainText = extractPlainText(children);
    if (plainText.length === 0) return <span className="inline-flex rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium tracking-wide text-slate-400">{options.placeholder ?? '未填写'}</span>;
    const processed = processChildren(children, counter);
    const shouldTruncate = options.truncate === true && plainText.length > 64;
    const alignmentClass = options.align === 'right' ? 'items-end text-right' : 'items-start text-left';
    if (!shouldTruncate) return <div className={cn('flex min-w-0 flex-col whitespace-pre-wrap break-words', alignmentClass)}>{processed}</div>;
    return <div className={cn('flex min-w-0 flex-col', alignmentClass)} title={plainText}><span className="max-w-[18rem] overflow-hidden text-ellipsis whitespace-nowrap">{processed}</span></div>;
  };

  const HighlightedText = ({ text, counter }: { text: string; counter: { current: number } }) => {
    if (!searchQuery?.trim()) return <>{text}</>;
    const escapedQuery = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${escapedQuery})`, 'gi'));
    return <>{parts.map((part, i) => {
      if (part.toLowerCase() === searchQuery.toLowerCase()) {
        const currentIdx = counter.current++;
        const elementId = `mark-${message?.id}-${currentIdx}`;
        const isActive = elementId === activeMatchId;
        return <mark key={i} id={elementId} className={cn("rounded-[2px] px-0.5 font-bold shadow-sm transition-all duration-300", isActive ? "bg-orange-500 text-white ring-2 ring-orange-600 z-10 scale-110 inline-block" : "bg-yellow-300 text-zinc-900 ring-1 ring-yellow-400")}>{part}</mark>;
      }
      return part;
    })}</>;
  };

  const processChildren = (children: any, counter: { current: number }): any =>
    React.Children.map(children, child => {
      if (typeof child === 'string') {
        return child.split(/(<br\s*\/?>)/gi).map((segment, index) => {
          if (/^<br\s*\/?>$/i.test(segment)) return <br key={`br-${index}`} />;
          if (!segment) return null;
          return <HighlightedText key={`text-${index}`} text={segment} counter={counter} />;
        });
      }
      if (React.isValidElement(child) && (child.props as any).children) {
        return React.cloneElement(child, { ...(child.props as any), children: processChildren((child.props as any).children, counter) });
      }
      return child;
    });

  const handleCopy = useCallback(async () => {
    if (visibleText) { await copyToClipboard(visibleText); setIsCopied(true); setTimeout(() => setIsCopied(false), 2000); }
  }, [visibleText]);

  const TableHeaderCell = ({ children }: { children: React.ReactNode }) => {
    const plainText = extractPlainText(children);
    const rightAligned = isNumericHeader(plainText);
    return <th className={cn('px-4 py-3.5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-200/95', rightAligned ? 'text-right' : 'text-left')}>
      <div className={cn('flex min-w-0 items-center gap-2', rightAligned ? 'justify-end' : 'justify-start')}><span className="truncate">{plainText || '字段'}</span></div>
    </th>;
  };

  const TableCell = ({ children }: { children: React.ReactNode }) => {
    const plainText = extractPlainText(children);
    const rightAligned = isNumericLike(plainText);
    return <td className={cn('px-4 py-3.5 align-top leading-relaxed text-slate-700', rightAligned && 'font-mono tabular-nums text-slate-800')}>
      {renderTableCellContent(children, sessionCounter.current, { placeholder: '未填写', align: rightAligned ? 'right' : 'left', truncate: false })}
    </td>;
  };

  return (
    <motion.div
      id={message?.id ? `msg-${message.id}` : undefined}
      initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.6, delay: Math.min(index * 0.08, 0.8), ease: [0.16, 1, 0.3, 1] }}
      layout="position"
      className={cn("flex mx-auto w-full items-start group/msg", wideLayout ? "max-w-[92rem] gap-8 px-8" : "max-w-4xl gap-4", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <motion.div whileHover={{ scale: 1.1, rotate: [0, -5, 5, 0] }}
        className={cn("w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm z-10 cursor-help transition-all", isUser ? "bg-zinc-900 text-white" : "bg-white border border-slate-200 text-zinc-800")}>
        {isUser ? <UserAvatarIcon size={20} /> : <MascotCool size={20} />}
      </motion.div>

      <div className={cn("flex flex-col gap-1", wideLayout ? "max-w-[78%]" : "max-w-[80%]", isUser ? "items-end" : "items-start")}>
        {/* Tool Calls */}
        {!isUser && message?.toolCalls && message.toolCalls.length > 0 && config.enableSearch && (
          <div className="mb-1 w-full text-left">
            <details className="group [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-slate-500 bg-white/60 hover:bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-sm w-fit cursor-pointer transition-all select-none">
                <WrenchIcon size={12} className="text-zinc-600" />
                <span>工具链调用历史 ({message.toolCalls.length})</span>
                <ChevronDownIcon size={12} className="transition-transform duration-300 group-open:-rotate-180" />
              </summary>
              <div className="mt-3 flex flex-col gap-3 transition-all">
                {message.toolCalls.map((tool, idx) => {
                  const isSuccess = tool.status === 'success';
                  const isError = tool.status === 'error';
                  const needsApproval = tool.status === 'approval_required';
                  const wasApproved = tool.status === 'approved';
                  const wasRejected = tool.status === 'rejected';
                  const wasNotExecuted = tool.toolExecuted === false;
                  const metaItems = buildToolMetaItems(tool);
                  const detailText = tool.reason || tool.instruction;
                  const statusClass = isSuccess ? "bg-emerald-50 text-emerald-600" : isError ? "bg-rose-50 text-rose-600" : needsApproval ? "bg-amber-50 text-amber-700" : wasRejected ? "bg-rose-50 text-rose-600" : wasApproved ? "bg-sky-50 text-sky-600" : "bg-sky-50 text-sky-600";
                  const statusLabel = isSuccess ? '已完成' : isError ? '失败' : needsApproval ? '待审批' : wasRejected ? '已拒绝' : wasApproved ? '已批准' : '执行中';
                  const executionState = isSuccess ? 'done' : isError || wasRejected || wasNotExecuted ? 'idle' : 'active';
                  const executionBody = wasNotExecuted ? '运行时反馈该工具调用未实际执行。' : isSuccess ? '工具执行完成。' : isError ? '工具执行失败，请查看返回内容中的错误信息。' : needsApproval ? '该工具需要人工审批后才会执行。' : wasApproved ? '审批已通过，等待工具返回结果。' : wasRejected ? '审批已拒绝，工具不会继续执行。' : '工具正在处理中，请稍候。';
                  const resultDotClass = isSuccess ? "border-emerald-500 bg-emerald-500" : isError ? "border-rose-500 bg-rose-500" : tool.result ? "border-emerald-500 bg-emerald-500" : "border-slate-300 bg-white";
                  const resultTitleClass = isSuccess ? "text-emerald-600" : isError ? "text-rose-600" : tool.result ? "text-emerald-600" : "text-slate-400";
                  return (
                    <motion.div key={idx} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.1 }}
                      className="max-w-[34rem] rounded-3xl border border-slate-200/90 bg-white/88 px-4 py-3 text-xs text-slate-600 shadow-md backdrop-blur-sm">
                      <div className="mb-3 flex items-center justify-between gap-3 border-b border-slate-100 pb-3">
                        <div className="flex items-center gap-2"><WrenchIcon size={13} className="text-zinc-700" /><span className="font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-zinc-900">{tool.name}</span></div>
                        <span className={cn("rounded-full px-2 py-1 text-[10px] font-bold uppercase tracking-[0.14em]", statusClass)}>{statusLabel}</span>
                      </div>
                      {isAdmin ? (
                        <>
                          {metaItems.length > 0 && <div className="mb-3 flex flex-wrap gap-1.5">{metaItems.map(item => <span key={item} className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] font-bold uppercase tracking-[0.08em] text-slate-500">{item}</span>)}</div>}
                          {detailText && <div className={cn("mb-3 rounded-xl border px-3 py-2 text-[11px] leading-relaxed", isError ? "border-rose-200/90 bg-rose-50/90 text-rose-700" : "border-slate-200/80 bg-slate-50/90 text-slate-600")}>{detailText}</div>}
                          <div className="flex flex-col">
                            <ToolTimelineStep title="调用阶段" state="done" body="已向运行时发起工具调用，请求参数已发送。" />
                            <ToolTimelineStep title="执行状态" state={executionState} body={executionBody} />
                            <div className="grid grid-cols-[1rem_1fr] gap-3">
                              <div className="flex justify-center"><div className={cn("mt-1 h-3 w-3 rounded-full border-2", resultDotClass)} /></div>
                              <div>
                                <div className={cn("text-[11px] font-bold uppercase tracking-[0.14em]", resultTitleClass)}>返回结果</div>
                                <div className="mt-1">{tool.result ? <ToolResultPreview result={tool.result} isError={isError} /> : <div className="rounded-xl border border-dashed border-sky-200/60 bg-sky-50/40 px-3 py-2 text-[11px] text-slate-500">等待工具返回内容</div>}</div>
                              </div>
                            </div>
                          </div>
                        </>
                      ) : <div className="text-[11px] text-slate-500">{isSuccess ? '工具执行完成' : isError ? '工具执行失败' : executionBody}</div>}
                    </motion.div>
                  );
                })}
              </div>
            </details>
          </div>
        )}

        {!isUser && message && <><PptArtifactCard message={message} onOpenArtifact={onOpenArtifact} /><WebsiteArtifactCard message={message} onOpenArtifact={onOpenArtifact} /></>}

        {shouldRenderBubble && (
          <div id={message?.id ? `bubble-${message.id}` : undefined}
            className={cn("px-5 py-3 rounded-[2rem] relative group max-w-full min-w-0 transition-colors duration-300 overflow-hidden",
              hasStructuredContent ? "w-full" : "w-fit", !isUser && isStreaming && "min-h-[3.5rem] min-w-[10rem]",
              isUser ? "bg-[var(--bubble-user)] text-[var(--bubble-user-text)] rounded-tr-none shadow-lg hover:shadow-xl" : "bg-[var(--bubble-ai)] backdrop-blur-xl text-slate-800 rounded-tl-none border border-slate-100 hover:bg-white shadow-xs")}>

            {!isUser && !isTyping && message?.toolCalls && message.toolCalls.length > 0 && isStreaming && (
              <div className="flex flex-col gap-1.5 mb-3"><AnimatePresence>{message.toolCalls.map((tool, i) => <LiveToolCall key={`${tool.id || i}-${tool.status}`} tool={tool} />)}</AnimatePresence></div>
            )}

            {showAssistantWaiting && !isTyping && (!message?.toolCalls || message.toolCalls.length === 0) && <div className="mb-2"><AssistantWaitingIndicator /></div>}

            {isTyping ? (
              <div className="flex items-center gap-2 h-6 px-1">
                {[0, 0.2, 0.4].map(delay => <motion.span key={delay} className="w-2 h-2 bg-zinc-300 rounded-full shadow-sm" animate={{ y: [0, -6, 0], scale: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity, ease: "easeInOut", delay }} />)}
              </div>
            ) : isUser ? (
              <div className="flex flex-col gap-3">
                {message?.attachments && message.attachments.length > 0 && (
                  <div className="flex flex-wrap gap-3 mb-1">
                    {message.attachments.map((att, i) => (
                      <motion.div whileHover={{ scale: 1.05 }} key={i} className="max-w-[240px] rounded-2xl overflow-hidden border border-white/20 shadow-lg ring-4 ring-white/5">
                        {att.type.startsWith('image/') ? <img src={att.url} alt={att.name} className="w-full h-auto object-cover max-h-52" /> : <div className="bg-white/10 p-3 flex items-center gap-3"><WrenchIcon size={16} /><span className="text-xs font-bold truncate">{att.name}</span></div>}
                      </motion.div>
                    ))}
                  </div>
                )}
                <p className="whitespace-pre-wrap break-words leading-relaxed tracking-tight font-medium"><HighlightedText text={message?.text || ''} counter={sessionCounter.current} /></p>
              </div>
            ) : (
              <div className="prose prose-slate prose-sm max-w-none break-words [overflow-wrap:anywhere] prose-p:my-0 prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:shadow-none prose-pre:border-none">
                {reasoningText && (
                  <details open={isReasoningOpen} onToggle={(e) => setIsReasoningOpen(e.currentTarget.open)}
                    className="group mb-3 rounded-2xl border border-sky-200/50 bg-sky-50/50 px-3 py-2 text-slate-600 [&_summary::-webkit-details-marker]:hidden">
                    <summary className="flex cursor-pointer select-none items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-slate-600">
                      <BrainCircuit size={13} className="text-sky-500" /><span>思考过程</span>
                      {shouldAutoOpenReasoning && <span className="h-1.5 w-1.5 rounded-full bg-sky-500 animate-pulse" />}
                      <ChevronDownIcon size={12} className="ml-auto transition-transform duration-300 group-open:-rotate-180" />
                    </summary>
                    <div className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words border-t border-sky-200/40 pt-2 text-xs leading-relaxed text-slate-600">{reasoningText}</div>
                  </details>
                )}
                {visibleText ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm, ...(config.enableLaTeX ? [remarkMath] : [])]} rehypePlugins={[...(config.enableLaTeX ? [rehypeKatex] : [])]}
                    components={{
                      code: (props) => <CodeBlock {...props} onOpenArtifact={onOpenArtifact} />,
                      pre: ({ children }) => <>{children}</>,
                      p: ({ children }) => <p>{processChildren(children, sessionCounter.current)}</p>,
                      table: ({ children }) => <MarkdownTable>{children}</MarkdownTable>,
                      thead: ({ children }) => <MarkdownTableHead>{children}</MarkdownTableHead>,
                      tr: ({ children }) => <MarkdownTableRow>{children}</MarkdownTableRow>,
                      th: ({ children }) => <TableHeaderCell>{children}</TableHeaderCell>,
                      td: ({ children }) => <TableCell>{children}</TableCell>,
                      li: ({ children }) => <li>{processChildren(children, sessionCounter.current)}</li>,
                      h1: ({ children }) => <h1>{processChildren(children, sessionCounter.current)}</h1>,
                      h2: ({ children }) => <h2>{processChildren(children, sessionCounter.current)}</h2>,
                      h3: ({ children }) => <h3>{processChildren(children, sessionCounter.current)}</h3>,
                      h4: ({ children }) => <h4>{processChildren(children, sessionCounter.current)}</h4>,
                      h5: ({ children }) => <h5>{processChildren(children, sessionCounter.current)}</h5>,
                      h6: ({ children }) => <h6>{processChildren(children, sessionCounter.current)}</h6>,
                    }}>{visibleText}</ReactMarkdown>
                ) : <span className="text-sm font-medium text-slate-400"> </span>}
                {!isUser && isStreaming && visibleText && <motion.span className="inline-block w-[2px] h-[1.2em] bg-brand-500 rounded-full align-text-bottom ml-px" animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 0.8, repeat: Infinity }} />}
              </div>
            )}
          </div>
        )}

        {message?.id && !isTyping && (
          <div className="text-[9px] font-black uppercase tracking-[0.1em] text-slate-500 px-2 mt-1.5 flex items-center gap-2">
            <span>{new Date(parseInt(message.id)).toLocaleTimeString('zh-CN', { timeZone: APP_TIME_ZONE, hour: '2-digit', minute: '2-digit' })}</span>
            {!isUser && visibleText && <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="opacity-0 group-hover:opacity-100 transition-opacity">· {visibleText.length} 字</motion.span>}
            {canCopyMessage && (
              <button onClick={handleCopy} title="复制" className="text-slate-400 hover:text-sky-600 transition-colors duration-200">
                {isCopied ? <CheckIcon size={12} className="text-green-400" /> : <CopyIcon size={12} />}
              </button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
});
