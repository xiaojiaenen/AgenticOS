import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { BrainCircuit } from 'lucide-react';
import { Artifact, Message } from '../../types';
import { APP_TIME_ZONE } from '../../lib/datetime';
import { cn, copyToClipboard } from '../../lib/utils';
import { getAppConfig } from '../../services/configService';
import { UserAvatarIcon, MascotCool, CopyIcon, CheckIcon, WrenchIcon, ChevronDownIcon } from '../ui/AnimatedIcons';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { submitFeedback } from '../../services/llmopsService';
import { ErrorBoundary, InlineErrorFallback } from '../ui/ErrorBoundary';
import { OrderedAssistantContent, shouldUseOrderedRender, collectBlockText } from './OrderedAssistantContent';
import { TableCell, TableHeaderCell, HighlightedText, OutputImage, processChildren, renderOutputImages } from './markdownRenderParts';
import { A2uiRenderer } from '../a2ui/A2uiRenderer';
import { ChartMessage } from '../a2ui/ChartMessage';
import {
  CodeBlock,
  PptArtifactCard,
  WebsiteArtifactCard,
  AssistantWaitingIndicator,
  LiveToolCall,
  ToolResultPreview,
  ToolTimelineStep,
  MarkdownTable,
  MarkdownTableHead,
  MarkdownTableRow,
  buildToolMetaItems,
} from './ChatMessageSubComponents';

// ── 模块级纯函数：不依赖组件闭包，避免每次渲染重建 ──

interface ChatMessageProps {
  message?: Message;
  isTyping?: boolean;
  isStreaming?: boolean;
  wideLayout?: boolean;
  isAdmin?: boolean;
  onOpenArtifact?: (artifact: Artifact) => void;
  /** A2UI 交互组件（Button 等）被点击时回调，上层转成一条用户消息。 */
  onA2uiAction?: (action: Record<string, unknown>) => void;
  /** A2UI 数据模型变化（表单输入等），用于"跟随刷新" */
  onA2uiDataChange?: (data: Record<string, unknown>, surfaceId?: string) => void;
  index?: number;
  /** ???? ID????? ??/?? ?????*/
  sessionId?: string;
  searchQuery?: string;
  activeMatchId?: string | null;
}

// 将 __ECHART_JSON__ 标记转为 ```echarts 代码块，让 CodeBlock 渲染图表
function preprocessChartMarkers(text: string): string {
  const marker = '__ECHART_JSON__';
  if (!text.includes(marker)) return text;
  return text.replace(
    new RegExp(`${marker}\\n([\\s\\S]*?)\\n${marker}`, 'g'),
    '\n```echarts\n$1\n```\n',
  );
}

/**
 * 该不该为这条消息绘制气泡。
 *
 * 抽成纯函数的原因：这里有两次互相打脸的回归，每次都是「修 A 弄坏 B」，
 * 而症状都只在特定时序下出现（流式中 / 停止后），靠手点很难覆盖。
 *
 * 历史：
 * 1. 原始条件末尾是 `|| (!hasPptArtifact && !hasWebsiteArtifact)`，
 *    「没有产物」恒真 → 任何空消息都画空气泡 → 停止后一路空泡。
 * 2. 去掉它之后，正文为空的 assistant 不再画气泡 —— 但 `LiveToolCall`
 *    与 `OrderedAssistantContent` 都挂在这个气泡**内部**。网站/PPT 这类
 *    智能体是「先调一串工具、最后才出文字」，流式早期正文为空，
 *    于是工具调用完全不可见，直到模型吐出第一段文字才「突然」冒出来。
 *
 * 现在的判据：
 * - 用户消息 / 打字指示器 → 画
 * - 有正文 / 有思考 → 画
 * - **正在流式且已有工具调用 → 画**（工具卡片在气泡内，不画就看不见）
 * - 其余（停止后的空 assistant、纯工具过渡泡的历史消息）→ 不画
 */
export function shouldRenderBubbleFor({
  isTyping,
  isUser,
  hasVisibleText,
  hasReasoning,
  isStreaming,
  hasToolCalls,
}: {
  isTyping: boolean;
  isUser: boolean;
  hasVisibleText: boolean;
  hasReasoning: boolean;
  isStreaming: boolean;
  hasToolCalls: boolean;
}): boolean {
  if (isTyping || isUser) return true;
  if (hasVisibleText || hasReasoning) return true;
  // 流式中且已有工具调用：工具卡片挂在气泡内部，跳过气泡等于让用户
  // 看不到正在执行什么。停止后 isStreaming=false，不会产生空气泡。
  return isStreaming && hasToolCalls;
}

