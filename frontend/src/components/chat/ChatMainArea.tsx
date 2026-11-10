import React, { useCallback, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChatTimeline } from './ChatTimeline';
import { ChatSearch } from './ChatSearch';
import { MessagesList } from './MessagesList';
import { PendingApprovalPanel } from './PendingApprovalPanel';
import { EmailPreviewPanel, EmailPreview } from './EmailPreviewPanel';
import { DecisionPanel } from './DecisionPanel';
import { ChatInput } from './ChatInput';
import { MascotState } from '../ui/MascotState';
import { MascotCompanion } from '../ui/MascotCompanion';
import { AlertCircleIcon, ChevronDownIcon } from '../ui/AnimatedIcons';
import { Globe, Presentation, Sparkles } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../shadcn/tooltip';
import { useChat } from '../../contexts/ChatContext';
import { useChatStore } from '../../stores/chatStore';
import { cn } from '../../lib/utils';
import { getStoredUser } from '../../services/authService';
import { issueWebsitePreviewUrl } from '../../services/websiteService';
import { getSessionArtifacts } from '../../services/agentService';
import { toast } from 'sonner';

export const ChatMainArea = React.memo(() => {
  // 从 Context 获取 hook 返回值和派生状态
    /**
   * A2UI 数据变化（表单输入）。
   *
   * 取舍：不在这里直接发消息 —— 用户每敲一个字都发一条会污染对话。
   * 仅在「值确实变了」时记录最新数据，等用户点按钮/提交时随 action
   * 一起带给智能体；智能体可据此调用 update_interface 局部刷新界面。
   */
  const a2uiDataRef = useRef<Record<string, unknown>>({});
  const handleA2uiDataChange = (
    data: Record<string, unknown>,
    surfaceId?: string,
  ) => {
    a2uiDataRef.current = { ...data, __surface: surfaceId ?? '' };
  };
  // 点击提交时读取表单当前值（随动作一起带给智能体）
  const getA2uiData = React.useCallback(() => a2uiDataRef.current, []);

const {
    currentSession, isLoading, isWideConversation,
    isUserScrolledUp, error, runStatus,
    showSearch, searchQuery, searchMatchesCount, searchCurrentIndex, activeMatchId,
    pendingApprovals, pendingDecisions,
    scrollRef, messagesEndRef, chatInputRef, virtuosoRef,
    currentSessionId,
    handleScroll, handleJumpToBottom, handleSend, handleStopGeneration,
    handleApprovalDecision, handleDecisionMade,
    setError, setSearchQuery, setShowSearch,
    prevMatch, nextMatch, onSuggestionClick, onOpenArtifact,
    onAgentProfileChange, isModeLocked,
  } = useChat();

  // 从 Zustand store 获取 UI 状态
  const {
    inputValue, setInputValue,
    chatMode, setChatMode,
    agentProfiles, selectedAgentProfileId,
    isMobile,
    artifact, setArtifact,
    approvalMode, setApprovalMode,
    planMode, setPlanMode,
  } = useChatStore();
  // 虚拟化模式（长会话）需要把真实滚动容器传给 Virtuoso 的 customScrollParent
  const [scrollParent, setScrollParent] = useState<HTMLDivElement | null>(null);
  const attachScrollRef = useCallback((el: HTMLDivElement | null) => {
    (scrollRef as React.MutableRefObject<HTMLDivElement | null>).current = el;
    setScrollParent(el);
  }, [scrollRef]);
  // 分离邮件审批和其他审批
  const { emailApprovals, otherApprovals } = useMemo(() => {
    const emailIds = new Set<string>();
    const emailPreviews: EmailPreview[] = [];
    const other: typeof pendingApprovals = [];

    for (const approval of pendingApprovals) {
      // 检查是否是 send_email 工具
      if (approval.name === 'send_email' && approval.arguments) {
        // arguments 可能是 JSON 字符串（后端偶发下发字符串形态），
        // 直接强转为对象会让 to/subject 为 undefined → 渲染出空白确认卡
        let args: Record<string, unknown> = {};
        if (typeof approval.arguments === 'string') {
          try {
            args = JSON.parse(approval.arguments) as Record<string, unknown>;
          } catch {
            continue; // 解析失败的邮件审批不进面板，交给 other 分支走通用审批 UI
          }
        } else {
          args = approval.arguments as Record<string, unknown>;
        }
        emailPreviews.push({
          approval_id: approval.approvalId || '',
          to: String(args.to || ''),
          subject: String(args.subject || ''),
          body: String(args.body || ''),
          cc: args.cc ? String(args.cc) : undefined,
          is_html: Boolean(args.is_html),
        });
        emailIds.add(approval.approvalId || '');
      } else {
        other.push(approval);
      }
    }

    return {
      emailApprovals: emailPreviews,
      otherApprovals: other,
    };
  }, [pendingApprovals]);

  // 产物面板关闭后的「重新打开」入口：
  // 产物卡片在消息里，消息一长就找不到，这里在输入区上方常驻一个入口。
  //
  // **必须覆盖全部产物类型。** 早先只认 ppt / website，于是表格、文档、
  // 邮件面板一旦收起，这个按钮永远不出现 —— 用户看到的就是「右侧边栏
  // 收起来后再也打不开」。sheet / document 的 snapshot 体量大、不进
  // localStorage 缓存，所以这里只记引用，真正打开时从后端回源
  // （见 handleReopenArtifact）。
  const reopenableArtifact = React.useMemo(() => {
    if (artifact) return null;
    const messages = [...(currentSession?.messages ?? [])].reverse();
    const msg = messages.find(
      (m) =>
        m.role === 'model' &&
        ((m.pptArtifact?.status === 'ready' && m.pptArtifact.html) ||
          (m.websiteArtifact?.status === 'ready' && m.websiteArtifact?.html) ||
          (m.sheetArtifact?.status === 'ready' && m.sheetArtifact.artifactId) ||
          m.documentArtifact?.status === 'ready'),
    );
    if (!msg) return null;
    if (msg.pptArtifact?.html) {
      return {
        language: 'ppt' as const,
        artifactId: msg.pptArtifact.artifactId ?? '',
        html: msg.pptArtifact.html,
        title: msg.pptArtifact.title || 'PPT 演示文稿',
        slideCount: msg.pptArtifact.slideCount || 0,
        theme: msg.pptArtifact.theme,
      };
    }
    if (msg.websiteArtifact?.html) {
      return {
        language: 'website' as const,
        artifactId: msg.websiteArtifact?.artifactId || '',
        html: msg.websiteArtifact?.html || '',
        title: msg.websiteArtifact?.title || '网站预览',
        projectSlug: msg.websiteArtifact?.projectSlug || '',
        stack: msg.websiteArtifact?.stack,
        sessionId: currentSessionId ?? undefined,
      };
    }
    if (msg.sheetArtifact?.artifactId) {
      // snapshot 不在缓存里，占位即可；handleReopenArtifact 会回源补齐
      return {
        language: 'spreadsheet' as const,
        artifactId: msg.sheetArtifact.artifactId,
        title: msg.sheetArtifact.title || '电子表格',
        snapshot: {} as Record<string, unknown>,
        sheetNames: msg.sheetArtifact.sheetNames ?? [],
        sheetCount: msg.sheetArtifact.sheetCount ?? 0,
        sessionId: currentSessionId ?? undefined,
      };
    }
    if (msg.documentArtifact?.artifactId) {
      return {
        language: 'document' as const,
        artifactId: msg.documentArtifact.artifactId,
        title: msg.documentArtifact.title || '文档',
        snapshot: {} as Record<string, unknown>,
        charCount: 0,
        sessionId: currentSessionId ?? undefined,
      };
    }
    return null;
  }, [artifact, currentSession?.messages, currentSessionId]);

  // 重新打开产物面板。
  //
  // - website：预览令牌可能已过 15 分钟 TTL（页面开着很久后点「重新打开」），
  //   直接复用旧 URL 会让 iframe 渲染 403 错误页 —— 所以先现签一个新 URL，
  //   签发失败退回 preview_html 内联 srcDoc（自包含、永不过期）。
  // - spreadsheet / document：snapshot 体量大、不在缓存里，必须回源拿最新快照，
  //   否则打开的是一个空编辑器（比打不开更糟：用户会以为内容丢了）。
  const handleReopenArtifact = useCallback(async () => {
    const next = reopenableArtifact;
    if (!next) return;

    if (next.language === 'website' && next.sessionId && next.projectSlug) {
      try {
        const { url } = await issueWebsitePreviewUrl(next.sessionId, next.projectSlug);
        setArtifact({ ...next, previewUrl: url });
        return;
      } catch {
        // 签发失败（离线 / 后端异常）→ 走内联兜底
      }
    }

    if (
      (next.language === 'spreadsheet' || next.language === 'document') &&
      next.sessionId
    ) {
      try {
        const artifacts = await getSessionArtifacts(next.sessionId);
        if (next.language === 'spreadsheet' && artifacts.sheet_artifact) {
          const sheet = artifacts.sheet_artifact;
          setArtifact({
            language: 'spreadsheet',
            artifactId: sheet.artifact_id,
            title: sheet.title,
            snapshot: sheet.snapshot,
            sheetNames: sheet.sheet_names ?? [],
            sheetCount: sheet.sheet_count ?? 0,
            sessionId: next.sessionId,
            version: sheet.version,
          });
          return;
        }
        if (next.language === 'document' && artifacts.document_artifact) {
          const doc = artifacts.document_artifact;
          setArtifact({
            language: 'document',
            artifactId: doc.artifact_id,
            title: doc.title,
            snapshot: doc.snapshot,
            charCount: doc.char_count ?? 0,
            sessionId: next.sessionId,
            version: doc.version,
          });
          return;
        }
      } catch {
        // 回源失败：提示比静默打开空编辑器好
        toast.error('产物内容加载失败，请刷新页面后重试');
        return;
      }
    }

    setArtifact(next);
  }, [reopenableArtifact, setArtifact]);

  return (
    <>
      <TooltipProvider delayDuration={250} skipDelayDuration={400}>
      {/* 时间线导航 */}
      <AnimatePresence>
        {!isMobile && currentSession?.messages && (
          <ChatTimeline messages={currentSession.messages} />
        )}
      </AnimatePresence>

      {/* 消息区域 + 精灵叠加层 */}
      <div className="flex-1 relative overflow-hidden">
        {/* 动态陪伴精灵 */}
        <AnimatePresence>
          {isLoading && runStatus.phase !== 'streaming' && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute inset-0 z-20 flex items-center justify-center pointer-events-none"
            >
              <MascotCompanion
                size={100}
                phase={
                  runStatus.phase === 'generating_ppt' ? 'generating_ppt'
                  : runStatus.phase === 'rendering_ppt' ? 'rendering_ppt'
                  : runStatus.phase === 'error' ? 'error'
                  : 'thinking'
                }
                label={runStatus.label}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* 可滚动消息列表 */}
        <div
          ref={attachScrollRef}
          onScroll={handleScroll}
          className={cn(
            "h-full overflow-y-auto custom-scrollbar",
            isMobile ? "pr-4" : "pr-16",
            isWideConversation ? "px-6 py-8 md:px-10 lg:px-14 xl:px-16" : "p-4 md:p-8"
          )}
        >
          {/* 搜索浮层 */}
          <ChatSearch
            showSearch={showSearch}
            searchQuery={searchQuery}
            setSearchQuery={setSearchQuery}
            searchCurrentIndex={searchCurrentIndex}
            searchMatchesCount={searchMatchesCount}
            onPrev={prevMatch}
            onNext={nextMatch}
            onClose={() => { setShowSearch(false); setSearchQuery(''); }}
          />

          {/* 右下角搜索按钮 —— absolute 而非 fixed：fixed 会逃逸到视口，
              产物面板打开时悬浮盖在预览上（走查 bug）。挂在消息区内右下角 */}
          <div className="absolute right-4 bottom-4 flex flex-col gap-3 z-40">
            <button
              onClick={() => setShowSearch(!showSearch)}
              className={cn(
                "w-12 h-12 rounded-2xl flex items-center justify-center transition-all shadow-lg border hover:scale-105 active:scale-95",
                showSearch
                  ? "bg-[var(--primary)] text-[var(--primary-foreground)] border-[var(--primary)]"
                  : "bg-[var(--surface-1)] text-[var(--muted-foreground)] border-[var(--border-subtle)] hover:bg-[var(--surface-2)]"
              )}
              aria-label="切换搜索"
            >
              <div className={cn("transition-transform duration-200", showSearch && "rotate-90")}>
                {showSearch ? (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
                  </svg>
                )}
              </div>
            </button>
          </div>

          {/* 错误提示 */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}
                className={cn(
                  "absolute top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-4 py-3 rounded-2xl shadow-lg border",
                  "bg-red-50 border-red-200 text-red-700 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-300"
                )}
              >
                <AlertCircleIcon size={18} />
                <span className="text-sm font-medium">{error}</span>
                <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700 dark:hover:text-red-200" aria-label="关闭错误提示">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </motion.div>
            )}
          </AnimatePresence>

          <MessagesList
            currentSession={currentSession ?? undefined}
            isLoading={isLoading}
            wideLayout={isWideConversation}
            searchQuery={searchQuery}
            activeMatchId={activeMatchId}
            onSend={handleSend}
            onA2uiDataChange={handleA2uiDataChange}
            getA2uiData={getA2uiData}
            onSuggestionClick={onSuggestionClick}
            onOpenArtifact={onOpenArtifact}
            messagesEndRef={messagesEndRef}
            scrollParent={scrollParent}
            virtuosoRef={virtuosoRef}
          />
        </div>
      </div>

      {/* 输入区域 */}
      <div className="p-4 md:p-6 bg-transparent flex-shrink-0 relative">
        {/* 运行预算：第 N/M 步（让用户知道边界，避免误以为卡死） */}
        <AnimatePresence>
          {isLoading && runStatus.maxSteps ? (
            <motion.div
              key="run-budget"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              className="absolute -top-2 left-1/2 z-30 -translate-x-1/2"
            >
              <div className="flex items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-3 py-1 text-[11px] shadow-sm backdrop-blur">
                <span className="text-[var(--muted-foreground)]">{runStatus.label}</span>
                <span className="tabular-nums text-[var(--foreground)]">
                  第 {(runStatus.step ?? 0) + 1} / {runStatus.maxSteps} 步
                </span>
                <div className="h-1 w-16 overflow-hidden rounded-full bg-[var(--surface-2)]">
                  <div
                    className="h-full rounded-full bg-[var(--ring)] transition-[width] duration-300"
                    style={{
                      width: `${Math.min(
                        100,
                        (((runStatus.step ?? 0) + 1) / Math.max(1, runStatus.maxSteps)) * 100,
                      )}%`,
                    }}
                  />
                </div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
        <AnimatePresence>
          {isUserScrolledUp && (
            <motion.div
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}
              className="absolute -top-4 left-0 right-0 flex justify-center z-30"
            >
              <button
                onClick={handleJumpToBottom}
                className="flex items-center gap-2 px-6 py-1.5 bg-[var(--primary)] text-[var(--primary-foreground)] rounded-full text-[10px] font-semibold uppercase tracking-[0.2em] shadow-2xl border border-[var(--border-strong)] hover:opacity-90 transition-all active:scale-95 group"
              >
                <span>回到底部</span>
                <ChevronDownIcon size={12} className="group-hover:translate-y-0.5 transition-transform" />
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* 产物面板关闭后：重新打开入口（通用，不区分产物类型） */}
        <AnimatePresence>
          {reopenableArtifact && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="absolute -top-3 right-0 z-30"
            >
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => void handleReopenArtifact()}
                    className="flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)]/90 px-2.5 py-1.5 text-[var(--muted-foreground)] shadow-sm backdrop-blur transition-all duration-200 hover:text-[var(--foreground)] hover:shadow-md active:scale-95"
                    aria-label="重新打开产物预览"
                  >
                    {reopenableArtifact.language === 'ppt' ? (
                      <Presentation size={13} />
                    ) : reopenableArtifact.language === 'website' ? (
                      <Globe size={13} />
                    ) : (
                      <Sparkles size={13} />
                    )}
                    <span className="text-[10px] font-semibold">产物</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" sideOffset={8}>
                  {reopenableArtifact.language === 'ppt'
                    ? '重新打开 PPT 预览'
                    : reopenableArtifact.language === 'website'
                      ? '重新打开网站预览'
                      : '重新打开产物预览'}
                </TooltipContent>
              </Tooltip>
            </motion.div>
          )}
        </AnimatePresence>

        <div className={cn("mx-auto", isWideConversation ? "max-w-[92rem] px-8" : "max-w-4xl")}>
          <DecisionPanel decisions={pendingDecisions} onDecision={handleDecisionMade} />
          <EmailPreviewPanel
            emails={emailApprovals}
            onDecision={(id, status, modified) =>
              handleApprovalDecision(id, status, false, false, modified)
            }
          />
          <PendingApprovalPanel approvals={otherApprovals} onDecision={handleApprovalDecision} />
          <ChatInput
            ref={chatInputRef}
            value={inputValue}
            onChange={setInputValue}
            onSend={handleSend}
            onStop={handleStopGeneration}
            isLoading={isLoading}
            chatMode={chatMode}
            setChatMode={setChatMode}
            agentProfiles={agentProfiles}
            selectedAgentProfileId={selectedAgentProfileId}
            onAgentProfileChange={onAgentProfileChange}
            isModeLocked={isModeLocked}
            approvalMode={approvalMode}
            onApprovalModeChange={setApprovalMode}
            planMode={planMode}
            onPlanModeChange={setPlanMode}
            isAdmin={getStoredUser()?.role === 'admin'}
          />
          <div className={cn("mt-3 flex min-h-9 items-center justify-center gap-2 text-xs font-medium", "text-[var(--muted-foreground)]")}>
            {isLoading ? (
              <MascotState
                phase={
                  runStatus.phase === 'generating_ppt' || runStatus.phase === 'rendering_ppt' ? 'thinking'
                  : runStatus.phase === 'streaming' ? 'streaming'
                  : runStatus.phase === 'error' ? 'error'
                  : 'thinking'
                }
                size={22}
                label={runStatus.label}
              />
            ) : (
              <span>
                <MascotState phase="idle" size={22} className="inline-flex" />
                <span className="ml-1">AI 可能会犯错，请核实重要信息。</span>
              </span>
            )}
          </div>
        </div>
      </div>
      </TooltipProvider>
    </>
  );
});
