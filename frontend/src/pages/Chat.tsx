import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion, AnimatePresence, useScroll, useTransform } from 'motion/react';
import { useLocation } from 'react-router-dom';
import { Sidebar } from '../components/chat/Sidebar';
import { ChatMainArea } from '../components/chat/ChatMainArea';
import { ChatArtifactArea } from '../components/chat/ChatArtifactArea';
import { SlideLivePreview } from '../components/ppt/SlideLivePreview';
import { DragOverlay } from '../components/chat/DragOverlay';
import { RandomMascot } from '../components/ui/RandomMascot';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { useChatSearch } from '../hooks/useChatSearch';
import { useChatSessions } from '../hooks/useChatSessions';
import { useChatScroll } from '../hooks/useChatScroll';
import { useChatStream } from '../hooks/useChatStream';
import { useDragAndDrop } from '../hooks/useDragAndDrop';
import { useChatStore } from '../stores/chatStore';
import { ChatContextProvider, type ChatContextValue } from '../contexts/ChatContext';
import { getStoredUser } from '../services/authService';
import { getMyAgents } from '../services/agentProfileService';
import { ChatInputHandle } from '../components/chat/ChatInput';
import { cn } from '../lib/utils';
import { UserInputPanel } from '../components/chat/UserInputPanel';
import { submitUserInput, type UserInputRequest } from '../services/agentService';
import type { VirtuosoHandle } from 'react-virtuoso';
export const Chat = () => {
  const location = useLocation();
  const initialMessage = location.state?.initialMessage as string | undefined;

  // ── Zustand store（UI 状态）──
  const {
    setInputValue,
    chatMode, setChatMode,
    agentProfiles, setAgentProfiles,
    selectedAgentProfileId, setSelectedAgentProfileId,
    isSidebarOpen, setIsSidebarOpen,
    isMobile, setIsMobile,
    artifact, setArtifact,
    isSidebarHiddenByArtifact, setIsSidebarHiddenByArtifact,
    createNewChat: storeCreateNewChat,
  } = useChatStore();

  // ── 会话管理 ──
  const {
    sessions, setSessions,
    currentSessionId, setCurrentSessionId,
    currentSession, visibleSessions,
    hasMoreSessions, loadMoreSessions,
    applySessionState,
    loadSessionMessages,
    deleteSession: deleteSessionBackend,
  } = useChatSessions();

  // ── 搜索 ──
  // 长会话虚拟化时消息可能未渲染进 DOM，搜索跳转需经 Virtuoso scrollToIndex 回退
  const virtuosoRef = useRef<VirtuosoHandle | null>(null);
  const virtualScrollToMessage = useCallback((messageId: string) => {
    const idx = (currentSession?.messages ?? []).findIndex((m) => m.id === messageId);
    if (idx >= 0) virtuosoRef.current?.scrollToIndex({ index: idx, align: 'center' });
  }, [currentSession?.messages]);
  const {
    searchQuery, setSearchQuery,
    showSearch, setShowSearch,
    searchCurrentIndex, searchMatches, nextMatch, prevMatch, activeMatchId,
  } = useChatSearch(currentSession, virtualScrollToMessage);

  // ── 滚动 ──
  const {
    scrollRef, messagesEndRef,
    isUserScrolledUp, scrollToBottom,
    handleJumpToBottom, handleScroll,
  } = useChatScroll();

  // ── Refs ──
  const chatInputRef = useRef<ChatInputHandle>(null);
  const isAdmin = getStoredUser()?.role === 'admin';

  // ── 流式 ──
  const [userInputReq, setUserInputReq] = useState<UserInputRequest | null>(null);

  const {
    isLoading, error, setError, runStatus, pendingDecisions,
    handleSend, handleStopGeneration,
    handleApprovalDecision, handleDecisionMade,
  } = useChatStream({
    sessions, currentSessionId, currentSession: currentSession ?? null,
    chatMode, selectedAgentProfileId,
    selectedAgent: agentProfiles.find((a) => a.id === selectedAgentProfileId) || null,
    setSessions, setCurrentSessionId,
    applySessionState, setArtifact, setInputValue,
    onUserInputRequired: setUserInputReq,
    // 接上 API 审批回调（面板 UI 由 toolCalls 驱动，此处保留扩展点）
    onApiApprovalRequired: () => {
      /* api_approval_required 已在 agentService 转为 toolCalls，触发 PendingApprovalPanel */
    },
  });

  // ── 派生状态 ──
  const currentSessionMessages = currentSession?.messages ?? [];
  const isStreamingResponse = isLoading && currentSessionMessages[currentSessionMessages.length - 1]?.role === 'model';
  const isWideConversation = !artifact && !isMobile;
  const pendingApprovals = useMemo(
    () => currentSessionMessages
      .flatMap((m) => m.toolCalls || [])
      .filter((t) => t.status === 'approval_required' && t.approvalId),
    [currentSessionMessages],
  );
  const isModeLocked = !!currentSession && currentSession.messages.length > 0;

  // ── 检测 send_email 审批请求，自动打开邮件预览面板 ──
  useEffect(() => {
    // 同时检查英文名和中文名（后端会转换为中文显示名）
    const emailApproval = pendingApprovals.find(
      (t) => t.name === 'send_email' || t.name === '发送邮件'
    );
    if (!emailApproval || !emailApproval.arguments) return;

    // 确保 arguments 是对象（可能是 JSON 字符串）
    let args: Record<string, unknown> = {};
    if (typeof emailApproval.arguments === 'string') {
      try {
        args = JSON.parse(emailApproval.arguments);
      } catch {
        return;
      }
    } else {
      args = emailApproval.arguments as Record<string, unknown>;
    }

    // 只有当 to 和 subject 存在时才显示面板
    if (args.to && args.subject) {
      setArtifact({
        language: 'email',
        approvalId: emailApproval.approvalId || '',
        to: String(args.to || ''),
        subject: String(args.subject || ''),
        body: String(args.body || ''),
        cc: args.cc ? String(args.cc) : undefined,
        isHtml: Boolean(args.is_html),
      });
    }
  }, [pendingApprovals, setArtifact]);

  // ── 拖放 ──
  const { isDragging, handleDragEnter, handleDragOver, handleDragLeave, handleDrop } = useDragAndDrop();
  const onDrop = (e: React.DragEvent) => handleDrop(e, (files) => chatInputRef.current?.addFiles(files));  // ── 制品面板 ──
  const { scrollYProgress } = useScroll({ container: scrollRef });
  const borderColor = useTransform(scrollYProgress, [0, 0.2, 1], ['rgba(255,255,255,0.7)', 'rgba(255,255,255,1)', 'rgba(56,189,248,0.4)']);

  // ── 回调 ──
  const createNewChat = useCallback(() => {
    storeCreateNewChat();
    setCurrentSessionId(null);
    if (isMobile) setIsSidebarOpen(false);
  }, [isMobile, storeCreateNewChat, setCurrentSessionId, setIsSidebarOpen]);

  const deleteSession = useCallback(async (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const wasCurrent = currentSessionId === id;
    if (wasCurrent) {
      setArtifact(null);
      setChatMode('general');
      setSelectedAgentProfileId(null);
    }
    // 调用后端 deleteSession；失败时 useChatSessions 内部回滚本地列表
    const ok = await deleteSessionBackend(id);
    if (!ok && wasCurrent) {
      // 回滚 UI 状态（本地会话已恢复）
      const restored = sessions.find((s) => s.id === id);
      if (restored?.mode) setChatMode(restored.mode);
      setSelectedAgentProfileId(restored?.agentProfileId ?? null);
    }
  }, [currentSessionId, sessions, deleteSessionBackend, setArtifact, setChatMode, setSelectedAgentProfileId]);

  const handleOpenArtifact = useCallback((next: any) => setArtifact(next), [setArtifact]);

  const handlePptThemeChange = useCallback((newHtml: string, theme: string) => {
    if (artifact && artifact.language === 'ppt') {
      setArtifact({ ...artifact, html: newHtml, theme });
    }
  }, [artifact, setArtifact]);

  const handleEmailConfirm = useCallback(async (approvalId: string) => {
    await handleApprovalDecision(approvalId, 'approved');
    setArtifact(null);
  }, [handleApprovalDecision, setArtifact]);

  const handleEmailCancel = useCallback(async (approvalId: string) => {
    await handleApprovalDecision(approvalId, 'rejected');
    setArtifact(null);
  }, [handleApprovalDecision, setArtifact]);

  const handleUserInputSubmit = useCallback(async (values: Record<string, string>) => {
    if (!userInputReq || !currentSessionId) return;
    try {
      await submitUserInput(currentSessionId, userInputReq.api_name, values);
      setUserInputReq(null);
      // agent 被阻塞等待，Future 解析后自动继续执行，无需发新消息
    } catch (err) {
      console.error('Submit user input error:', err);
      setError(err instanceof Error ? err.message : '提交参数失败');
    }
  }, [userInputReq, currentSessionId, handleSend, setError]);

  const handleAgentProfileChange = useCallback((profile: any) => {
    setSelectedAgentProfileId(profile?.id ?? null);
    if (profile) setChatMode(profile.response_mode);
  }, [setSelectedAgentProfileId, setChatMode]);

  const onSuggestionClick = useCallback((text: string) => setInputValue(text), [setInputValue]);

  // ── Effects ──
  // 会话切换时同步模式和智能体
  useEffect(() => {
    if (currentSessionId && currentSession?.mode) {
      setChatMode(currentSession.mode);
      setSelectedAgentProfileId(currentSession.agentProfileId ?? null);
    }
  }, [currentSessionId, currentSession?.mode, currentSession?.agentProfileId]);

  // 会话切换时：从后端加载消息（仅依赖 sessionId，避免流式增长重复触发）
  useEffect(() => {
    if (!currentSessionId) return;
    const session = sessions.find(s => s.id === currentSessionId);
    if (!session) return;
    // 缓存中的 artifact 已剥离 HTML（localStorage 瘦身），需要回源补全
    const needsArtifactRefetch = session.messages.some(
      (m) => m.role === 'model' && ((m.pptArtifact && !m.pptArtifact.html) || (m.websiteArtifact && !m.websiteArtifact.html)),
    );
    if (session.messages.length === 0 || needsArtifactRefetch) {
      loadSessionMessages(currentSessionId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId]);

  // 恢复 artifact 面板 — 依赖 sessionId（而非 messages.length），避免流式增长时反复 setArtifact(null)
  const artifactRestoredSessionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!currentSessionId) {
      artifactRestoredSessionRef.current = null;
      setArtifact(null);
      return;
    }
    // 每个会话只恢复一次；流式过程中 messages 变化不再触发清空
    if (artifactRestoredSessionRef.current === currentSessionId) return;

    const messages = currentSession?.messages || [];
    // 消息尚未加载完成时等待（loadSessionMessages 会更新 messages）
    if (messages.length === 0) return;

    // 缓存剥离了 artifact HTML，等待 loadSessionMessages 回源补全后再恢复预览；
    // 此时不标记 restored，回源完成后 effect 会随 currentSession 变化重新执行
    const pendingArtifactHtml = messages.some(
      (m) => m.role === 'model' && ((m.pptArtifact && !m.pptArtifact.html) || (m.websiteArtifact && !m.websiteArtifact.html)),
    );
    if (pendingArtifactHtml) return;

    // 从后往前找第一条带 pptArtifact 或 websiteArtifact 的消息
    const lastPptMsg = [...messages].reverse().find(
      m => m.role === 'model' && m.pptArtifact?.status === 'ready' && m.pptArtifact.html
    );
    const lastWebsiteMsg = [...messages].reverse().find(
      m => m.role === 'model' && m.websiteArtifact?.status === 'ready' && m.websiteArtifact.html
    );

    // 优先恢复 PPT，其次网站
    if (lastPptMsg?.pptArtifact) {
      setArtifact({
        language: 'ppt',
        artifactId: lastPptMsg.pptArtifact.artifactId,
        html: lastPptMsg.pptArtifact.html || '',
        title: lastPptMsg.pptArtifact.title || '',
        slideCount: lastPptMsg.pptArtifact.slideCount || 0,
        theme: lastPptMsg.pptArtifact.theme,
      });
    } else if (lastWebsiteMsg?.websiteArtifact) {
      setArtifact({
        language: 'website',
        artifactId: lastWebsiteMsg.websiteArtifact.artifactId || '',
        html: lastWebsiteMsg.websiteArtifact.html || '',
        title: lastWebsiteMsg.websiteArtifact.title || '',
        projectSlug: lastWebsiteMsg.websiteArtifact.projectSlug || '',
        stack: lastWebsiteMsg.websiteArtifact.stack,
        sessionId: currentSessionId,
      });
    } else {
      setArtifact(null);
    }
    artifactRestoredSessionRef.current = currentSessionId;
    // 刻意不依赖 messages.length：用 ref 保证仅在会话切换/首次加载时恢复
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId, currentSession]);

  // 加载智能体列表
  const [agentProfilesLoaded, setAgentProfilesLoaded] = useState(false);
  useEffect(() => {
    getMyAgents()
      .then((response) => {
        setAgentProfiles(response.items);
        const initialState = location.state as { agentProfileId?: number; mode?: string } | null;
        const initialProfileId = initialState?.agentProfileId;
        if (initialProfileId) {
          const initialProfile = response.items.find((item) => item.id === initialProfileId);
          if (initialProfile) {
            setChatMode(initialProfile.response_mode);
            setSelectedAgentProfileId(initialProfile.id);
            return;
          }
          console.warn(
            `[chat] 首页指定的智能体 ${initialProfileId} 不在已安装列表中，回退到模式默认智能体`,
          );
        }
        const defaultAgent = response.items.find((a) => a.response_mode === chatMode);
        if (defaultAgent) setSelectedAgentProfileId(defaultAgent.id);
      })
      .catch((err) => console.error('Load agents error:', err))
      .finally(() => setAgentProfilesLoaded(true));
  }, []);

  // Auto-select default agent
  useEffect(() => {
    if (selectedAgentProfileId !== null || agentProfiles.length === 0) return;
    const defaultAgent = agentProfiles.find((a) => a.response_mode === chatMode);
    if (defaultAgent) setSelectedAgentProfileId(defaultAgent.id);
  }, [chatMode, agentProfiles, selectedAgentProfileId]);

  // 智能体被删除时清除关联
  useEffect(() => {
    if (selectedAgentProfileId && !agentProfiles.some((a) => a.id === selectedAgentProfileId)) {
      setSelectedAgentProfileId(null);
      setSessions((prev) =>
        prev.map((s) => s.id === currentSessionId ? { ...s, agentProfileId: null, agentName: undefined } : s),
      );
    }
  }, [agentProfiles, selectedAgentProfileId, currentSessionId]);

  // 响应式处理
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (!mobile) setIsSidebarOpen(true);
      else setIsSidebarOpen(false);
    };
    window.addEventListener('resize', handleResize);
    handleResize();
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Escape 键关闭移动端侧边栏
  useEffect(() => {
    if (!isMobile || !isSidebarOpen) return;
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setIsSidebarOpen(false); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isMobile, isSidebarOpen]);

  // 自动滚动 - 当用户主动向上滚动时，不自动跳到底部
  useEffect(() => {
    // 如果用户向上滚动了，不自动滚动
    if (isUserScrolledUp) return;
    const frame = window.requestAnimationFrame(() => scrollToBottom(isStreamingResponse ? 'auto' : 'smooth'));
    return () => window.cancelAnimationFrame(frame);
  }, [sessions, currentSessionId, isLoading, isUserScrolledUp, isStreamingResponse, scrollToBottom]);

  // 自动收起错误提示
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 15000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  // 处理首页带过来的首条消息
  // 必须等智能体列表加载完成后再发：否则 selectedAgentProfileId 还是 null，
  // 首页选中的智能体（如 PPT 设计师）会丢失，请求退回通用助手模式。
  const initialMessageSent = useRef(false);
  useEffect(() => {
    if (initialMessage && !initialMessageSent.current && agentProfilesLoaded) {
      initialMessageSent.current = true;
      handleSend(initialMessage);
      window.history.replaceState({}, document.title);
    }
  }, [initialMessage, agentProfilesLoaded]);

  // 制品面板打开时自动收起侧边栏
  useEffect(() => {
    if (artifact && isSidebarOpen && !isMobile) {
      setIsSidebarOpen(false);
      setIsSidebarHiddenByArtifact(true);
    } else if (!artifact && isSidebarHiddenByArtifact && !isMobile) {
      setIsSidebarOpen(true);
      setIsSidebarHiddenByArtifact(false);
    }
  }, [artifact, isMobile]);

  // ── Context Value ──
  const ctxValue: ChatContextValue = useMemo(() => ({
    sessions, currentSessionId, currentSession: currentSession ?? null, visibleSessions,
    hasMoreSessions, loadMoreSessions,
    isLoading, error, setError, runStatus, pendingDecisions,
    handleSend, handleStopGeneration,
    handleApprovalDecision, handleDecisionMade,
    scrollRef, messagesEndRef, isUserScrolledUp,
    scrollToBottom, handleJumpToBottom, handleScroll,
    virtuosoRef,
    showSearch, setShowSearch, searchQuery, setSearchQuery,
    searchCurrentIndex, searchMatchesCount: searchMatches.length,
    activeMatchId, prevMatch, nextMatch,
    chatInputRef,
    isStreamingResponse, isWideConversation,
    pendingApprovals, isModeLocked, isAdmin,
    onSuggestionClick, onOpenArtifact: handleOpenArtifact,
    onAgentProfileChange: handleAgentProfileChange,
    deleteSession,
  }), [
    // 数据类字段：sessions/currentSession 在流式期间每帧变化，是 context 每帧重建的根因之一；
    // ChatMainArea 经 context 消费 currentSession 渲染消息列表，必须保留实时性，故不从此处移除。
    sessions, currentSessionId, currentSession, visibleSessions,
    hasMoreSessions, isLoading, error, runStatus, pendingDecisions,
    isUserScrolledUp, showSearch, searchQuery, searchCurrentIndex,
    searchMatches.length, activeMatchId, isStreamingResponse,
    isWideConversation, pendingApprovals, isModeLocked, isAdmin,
    // 回调类字段：补齐依赖避免 stale closure（handleSend 等已在 useChatStream 内稳定化）
    loadMoreSessions, setError, handleSend, handleStopGeneration,
    handleApprovalDecision, handleDecisionMade,
    scrollToBottom, handleJumpToBottom, handleScroll,
    setShowSearch, setSearchQuery, prevMatch, nextMatch,
    onSuggestionClick, handleOpenArtifact, handleAgentProfileChange, deleteSession,
  ]);

  return (
    <motion.div
      key="chat"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={onDrop}
      className={cn(
        "flex h-screen font-sans overflow-hidden relative",
        "text-slate-800 bg-[var(--surface-0)]",
      )
    }>
      <DragOverlay isDragging={isDragging} />

      {/* 背景装饰 */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 -left-16 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.06),transparent_70%)] blur-[80px]" />
        <div className="absolute bottom-0 left-1/4 w-[420px] h-[420px] rounded-full bg-[radial-gradient(circle,rgba(129,140,248,0.05),transparent_70%)] blur-[80px]" />
            <div className="absolute inset-0" style={{ backgroundImage: 'radial-gradient(circle, rgba(99,102,241,0.05) 1px, transparent 1px)', backgroundSize: '48px 48px', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0.50), rgba(0,0,0,0.06) 60%, rgba(0,0,0,0.16))' }} />
            <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-zinc-900 opacity-[0.02]" />
      </div>

      {/* 移动端侧边栏遮罩 */}
      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-10"
          />
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {(isSidebarOpen || (isMobile && isSidebarOpen)) && (!artifact || isMobile || isSidebarOpen) && (
          <motion.div
            initial={{ x: -250, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: -250, opacity: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="flex-shrink-0 z-20"
          >
            <Sidebar
              sessions={visibleSessions}
              currentSessionId={currentSessionId}
              onNewChat={createNewChat}
              onSelectSession={(id) => { setCurrentSessionId(id); if (isMobile) setIsSidebarOpen(false); }}
              onDeleteSession={deleteSession}
              onClose={() => setIsSidebarOpen(false)}
              isMobile={isMobile}
              onLoadMore={loadMoreSessions}
              hasMore={hasMoreSessions}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* 侧边栏展开按钮 */}
      <AnimatePresence>
        {!isSidebarOpen && !isMobile && (
          <motion.button
            initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}
            onClick={() => { setIsSidebarOpen(true); setIsSidebarHiddenByArtifact(false); }}
            className={cn(
              "fixed top-4 left-4 z-50 w-12 h-12 border rounded-2xl shadow-sm flex items-center justify-center transition-all group focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2",
              "bg-white/80 border-slate-200 text-zinc-800 hover:bg-white hover:shadow-md"
            )}
            aria-label="展开侧边栏"
          >
            <MascotCool size={24} className="group-hover:scale-110 transition-transform" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* 主区域 */}
      <ChatContextProvider value={ctxValue}>
        <div className="flex-1 flex overflow-hidden relative">
          <main
            id="main-content"
            className={cn(
              "flex flex-col h-full transition-all duration-500 ease-[0.16,1,0.3,1] min-w-0 relative",
              artifact ? "w-[40%] border-r border-slate-200/60" : "w-full",
              isWideConversation && "px-4 lg:px-8 xl:px-10",
            )}
          >
            <ChatMainArea />
            {userInputReq && (
              <div className="absolute inset-x-0 bottom-0 z-30 px-4 pb-4">
                <UserInputPanel
                  request={userInputReq}
                  onSubmit={handleUserInputSubmit}
                  onDismiss={() => setUserInputReq(null)}
                />
              </div>
            )}
          </main>
          <AnimatePresence>
            {chatMode === 'ppt' && (
              <SlideLivePreview
                sessionId={currentSessionId}
                isStreaming={isStreamingResponse}
                hasArtifact={!!artifact}
              />
            )}
          </AnimatePresence>
          <ChatArtifactArea
            artifact={artifact}
            onClose={() => setArtifact(null)}
            borderColor={borderColor}
            onPptThemeChange={handlePptThemeChange}
            onEmailConfirm={handleEmailConfirm}
            onEmailCancel={handleEmailCancel}
            sessionId={currentSessionId}
          />
        </div>
      </ChatContextProvider>
    </motion.div>
  );
};