export const ChatMessage = React.memo(({ message, isTyping, isStreaming, wideLayout = false, isAdmin = false, onOpenArtifact, onA2uiAction, onA2uiDataChange, index = 0, searchQuery = "", activeMatchId, sessionId }: ChatMessageProps) => {
  const isUser = message?.role === 'user';
  // 按序渲染（新消息）：正文/工具/思考交错展示；历史消息回退旧式三桶
  const useOrderedRender = !isUser && !isTyping && Boolean(message?.blocks?.length) && shouldUseOrderedRender(message!);
  const rawText = useOrderedRender && message ? collectBlockText(message) : message?.text || '';
  const visibleText = preprocessChartMarkers(rawText);
  const reasoningText = useOrderedRender ? '' : message?.reasoningText || '';
  const hasAnyReasoning = reasoningText.trim().length > 0;
  const hasToolCalls = Boolean(!isUser && message?.toolCalls && message.toolCalls.length > 0);
  // 产物由 PptArtifactCard / WebsiteArtifactCard / ChartMessage / A2uiRenderer
  // 各自渲染，不依赖这个气泡承载。
  const shouldRenderBubble = shouldRenderBubbleFor({
    isTyping: Boolean(isTyping),
    isUser,
    hasVisibleText: visibleText.trim().length > 0,
    hasReasoning: hasAnyReasoning,
    isStreaming: Boolean(isStreaming),
    hasToolCalls,
  });
  const hasStructuredContent = !isUser && /```|(?:^|\n)\|.+\|/.test(visibleText);
  const showAssistantWaiting = !isUser && Boolean(isStreaming) && !visibleText.trim() && !hasAnyReasoning && !isTyping;
  const canCopyMessage = visibleText.trim().length > 0;
  const [isCopied, setIsCopied] = useState(false);
  const config = getAppConfig();
  const sessionCounter = useRef({ current: 0 });
  const copyTimeoutRef = useRef<number | null>(null);
  // ?????LLMOps????/?? ??? agent_message_feedbacks
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const handleFeedback = (rating: 'up' | 'down') => {
    const next = feedback === rating ? null : rating;
    setFeedback(next);
    if (!next) return;
    void submitFeedback({
      session_id: sessionId || '',
      message_index: index,
      rating,
    }).catch(() => undefined);
  };

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current !== null) {
        clearTimeout(copyTimeoutRef.current);
      }
    };
  }, []);

  const handleCopy = useCallback(async () => {
    if (visibleText) {
      if (copyTimeoutRef.current !== null) clearTimeout(copyTimeoutRef.current);
      await copyToClipboard(visibleText);
      setIsCopied(true);
      copyTimeoutRef.current = window.setTimeout(() => setIsCopied(false), 2000);
    }
  }, [visibleText]);

  return (
    <motion.div
      id={message?.id ? `msg-${message.id}` : undefined}
      initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.6, delay: Math.min(index * 0.08, 0.8), ease: [0.16, 1, 0.3, 1] }}
      layout="position"
      className={cn("flex mx-auto w-full items-start group/msg", wideLayout ? "max-w-[92rem] gap-8 px-8" : "max-w-4xl gap-4", isUser ? "flex-row-reverse" : "flex-row")}
    >
      <motion.div whileHover={{ scale: 1.1, rotate: [0, -5, 5, 0] }}
        title={isUser ? "你" : "AI 助手"}
        className={cn("w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm z-10 transition-all",
          isUser ? "bg-[var(--primary)] text-[var(--primary-foreground)]" : "bg-[var(--surface-1)] border border-[var(--border-subtle)] text-[var(--foreground)]"
        )}>
        {isUser ? <UserAvatarIcon size={20} /> : <MascotCool size={20} />}
      </motion.div>

      <div className={cn("flex flex-col gap-1", wideLayout ? "max-w-[78%]" : "max-w-[80%]", isUser ? "items-end" : "items-start")}>
        {/* Tool Calls（按序渲染时工具已就地展示，不再重复渲染总览） */}
        {!useOrderedRender && !isUser && message?.toolCalls && message.toolCalls.length > 0 && config.enableSearch && (
          <div className="mb-1 w-full text-left">
            <details className="group [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest text-[var(--muted-foreground)] bg-[var(--surface-1)] hover:bg-[var(--surface-1)] border border-[var(--border-subtle)] px-3 py-1.5 rounded-full shadow-sm w-fit cursor-pointer transition-all select-none">
                <WrenchIcon size={12} className="text-[var(--muted-foreground)]" />
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
                  const statusClass = isSuccess ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" : isError ? "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300" : needsApproval ? "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" : wasRejected ? "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300" : wasApproved ? "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300" : "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300";
                  const statusLabel = isSuccess ? '已完成' : isError ? '失败' : needsApproval ? '待审批' : wasRejected ? '已拒绝' : wasApproved ? '已批准' : '执行中';
                  const executionState = isSuccess ? 'done' : isError || wasRejected || wasNotExecuted ? 'idle' : 'active';
                  const executionBody = wasNotExecuted ? '运行时反馈该工具调用未实际执行。' : isSuccess ? '工具执行完成。' : isError ? '工具执行失败，请查看返回内容中的错误信息。' : needsApproval ? '该工具需要人工审批后才会执行。' : wasApproved ? '审批已通过，等待工具返回结果。' : wasRejected ? '审批已拒绝，工具不会继续执行。' : '工具正在处理中，请稍候。';
                  const resultDotClass = isSuccess ? "border-emerald-500 bg-emerald-500" : isError ? "border-rose-500 bg-rose-500" : tool.result ? "border-emerald-500 bg-emerald-500" : "border-[var(--border-strong)] bg-[var(--surface-1)]";
                  const resultTitleClass = isSuccess ? "text-emerald-700 dark:text-emerald-300" : isError ? "text-rose-700 dark:text-rose-300" : tool.result ? "text-emerald-700 dark:text-emerald-300" : "text-[var(--muted-foreground)]";
                  return (
                    <motion.div key={idx} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.1 }}
                      className="max-w-[34rem] rounded-3xl border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-3 text-xs text-[var(--muted-foreground)] shadow-md backdrop-blur-sm">
                      <div className="mb-3 flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
                        <div className="flex items-center gap-2"><WrenchIcon size={13} className="text-[var(--muted-foreground)]" /><span className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--foreground)]">{tool.name}</span></div>
                        <span className={cn("rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]", statusClass)}>{statusLabel}</span>
                      </div>
                      {isAdmin ? (
                        <>
                          {metaItems.length > 0 && <div className="mb-3 flex flex-wrap gap-1.5">{metaItems.map(item => <span key={item} className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-2)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--muted-foreground)]">{item}</span>)}</div>}
                          {detailText && <div className={cn("mb-3 rounded-xl border px-3 py-2 text-[11px] leading-relaxed", isError ? "border-rose-200/90 bg-rose-50/90 text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300" : "border-[var(--border-subtle)] bg-[var(--surface-3)] text-[var(--muted-foreground)]")}>{detailText}</div>}
                          <div className="flex flex-col">
                            <ToolTimelineStep title="调用阶段" state="done" body="已向运行时发起工具调用，请求参数已发送。" />
                            <ToolTimelineStep title="执行状态" state={executionState} body={executionBody} />
                            <div className="grid grid-cols-[1rem_1fr] gap-3">
                              <div className="flex justify-center"><div className={cn("mt-1 h-3 w-3 rounded-full border-2", resultDotClass)} /></div>
                              <div>
                                <div className={cn("text-[11px] font-semibold uppercase tracking-[0.14em]", resultTitleClass)}>返回结果</div>
                                <div className="mt-1">{tool.result ? <ToolResultPreview result={tool.result} isError={isError} /> : <div className="rounded-xl border border-dashed border-sky-200/60 bg-sky-50/40 px-3 py-2 text-[11px] text-[var(--muted-foreground)]">等待工具返回内容</div>}</div>
                              </div>
                            </div>
                          </div>
                        </>
                      ) : <div className="text-[11px] text-[var(--muted-foreground)]">{isSuccess ? '工具执行完成' : isError ? '工具执行失败' : executionBody}</div>}
                    </motion.div>
                  );
                })}
              </div>
            </details>
          </div>
        )}

        {shouldRenderBubble && (
            <div id={message?.id ? `bubble-${message.id}` : undefined}
              className={cn("px-5 py-3 rounded-[2rem] relative group max-w-full min-w-0 transition-colors duration-300 overflow-hidden",
                hasStructuredContent ? "w-full" : "w-fit", !isUser && isStreaming && "min-h-[3.5rem] min-w-[10rem]",
                isUser ? "bg-[var(--bubble-user)] text-[var(--bubble-user-text)] rounded-tr-none shadow-lg hover:shadow-xl" : "bg-[var(--bubble-ai)] backdrop-blur-xl text-[var(--foreground)] rounded-tl-none border border-[var(--border-subtle)] hover:bg-[var(--surface-1)] shadow-xs")}>

            {!useOrderedRender && !isUser && !isTyping && message?.toolCalls && message.toolCalls.length > 0 && isStreaming && (
              <div className="flex flex-col gap-1.5 mb-3"><AnimatePresence>{message.toolCalls.map((tool, i) => <LiveToolCall key={`${tool.id || i}-${tool.status}`} tool={tool} />)}</AnimatePresence></div>
            )}

            {showAssistantWaiting && !isTyping && (!message?.toolCalls || message.toolCalls.length === 0) && <div className="mb-2"><AssistantWaitingIndicator /></div>}

            {isTyping ? (
              <div className="flex items-center gap-2 h-6 px-1">
                {[0, 0.2, 0.4].map(delay => <motion.span key={delay} className="w-2 h-2 bg-[var(--muted-foreground)] rounded-full shadow-sm" animate={{ y: [0, -6, 0], scale: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity, ease: "easeInOut", delay }} />)}
              </div>
            ) : isUser ? (
              <div className="flex flex-col gap-3">
                {message?.attachments && message.attachments.length > 0 && (
                  <div className="flex flex-wrap gap-3 mb-1">
                    {message.attachments.map((att, i) => (
                      <motion.div whileHover={{ scale: 1.05 }} key={i} className="max-w-[240px] rounded-2xl overflow-hidden border border-current/20 shadow-lg ring-4 ring-current/5">
                        {att.type.startsWith('image/') ? <img src={att.url} alt={att.name} loading="lazy" className="w-full h-auto object-cover max-h-52" /> : <div className="bg-current/10 p-3 flex items-center gap-3"><WrenchIcon size={16} /><span className="text-xs font-semibold truncate">{att.name}</span></div>}
                      </motion.div>
                    ))}
                  </div>
                )}
                <p className="whitespace-pre-wrap break-words leading-relaxed tracking-tight font-medium"><HighlightedText text={message?.text || ''} counter={sessionCounter.current} searchQuery={searchQuery} activeMatchId={activeMatchId} messageId={message?.id} /></p>
              </div>
            ) : useOrderedRender && message ? (
              <OrderedAssistantContent
                message={message}
                counter={sessionCounter.current}
                searchQuery={searchQuery}
                activeMatchId={activeMatchId ?? null}
                isAdmin={isAdmin}
                isStreaming={Boolean(isStreaming)}
                sessionId={sessionId}
                onOpenArtifact={onOpenArtifact as never}
              />
            ) : (
              <div className="prose prose-slate prose-sm max-w-none break-words [overflow-wrap:anywhere] prose-p:my-0 prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0 prose-pre:shadow-none prose-pre:border-none">
                {reasoningText && (
                  <details className="group mb-3 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-[var(--muted-foreground)] [&_summary::-webkit-details-marker]:hidden">
                    <summary className="flex cursor-pointer select-none items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
                      <BrainCircuit size={13} className="text-[var(--muted-foreground)]" /><span>思考过程</span>
                      <ChevronDownIcon size={12} className="ml-auto transition-transform duration-300 group-open:-rotate-180" />
                    </summary>
                    <div className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words border-t border-[var(--border-subtle)] pt-2 text-xs leading-relaxed text-[var(--muted-foreground)] italic">{reasoningText}</div>
                  </details>
                )}
                {visibleText ? (
                  <ErrorBoundary fallback={<InlineErrorFallback error="Markdown 渲染失败" />}>
                  <ReactMarkdown remarkPlugins={[remarkGfm, ...(config.enableLaTeX ? [remarkMath] : [])]} rehypePlugins={[...(config.enableLaTeX ? [rehypeKatex] : [])]}
                    components={{
                      code: (props) => <CodeBlock {...props} onOpenArtifact={onOpenArtifact} />,
                      pre: ({ children }) => <>{children}</>,
                      // markdown 图片语法 `![alt](outputs/x.png)` 必须重写 src，
                      // 否则工作区相对路径会被浏览器按页面 URL 解析成 404。
                      img: ({ src, alt }) => <OutputImage src={src} alt={alt} sessionId={sessionId} />,
                      p: ({ children }) => <p>{renderOutputImages(processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id), sessionId)}</p>,
                      table: ({ children }) => <MarkdownTable>{children}</MarkdownTable>,
                      thead: ({ children }) => <MarkdownTableHead>{children}</MarkdownTableHead>,
                      tr: ({ children }) => <MarkdownTableRow>{children}</MarkdownTableRow>,
                      th: ({ children }) => <TableHeaderCell>{children}</TableHeaderCell>,
                      td: ({ children }) => <TableCell counter={sessionCounter.current} searchQuery={searchQuery} activeMatchId={activeMatchId} messageId={message?.id}>{children}</TableCell>,
                      li: ({ children }) => <li>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</li>,
                      h1: ({ children }) => <h1>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</h1>,
                      h2: ({ children }) => <h2>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</h2>,
                      h3: ({ children }) => <h3>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</h3>,
                      h4: ({ children }) => <h4>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</h4>,
                      h5: ({ children }) => <h5>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</h5>,
                      h6: ({ children }) => <h6>{processChildren(children, sessionCounter.current, searchQuery, activeMatchId, message?.id)}</h6>,
                    }}>{visibleText}</ReactMarkdown>
                  </ErrorBoundary>
                ) : <span className="text-sm font-medium text-[var(--muted-foreground)]"> </span>}
                {!isUser && isStreaming && visibleText && <motion.span className="inline-block w-[2px] h-[1.2em] bg-[var(--foreground)] rounded-full align-text-bottom ml-px" animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 0.8, repeat: Infinity }} />}
              </div>
            )}
            </div>
        )}

        {/* ── 产物区（图表 / GenUI / 产物卡片）统一放在文字气泡**下方** ──
             
            阅读顺序应当是「先看模型说了什么，再看它产出的东西」。此前这些都
            排在气泡上方，一进对话就先撞上一张大图表或交互界面，文字被挤到
            下面，很像加载顺序错了。

            产物卡（PPT/网站）放最后：它是「打开预览」的入口而非内容本体，
            紧贴时间戳更符合「操作区在底部」的直觉。

            始终在下方、不随流式跳变：流式早期还没有文字时它们单独占位，
            文字出现后自然接在下面，不会先上后下地闪一次。 */}
        {!isUser && message?.chartMessages?.length ? (
          <div className="w-full space-y-2 mt-2">
            {message.chartMessages.map((chart, i) => (
              <ChartMessage key={`chart-${message.id}-${i}`} chart={chart} />
            ))}
          </div>
        ) : null}

        {!isUser && message?.a2uiMessages?.length ? (
          <div className="w-full mt-2">
            <A2uiRenderer
              messages={message.a2uiMessages}
              onAction={onA2uiAction}
              onDataChange={onA2uiDataChange}
            />
          </div>
        ) : null}

        {!isUser && message ? (
          <div className="mt-2 flex flex-wrap gap-2">
            <PptArtifactCard message={message} onOpenArtifact={onOpenArtifact} />
            <WebsiteArtifactCard message={message} onOpenArtifact={onOpenArtifact} />
          </div>
        ) : null}

        {message?.id && !isTyping && (
          <div className={cn("text-[9px] font-semibold uppercase tracking-[0.1em] px-2 mt-1.5 flex items-center gap-2",
            "text-[var(--muted-foreground)]"
          )}>
            <span>{(() => { const ts = parseInt(message.id); return isNaN(ts) ? '' : new Date(ts).toLocaleTimeString('zh-CN', { timeZone: APP_TIME_ZONE, hour: '2-digit', minute: '2-digit' }); })()}</span>
            {!isUser && visibleText && <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="transition-opacity md:opacity-0 md:group-hover:opacity-100">· {visibleText.length} 字</motion.span>}
            {canCopyMessage && (
              <button onClick={handleCopy} title="复制" aria-label="复制消息" className={cn("transition-colors duration-200",
                "text-[var(--muted-foreground)] hover:text-[var(--accent-foreground)]"
              )}>
                {isCopied ? <CheckIcon size={12} className="text-emerald-500 dark:text-emerald-400" /> : <CopyIcon size={12} />}
              </button>
            )}
            {!isUser && visibleText && (
              <span className="inline-flex items-center gap-1.5 transition-opacity md:opacity-0 md:group-hover:opacity-100">
                <button
                  onClick={() => handleFeedback('up')}
                  title="有帮助"
                  aria-label="有帮助"
                  className={cn('transition-colors duration-200 hover:text-emerald-600', feedback === 'up' && 'text-emerald-600')}
                >
                  <ThumbsUp size={12} />
                </button>
                <button
                  onClick={() => handleFeedback('down')}
                  title="没帮助"
                  aria-label="没帮助"
                  className={cn('transition-colors duration-200 hover:text-rose-600', feedback === 'down' && 'text-rose-600')}
                >
                  <ThumbsDown size={12} />
                </button>
              </span>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
});
