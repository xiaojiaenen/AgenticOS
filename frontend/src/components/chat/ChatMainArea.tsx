import React, { useCallback, useMemo, useState } from 'react';
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

export const ChatMainArea = React.memo(() => {
  // 从 Context 获取 hook 返回值和派生状态
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
        const args = approval.arguments as Record<string, unknown>;
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
  // 产物卡片在消息里，消息一长就找不到，这里在输入区上方常驻一个入口
  const reopenableArtifact = React.useMemo(() => {
    if (artifact) return null;
    const messages = [...(currentSession?.messages ?? [])].reverse();
    const msg = messages.find(
      (m) =>
        m.role === 'model' &&
        ((m.pptArtifact?.status === 'ready' && m.pptArtifact.html) ||
          (m.websiteArtifact?.status === 'ready' && m.websiteArtifact?.html)),
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
    return {
      language: 'website' as const,
      artifactId: msg.websiteArtifact?.artifactId || '',
      html: msg.websiteArtifact?.html || '',
      title: msg.websiteArtifact?.title || '网站预览',
      projectSlug: msg.websiteArtifact?.projectSlug || '',
      stack: msg.websiteArtifact?.stack,
      sessionId: currentSessionId ?? undefined,
    };
  }, [artifact, currentSession?.messages, currentSessionId]);

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
            "h-full overflow-y-auto custom-scrollbar pr-16",
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

          {/* 右下角浮动工具栏 */}
          <div className="fixed right-6 bottom-24 flex flex-col gap-3 z-40">
            <button
              onClick={() => setShowSearch(!showSearch)}
              className={cn(
                "w-12 h-12 rounded-2xl flex items-center justify-center transition-all shadow-lg border hover:scale-105 active:scale-95",
                showSearch
                  ? "bg-zinc-900 text-white border-zinc-800"
                  : "bg-[var(--surface-1)] text-[var(--muted-foreground)] border-white/60 hover:bg-[var(--surface-1)]"
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
                  "bg-red-50 border-red-200 text-red-700"
                )}
              >
                <AlertCircleIcon size={18} />
                <span className="text-sm font-medium">{error}</span>
                <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700" aria-label="关闭错误提示">
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
        <AnimatePresence>
          {isUserScrolledUp && (
            <motion.div
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}
              className="absolute -top-4 left-0 right-0 flex justify-center z-30"
            >
              <button
                onClick={handleJumpToBottom}
                className="flex items-center gap-2 px-6 py-1.5 bg-zinc-900/90 text-white rounded-full text-[10px] font-semibold uppercase tracking-[0.2em] shadow-2xl border border-white/10 hover:bg-zinc-800 transition-all active:scale-95 group"
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
                    onClick={() => setArtifact(reopenableArtifact)}
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
          <EmailPreviewPanel emails={emailApprovals} onDecision={handleApprovalDecision} />
          <PendingApprovalPanel approvals={otherApprovals} onDecision={handleApprovalDecision} />
          <ChatInput
            ref={chatInputRef}
            value={inputValue}
            onChange={setInputValue}
            onSend={(text, files) => handleSend(text, files)}
            onStop={handleStopGeneration}
            isLoading={isLoading}
            chatMode={chatMode}
            setChatMode={setChatMode}
            agentProfiles={agentProfiles}
            selectedAgentProfileId={selectedAgentProfileId}
            onAgentProfileChange={onAgentProfileChange}
            isModeLocked={isModeLocked}
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
