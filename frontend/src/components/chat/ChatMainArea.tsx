import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChatTimeline } from './ChatTimeline';
import { ChatSearch } from './ChatSearch';
import { MessagesList } from './MessagesList';
import { PendingApprovalPanel } from './PendingApprovalPanel';
import { ChatInput, ChatInputHandle } from './ChatInput';
import { MascotState } from '../ui/MascotState';
import { MascotCompanion } from '../ui/MascotCompanion';
import { AlertCircleIcon, ChevronDownIcon } from '../ui/AnimatedIcons';
import { Artifact, Session } from '../../types';
import { AgentProfile } from '../../services/agentProfileService';
import { cn } from '../../lib/utils';

interface ChatMainAreaProps {
  currentSession: Session | null;
  isLoading: boolean;
  isMobile: boolean;
  isWideConversation: boolean;
  isUserScrolledUp: boolean;
  error: string | null;
  runStatus: { phase: string; label: string };
  inputValue: string;
  chatMode: 'general' | 'ppt' | 'website';
  agentProfiles: AgentProfile[];
  selectedAgentProfileId: number | null;
  showSearch: boolean;
  searchQuery: string;
  searchMatchesCount: number;
  searchCurrentIndex: number;
  activeMatchId: string | null;
  pendingApprovals: any[];
  scrollRef: React.RefObject<HTMLDivElement>;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  chatInputRef: React.RefObject<ChatInputHandle>;
  onScroll: () => void;
  onJumpToBottom: () => void;
  onSend: (text: string, files?: File[]) => void;
  onStopGeneration: () => void;
  onInputChange: (value: string) => void;
  onModeChange: (mode: 'general' | 'ppt' | 'website') => void;
  onAgentProfileChange: (profile: AgentProfile | null) => void;
  onSearchQueryChange: (query: string) => void;
  onSearchPrev: () => void;
  onSearchNext: () => void;
  onSearchClose: () => void;
  onToggleSearch: () => void;
  onApprovalDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
  onErrorDismiss: () => void;
  onSuggestionClick: (text: string) => void;
  onOpenArtifact: (artifact: Artifact) => void;
  isModeLocked: boolean;
}

export const ChatMainArea = React.memo(({
  currentSession,
  isLoading,
  isMobile,
  isWideConversation,
  isUserScrolledUp,
  error,
  runStatus,
  inputValue,
  chatMode,
  agentProfiles,
  selectedAgentProfileId,
  showSearch,
  searchQuery,
  searchMatchesCount,
  searchCurrentIndex,
  activeMatchId,
  pendingApprovals,
  scrollRef,
  messagesEndRef,
  chatInputRef,
  onScroll,
  onJumpToBottom,
  onSend,
  onStopGeneration,
  onInputChange,
  onModeChange,
  onAgentProfileChange,
  onSearchQueryChange,
  onSearchPrev,
  onSearchNext,
  onSearchClose,
  onToggleSearch,
  onApprovalDecision,
  onErrorDismiss,
  onSuggestionClick,
  onOpenArtifact,
  isModeLocked,
}: ChatMainAreaProps) => (
  <>
    {/* 时间线导航 */}
    <AnimatePresence>
      {!isMobile && currentSession?.messages && (
        <ChatTimeline messages={currentSession.messages} />
      )}
    </AnimatePresence>

    {/* 消息区域 + 精灵叠加层 */}
    <div className="flex-1 relative overflow-hidden">
      {/* 动态陪伴精灵 — 固定在消息区域中心不随滚动移动 */}
      <AnimatePresence>
        {isLoading && runStatus.phase !== 'streaming' && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
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
        ref={scrollRef as React.RefObject<HTMLDivElement>}
        onScroll={onScroll}
        className={cn(
          "h-full overflow-y-auto custom-scrollbar pr-16",
          isWideConversation ? "px-6 py-8 md:px-10 lg:px-14 xl:px-16" : "p-4 md:p-8"
        )}
      >

      {/* 搜索浮层 */}
      <ChatSearch
        showSearch={showSearch}
        searchQuery={searchQuery}
        setSearchQuery={onSearchQueryChange}
        searchCurrentIndex={searchCurrentIndex}
        searchMatchesCount={searchMatchesCount}
        onPrev={onSearchPrev}
        onNext={onSearchNext}
        onClose={onSearchClose}
      />

      {/* 右下角浮动工具栏 */}
      <div className="fixed right-6 bottom-10 flex flex-col gap-3 z-40">
        <button
          onClick={onToggleSearch}
          className={cn(
            "w-12 h-12 rounded-2xl flex items-center justify-center transition-all shadow-lg backdrop-blur-md border hover:scale-105 active:scale-95",
            showSearch
              ? "bg-zinc-900 text-white border-zinc-800"
              : "bg-white/80 text-slate-600 border-white/60 hover:bg-white"
          )}
          aria-label="切换搜索"
        >
          <div className={cn("transition-transform duration-500", showSearch && "rotate-90")}>
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
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="absolute top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl shadow-lg"
          >
            <AlertCircleIcon size={18} />
            <span className="text-sm font-medium">{error}</span>
            <button onClick={onErrorDismiss} className="ml-2 text-red-500 hover:text-red-700" aria-label="关闭错误提示">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <MessagesList
        currentSession={currentSession}
        isLoading={isLoading}
        wideLayout={isWideConversation}
        searchQuery={searchQuery}
        activeMatchId={activeMatchId}
        onSend={onSend}
        onSuggestionClick={onSuggestionClick}
        onOpenArtifact={onOpenArtifact}
        messagesEndRef={messagesEndRef as React.RefObject<HTMLDivElement>}
      />
    </div>{/* end scrollable */}

    </div>{/* end message-area-wrapper */}

    {/* 输入区域 */}
    <div className="p-4 md:p-6 bg-transparent flex-shrink-0 relative">
      <AnimatePresence>
        {isUserScrolledUp && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute -top-4 left-0 right-0 flex justify-center z-30"
          >
            <button
              onClick={onJumpToBottom}
              className="flex items-center gap-2 px-6 py-1.5 bg-zinc-900/90 backdrop-blur-2xl text-white rounded-full text-[10px] font-black uppercase tracking-[0.2em] shadow-2xl border border-white/10 hover:bg-zinc-800 transition-all active:scale-95 group"
            >
              <span>回到底部</span>
              <ChevronDownIcon size={12} className="group-hover:translate-y-0.5 transition-transform" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <div className={cn("mx-auto", isWideConversation ? "max-w-[92rem] px-8" : "max-w-4xl")}>
        <PendingApprovalPanel
          approvals={pendingApprovals}
          onDecision={onApprovalDecision}
        />
        <ChatInput
          ref={chatInputRef}
          value={inputValue}
          onChange={onInputChange}
          onSend={(text, files) => onSend(text, files)}
          onStop={onStopGeneration}
          isLoading={isLoading}
          chatMode={chatMode}
          setChatMode={onModeChange}
          agentProfiles={agentProfiles}
          selectedAgentProfileId={selectedAgentProfileId}
          onAgentProfileChange={onAgentProfileChange}
          isModeLocked={isModeLocked}
        />
        <div className="mt-3 flex min-h-9 items-center justify-center gap-2 text-xs font-medium text-slate-400">
          {isLoading ? (
            <MascotState
              phase={
                runStatus.phase === 'generating_ppt' || runStatus.phase === 'rendering_ppt'
                  ? 'thinking'
                  : runStatus.phase === 'streaming'
                    ? 'streaming'
                    : runStatus.phase === 'error'
                      ? 'error'
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
  </>
));
