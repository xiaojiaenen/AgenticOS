/**
 * Chat Context — 将 Chat.tsx 中所有 hook 返回值和派生状态打包为 Context。
 *
 * 子组件通过 useChat() 获取任意值，无需层层传递 props。
 * 仅在值变化时触发子组件重渲染（配合 selector 使用）。
 */
import React, { createContext, useContext, type RefObject } from 'react';
import type { Session, Artifact } from '../types';
import type { AgentProfile } from '../services/agentProfileService';
import type { ChatInputHandle } from '../components/chat/ChatInput';
import type { UserDecision } from '../components/chat/DecisionPanel';
import type { ChatMode } from '../stores/chatStore';

export interface ChatContextValue {
  // ── 会话 ──
  sessions: Session[];
  currentSessionId: string | null;
  currentSession: Session | null;
  visibleSessions: Session[];
  hasMoreSessions: boolean;
  loadMoreSessions: () => void;

  // ── 流式 ──
  isLoading: boolean;
  error: string | null;
  setError: (error: string | null) => void;
  runStatus: { phase: string; label: string };
  pendingDecisions: UserDecision[];
  handleSend: (text: string, files?: File[]) => void;
  handleStopGeneration: () => void;
  handleApprovalDecision: (approvalId: string, status: 'approved' | 'rejected') => void;
  handleDecisionMade: (decisionId: string, answer: string) => void;

  // ── 滚动 ──
  scrollRef: RefObject<HTMLDivElement | null>;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  isUserScrolledUp: boolean;
  scrollToBottom: (behavior?: ScrollBehavior) => void;
  handleJumpToBottom: () => void;
  handleScroll: () => void;

  // ── 搜索 ──
  showSearch: boolean;
  setShowSearch: (show: boolean) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  searchCurrentIndex: number;
  searchMatchesCount: number;
  activeMatchId: string | null;
  prevMatch: () => void;
  nextMatch: () => void;

  // ── Refs ──
  chatInputRef: RefObject<ChatInputHandle | null>;

  // ── 派生 ──
  isStreamingResponse: boolean;
  isWideConversation: boolean;
  pendingApprovals: any[];
  isModeLocked: boolean;
  isAdmin: boolean;

  // ── 操作 ──
  onSuggestionClick: (text: string) => void;
  onOpenArtifact: (artifact: Artifact) => void;
  onAgentProfileChange: (profile: AgentProfile | null) => void;
  deleteSession: (id: string, e?: React.MouseEvent) => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export const ChatContextProvider = ChatContext.Provider;

/**
 * 获取聊天上下文。可传入 selector 做精准订阅：
 *   const isLoading = useChat(s => s.isLoading)
 */
export function useChat(): ChatContextValue;
export function useChat<T>(selector: (ctx: ChatContextValue) => T): T;
export function useChat<T>(selector?: (ctx: ChatContextValue) => T): T | ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error('useChat must be used within ChatContextProvider');
  return selector ? selector(ctx) : ctx;
}
