import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { motion, AnimatePresence, useScroll, useTransform } from 'motion/react';
import { useLocation } from 'react-router-dom';
import { Sidebar } from '../components/chat/Sidebar';
import { ChatMainArea } from '../components/chat/ChatMainArea';
import { ChatArtifactArea } from '../components/chat/ChatArtifactArea';
import { DragOverlay } from '../components/chat/DragOverlay';
import { RandomMascot } from '../components/ui/RandomMascot';
import { MascotCool } from '../components/ui/AnimatedIcons';
import { useChatSearch } from '../hooks/useChatSearch';
import { useChatSessions } from '../hooks/useChatSessions';
import { useChatScroll } from '../hooks/useChatScroll';
import { useChatStream } from '../hooks/useChatStream';
import { useDragAndDrop } from '../hooks/useDragAndDrop';
import { Artifact } from '../types';
import { getStoredUser } from '../services/authService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';
import { ChatInputHandle } from '../components/chat/ChatInput';
import { cn } from '../lib/utils';

export const Chat = () => {
  const location = useLocation();
  const initialMessage = location.state?.initialMessage as string | undefined;

  const {
    sessions,
    setSessions,
    currentSessionId,
    setCurrentSessionId,
    currentSession,
    visibleSessions,
    hasMoreSessions,
    loadMoreSessions,
    applySessionState,
  } = useChatSessions();

  const {
    searchQuery, setSearchQuery, showSearch, setShowSearch,
    searchCurrentIndex, searchMatches, nextMatch, prevMatch, activeMatchId
  } = useChatSearch(currentSession);

  const {
    scrollRef,
    messagesEndRef,
    isUserScrolledUp,
    scrollToBottom,
    handleJumpToBottom,
    handleScroll,
  } = useChatScroll();

  const [inputValue, setInputValue] = useState('');
  const [chatMode, setChatMode] = useState<'general' | 'ppt' | 'website'>(
    (location.state as any)?.mode || 'general',
  );
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>(
    (location.state as any)?.agentProfileId || null,
  );
  const selectedAgent = agentProfiles.find((agent) => agent.id === selectedAgentProfileId) || null;

  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [isSidebarHiddenByArtifact, setIsSidebarHiddenByArtifact] = useState(false);

  const chatInputRef = React.useRef<ChatInputHandle>(null);
  const isAdmin = getStoredUser()?.role === 'admin';

  const {
    isLoading,
    error,
    setError,
    runStatus,
    handleSend,
    handleStopGeneration,
    handleApprovalDecision,
  } = useChatStream({
    sessions,
    currentSessionId,
    currentSession,
    chatMode,
    selectedAgentProfileId,
    selectedAgent,
    setSessions,
    setCurrentSessionId,
    applySessionState,
    setArtifact,
    setInputValue,
  });

  const currentSessionMessages = currentSession?.messages ?? [];
  const isStreamingResponse =
    isLoading && currentSessionMessages[currentSessionMessages.length - 1]?.role === 'model';
  const isWideConversation = !artifact && !isMobile;

  const pendingApprovals = useMemo(
    () =>
      isAdmin
        ? currentSessionMessages
            .flatMap((message) => message.toolCalls || [])
            .filter((tool) => tool.status === 'approval_required' && tool.approvalId)
        : [],
    [currentSessionMessages, isAdmin],
  );

  const { isDragging, handleDragEnter, handleDragOver, handleDragLeave, handleDrop } =
    useDragAndDrop();

  const onDrop = (e: React.DragEvent) => {
    handleDrop(e, (files) => {
      chatInputRef.current?.addFiles(files);
    });
  };

  // 会话切换时同步模式和智能体
  useEffect(() => {
    if (currentSessionId && currentSession?.mode) {
      setChatMode(currentSession.mode);
      setSelectedAgentProfileId(currentSession.agentProfileId ?? null);
    }
  }, [currentSessionId, currentSession?.mode, currentSession?.agentProfileId]);

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
        // Auto-select default agent matching current chatMode
        const defaultAgent = response.items.find((a) => a.response_mode === chatMode);
        if (defaultAgent) {
          setSelectedAgentProfileId(defaultAgent.id);
        }
      })
      .catch((err) => console.error('Load agents error:', err));
  }, []);

  // Auto-select default agent matching chatMode when none selected (e.g. new chat)
  useEffect(() => {
    if (selectedAgentProfileId !== null || agentProfiles.length === 0) return;
    const defaultAgent = agentProfiles.find((a) => a.response_mode === chatMode);
    if (defaultAgent) {
      setSelectedAgentProfileId(defaultAgent.id);
    }
  }, [chatMode, agentProfiles, selectedAgentProfileId]);

  // 智能体被删除时清除关联
  useEffect(() => {
    if (
      selectedAgentProfileId &&
      !agentProfiles.some((agent) => agent.id === selectedAgentProfileId)
    ) {
      setSelectedAgentProfileId(null);
      setSessions((prev) =>
        prev.map((session) =>
          session.id === currentSessionId
            ? { ...session, agentProfileId: null, agentName: undefined }
            : session,
        ),
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
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setIsSidebarOpen(false);
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isMobile, isSidebarOpen]);

  // 自动滚动
  useEffect(() => {
    if (isUserScrolledUp && !isStreamingResponse) return;
    const frame = window.requestAnimationFrame(() => {
      scrollToBottom(isStreamingResponse ? 'auto' : 'smooth');
    });
    return () => window.cancelAnimationFrame(frame);
  }, [sessions, currentSessionId, isLoading, isUserScrolledUp, isStreamingResponse, scrollToBottom]);

  // 自动收起错误提示（延长至15秒，给用户充足时间阅读）
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

  const { scrollYProgress } = useScroll({ container: scrollRef });
  const borderColor = useTransform(
    scrollYProgress,
    [0, 0.2, 1],
    ['rgba(255,255,255,0.7)', 'rgba(255,255,255,1)', 'rgba(56,189,248,0.4)'],
  );

  const createNewChat = useCallback(() => {
    setCurrentSessionId(null);
    setChatMode('general');
    setSelectedAgentProfileId(null);
    setArtifact(null);
    if (isMobile) setIsSidebarOpen(false);
  }, [isMobile, setCurrentSessionId]);

  const deleteSession = useCallback(
    (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setSessions((prev) => prev.filter((s) => s.id !== id));
      setCurrentSessionId((prev) => {
        if (prev !== id) return prev;
        setArtifact(null);
        setChatMode('general');
        setSelectedAgentProfileId(null);
        return null;
      });
    },
    [setSessions, setCurrentSessionId],
  );

  const handleOpenArtifact = useCallback((nextArtifact: Artifact) => {
    setArtifact(nextArtifact);
  }, []);

  const handleAgentProfileChange = useCallback((profile: AgentProfile | null) => {
    setSelectedAgentProfileId(profile?.id ?? null);
    if (profile) setChatMode(profile.response_mode);
  }, []);

  return (
    <motion.div
      key="chat"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={onDrop}
      className="flex h-screen bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] text-slate-800 font-sans overflow-hidden selection:bg-zinc-200 selection:text-zinc-900 relative"
    >
      <DragOverlay isDragging={isDragging} />

      {/* 聊天页全局背景装饰 */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.02]" />
      </div>

      {/* 移动端侧边栏遮罩 */}
      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-10"
          />
        )}
      </AnimatePresence>

      <AnimatePresence mode="wait">
        {(isSidebarOpen || (isMobile && isSidebarOpen)) && (!artifact || isMobile || isSidebarOpen) && (
          <motion.div
            initial={{ x: -250, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -250, opacity: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="flex-shrink-0 z-20"
          >
            <Sidebar
              sessions={visibleSessions}
              currentSessionId={currentSessionId}
              onNewChat={createNewChat}
              onSelectSession={(id) => {
                setCurrentSessionId(id);
                if (isMobile) setIsSidebarOpen(false);
              }}
              onDeleteSession={deleteSession}
              onClose={() => setIsSidebarOpen(false)}
              isMobile={isMobile}
              onLoadMore={loadMoreSessions}
              hasMore={hasMoreSessions}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* 侧边栏折叠后的展开按钮 */}
      <AnimatePresence>
        {!isSidebarOpen && !isMobile && (
          <motion.button
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            onClick={() => {
              setIsSidebarOpen(true);
              setIsSidebarHiddenByArtifact(false);
            }}
            className="fixed top-4 left-4 z-50 w-12 h-12 bg-white/80 backdrop-blur-md border border-slate-200 rounded-2xl shadow-sm flex items-center justify-center text-zinc-800 hover:bg-white hover:shadow-md transition-all group focus-visible:ring-2 focus-visible:ring-brand-400/60 focus-visible:ring-offset-2"
            aria-label="展开侧边栏"
          >
            <MascotCool size={24} className="group-hover:scale-110 transition-transform" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* 主聊天区域与制品面板 */}
      <div className="flex-1 flex overflow-hidden relative">
        <main
          id="main-content"
          className={cn(
            "flex flex-col h-full transition-all duration-700 ease-[0.16,1,0.3,1] min-w-0 relative",
            artifact ? "w-[40%] border-r border-slate-200/60" : "w-full",
            isWideConversation && "px-4 lg:px-8 xl:px-10",
          )}
        >
          <ChatMainArea
            currentSession={currentSession}
            isLoading={isLoading}
            isMobile={isMobile}
            isWideConversation={isWideConversation}
            isUserScrolledUp={isUserScrolledUp}
            error={error}
            runStatus={runStatus}
            inputValue={inputValue}
            chatMode={chatMode}
            agentProfiles={agentProfiles}
            selectedAgentProfileId={selectedAgentProfileId}
            showSearch={showSearch}
            searchQuery={searchQuery}
            searchMatchesCount={searchMatches.length}
            searchCurrentIndex={searchCurrentIndex}
            activeMatchId={activeMatchId}
            pendingApprovals={pendingApprovals}
            scrollRef={scrollRef}
            messagesEndRef={messagesEndRef}
            chatInputRef={chatInputRef}
            onScroll={handleScroll}
            onJumpToBottom={handleJumpToBottom}
            onSend={handleSend}
            onStopGeneration={handleStopGeneration}
            onInputChange={setInputValue}
            onModeChange={setChatMode}
            onAgentProfileChange={handleAgentProfileChange}
            onSearchQueryChange={setSearchQuery}
            onSearchPrev={prevMatch}
            onSearchNext={nextMatch}
            onSearchClose={() => {
              setShowSearch(false);
              setSearchQuery('');
            }}
            onToggleSearch={() => setShowSearch(!showSearch)}
            onApprovalDecision={handleApprovalDecision}
            onErrorDismiss={() => setError(null)}
            onSuggestionClick={(text) => setInputValue(text)}
            onOpenArtifact={handleOpenArtifact}
            isModeLocked={!!currentSession && currentSession.messages.length > 0}
          />
        </main>

        {/* 制品预览面板 */}
        <ChatArtifactArea
          artifact={artifact}
          onClose={() => setArtifact(null)}
          borderColor={borderColor}
        />
      </div>
    </motion.div>
  );
};
