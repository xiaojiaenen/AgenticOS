/**
 * Chat Context — Chat.tsx 组装的 action/派生值 下发给 ChatMainArea。
 *
 * R3-2 后**数据类状态**（sessions / currentSession / runStatus /
 * pendingDecisions / error）已迁入 zustand chatStore —— ChatMainArea 直接用
 * `useChatStore(selector)` 订阅，这里只保留动作、refs 与派生标志。
 * 子组件通过 useChat() 获取这些值。
 */
import React, { createContext, useContext, type MutableRefObject, type RefObject } from 'react';
import type { Artifact } from '../types';
import type { AgentProfile } from '../services/agentProfileService';
import type { ChatInputHandle } from '../components/chat/ChatInput';
import type { VirtuosoHandle } from 'react-virtuoso';

export interface ChatContextValue {
  // ── 流式（派生标志与动作；数据本体在 chatStore）──
  isLoading: boolean;
  handleSend: (text: string, files?: File[], source?: 'composer' | 'a2ui') => void;
  handleStopGeneration: () => void;
  handleApprovalDecision: (
    approvalId: string,
    status: 'approved' | 'rejected',
    isApiApproval?: boolean,
    allowAll?: boolean,
    modifiedArguments?: Record<string, unknown>,
  ) => Promise<void>;
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
  /** 长会话虚拟化（react-virtuoso）句柄，供搜索跳转 scrollToIndex 回退 */
  virtuosoRef: MutableRefObject<VirtuosoHandle | null>;

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
