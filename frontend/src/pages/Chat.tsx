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

export const Chat = () => {
  const location = useLocation();
  const initialMessage = location.state?.initialMessage as string | undefined;

  // ── Zustand store（UI 状态）──
  const {
    inputValue, setInputValue,
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
  } = useChatSessions();

  // ── 搜索 ──
  const {
    searchQuery, setSearchQuery,
    showSearch, setShowSearch,
    searchCurrentIndex, searchMatches, nextMatch, prevMatch, activeMatchId,
  } = useChatSearch(currentSession);

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
  const {
    isLoading, error, setError, runStatus, pendingDecisions,
    handleSend, handleStopGeneration,
    handleApprovalDecision, handleDecisionMade,
  } = useChatStream({
    sessions, currentSessionId, currentSession,
    chatMode, selectedAgentProfileId,
    selectedAgent: agentProfiles.find((a) => a.id === selectedAgentProfileId) || null,
    setSessions, setCurrentSessionId,
    applySessionState, setArtifact, setInputValue,
  });

  // ── 派生状态 ──
  const currentSessionMessages = currentSession?.messages ?? [];
  const isStreamingResponse = isLoading && currentSessionMessages[currentSessionMessages.length - 1]?.role === 'model';
  const isWideConversation = !artifact && !isMobile;
  const pendingApprovals = useMemo(
    () => isAdmin
      ? currentSessionMessages
          .flatMap((m) => m.toolCalls || [])
          .filter((t) => t.status === 'approval_required' && t.approvalId)
      : [],
    [currentSessionMessages, isAdmin],
  );
  const isModeLocked = !!currentSession && currentSession.messages.length > 0;
  const selectedAgent = agentProfiles.find((a) => a.id === selectedAgentProfileId) || null;

  // ── 拖放 ──
  const { isDragging, handleDragEnter, handleDragOver, handleDragLeave, handleDrop } = useDragAndDrop();
  const onDrop = (e: React.DragEvent) => handleDrop(e, (files) => chatInputRef.current?.addFiles(files));

  // ── 制品面板 ──
  const { scrollYProgress } = useScroll({ container: scrollRef });
  const borderColor = useTransform(scrollYProgress, [0, 0.2, 1], ['rgba(255,255,255,0.7)', 'rgba(255,255,255,1)', 'rgba(56,189,248,0.4)']);

  // ── 回调 ──
  const createNewChat = useCallback(() => {
    storeCreateNewChat();
    setCurrentSessionId(null);
    if (isMobile) setIsSidebarOpen(false);
  }, [isMobile, storeCreateNewChat, setCurrentSessionId, setIsSidebarOpen]);

  const deleteSession = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessions((prev) => prev.filter((s) => s.id !== id));
    setCurrentSessionId((prev) => {
      if (prev !== id) return prev;
      setArtifact(null);
      setChatMode('general');
      setSelectedAgentProfileId(null);
      return null;
    });
  }, [setSessions, setCurrentSessionId, setArtifact, setChatMode, setSelectedAgentProfileId]);

  const handleOpenArtifact = useCallback((next: any) => setArtifact(next), [setArtifact]);

  const handlePptThemeChange = useCallback((newHtml: string, theme: string) => {
    if (artifact && artifact.language === 'ppt') {
      setArtifact({ ...artifact, html: newHtml, theme });
    }
  }, [artifact, setArtifact]);

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

  // 会话切换时：从后端加载消息
  useEffect(() => {
    if (!currentSessionId) return;
    if (currentSession && currentSession.messages.length === 0) {
      loadSessionMessages(currentSessionId);
    }
  }, [currentSessionId, currentSession?.messages.length]);

  // 恢复 artifact 面板（从最后一条有 artifact 的 model 消息）
  useEffect(() => {
    if (!currentSessionId) {
      setArtifact(null);
      return;
    }
    const lastModelMsg = [...(currentSession?.messages || [])].reverse().find(m => m.role === 'model');
    if (lastModelMsg?.pptArtifact?.status === 'ready' && lastModelMsg.pptArtifact.html) {
      setArtifact({
        language: 'ppt',
        artifactId: lastModelMsg.pptArtifact.artifactId,
        html: lastModelMsg.pptArtifact.html,
        title: lastModelMsg.pptArtifact.title || '',
        slideCount: lastModelMsg.pptArtifact.slideCount || 0,
        theme: lastModelMsg.pptArtifact.theme,
      });
    } else if (lastModelMsg?.websiteArtifact?.status === 'ready' && lastModelMsg.websiteArtifact.html) {
      setArtifact({
        language: 'website',
        artifactId: lastModelMsg.websiteArtifact.artifactId || '',
        html: lastModelMsg.websiteArtifact.html,
        title: lastModelMsg.websiteArtifact.title || '',
        projectSlug: lastModelMsg.websiteArtifact.projectSlug || '',
      });
    } else {
      setArtifact(null);
    }
  }, [currentSessionId, currentSession?.messages.length]);

  // 加载智能体列表
  useEffect(() => {
    getMyAgents()
      .then((response) => {
        setAgentProfiles(response.items);
        const initialProfileId = (location.state as any)?.agentProfileId;
        if (initialProfileId) {
          const initialProfile = response.items.find((item) => item.id === initialProfileId);
          if (initialProfile) {
            setChatMode(initialProfile.response_mode);
            setSelectedAgentProfileId(initialProfile.id);
            return;
          }
        }
        const defaultAgent = response.items.find((a) => a.response_mode === chatMode);
        if (defaultAgent) setSelectedAgentProfileId(defaultAgent.id);
      })
      .catch((err) => console.error('Load agents error:', err));
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

  // 自动滚动
  useEffect(() => {
    if (isUserScrolledUp && !isStreamingResponse) return;
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
  const initialMessageSent = useRef(false);
  useEffect(() => {
    if (initialMessage && !initialMessageSent.current) {
      initialMessageSent.current = true;
      handleSend(initialMessage);
      window.history.replaceState({}, document.title);
    }
  }, [initialMessage]);

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
    sessions, currentSessionId, currentSession, visibleSessions,
    hasMoreSessions, loadMoreSessions,
    isLoading, error, setError, runStatus, pendingDecisions,
    handleSend, handleStopGeneration,
    handleApprovalDecision, handleDecisionMade,
    scrollRef, messagesEndRef, isUserScrolledUp,
    scrollToBottom, handleJumpToBottom, handleScroll,
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
    sessions, currentSessionId, currentSession, visibleSessions,
    hasMoreSessions, isLoading, error, runStatus, pendingDecisions,
    isUserScrolledUp, showSearch, searchQuery, searchCurrentIndex,
    searchMatches.length, activeMatchId, isStreamingResponse,
    isWideConversation, pendingApprovals, isModeLocked, isAdmin,
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
      className="flex h-screen text-slate-800 font-sans overflow-hidden selection:bg-zinc-200 selection:text-zinc-900 relative"
      style={{ background: 'linear-gradient(180deg, #d9edf4 0%, #e3f2f8 28%, #dceff5 55%, #dff0f5 100%)' }}
    >
      <DragOverlay isDragging={isDragging} />

      {/* 背景装饰 */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 -left-16 w-[500px] h-[500px] rounded-full bg-[radial-gradient(circle,rgba(14,165,233,0.12),transparent_70%)] blur-[80px] animate-[bg-blob-1_18s_ease-in-out_infinite]" />
        <div className="absolute top-8 -right-10 w-[440px] h-[440px] rounded-full bg-[radial-gradient(circle,rgba(6,182,212,0.10),transparent_70%)] blur-[70px] animate-[bg-blob-2_20s_ease-in-out_infinite]" />
        <div className="absolute bottom-0 left-1/4 w-[420px] h-[420px] rounded-full bg-[radial-gradient(circle,rgba(56,189,248,0.11),transparent_70%)] blur-[80px] animate-[bg-blob-3_17s_ease-in-out_infinite]" />
        <div className="absolute inset-0" style={{ backgroundImage: 'radial-gradient(circle, rgba(14,165,233,0.07) 1px, transparent 1px)', backgroundSize: '48px 48px', maskImage: 'linear-gradient(180deg, rgba(0,0,0,0.50), rgba(0,0,0,0.06) 60%, rgba(0,0,0,0.16))' }} />
        <div className="absolute inset-0 bg-[linear-gradient(108deg,transparent_38%,rgba(255,255,255,0.14)_50%,transparent_64%)] animate-[bg-drift-slow_20s_ease-in-out_infinite]" />
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.02]" />
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
            className="fixed top-4 left-4 z-50 w-12 h-12 bg-white/80 backdrop-blur-md border border-slate-200 rounded-2xl shadow-sm flex items-center justify-center text-zinc-800 hover:bg-white hover:shadow-md transition-all group focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2"
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
              "flex flex-col h-full transition-all duration-700 ease-[0.16,1,0.3,1] min-w-0 relative",
              artifact ? "w-[40%] border-r border-slate-200/60" : "w-full",
              isWideConversation && "px-4 lg:px-8 xl:px-10",
            )}
          >
            <ChatMainArea />
          </main>
          <AnimatePresence>
            <SlideLivePreview
              messages={currentSessionMessages}
              isStreaming={isStreamingResponse}
              hasArtifact={!!artifact}
            />
          </AnimatePresence>
          <ChatArtifactArea artifact={artifact} onClose={() => setArtifact(null)} borderColor={borderColor} onPptThemeChange={handlePptThemeChange} />
        </div>
      </ChatContextProvider>
    </motion.div>
  );
};
