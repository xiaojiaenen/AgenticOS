import React, { useEffect, useMemo, useRef } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { ChatMessage } from './ChatMessage';
import { ChatSuggestions } from './ChatSuggestions';
import { Artifact, Message } from '../../types';
import { getStoredUser } from '../../services/authService';

const sanitizedCache = new WeakMap<Message, Message>();

/**
 * M6-A7：超过该阈值才启用虚拟化。
 *
 * 阈值以下走原来的平铺渲染 —— 虚拟化本身有测量开销，短会话用它是净损失，
 * 而且会改变 DOM 结构（搜索高亮的 scrollIntoView 目标、动效表现都可能受影响）。
 */
const VIRTUALIZATION_THRESHOLD = 200;

function sanitizeForNonAdmin(message: Message): Message {
  if (sanitizedCache.has(message)) return sanitizedCache.get(message)!;
  const sanitized: Message = {
    ...message,
    reasoningText: undefined,
    // 保留工具名称和状态，隐藏参数和结果
    toolCalls: message.toolCalls?.map((tc) => ({
      id: tc.id,
      name: tc.name,
      status: tc.status,
      // 不暴露参数、结果、approvalId 等细节
    })),
  };
  sanitizedCache.set(message, sanitized);
  return sanitized;
}

interface MessagesListProps {
  currentSession: { messages: Message[] } | undefined;
  isLoading: boolean;
  wideLayout?: boolean;
  searchQuery: string;
  activeMatchId: string | null;
  onSend: (text: string) => void;
  onSuggestionClick: (text: string) => void;
  onOpenArtifact: (artifact: Artifact) => void;
  messagesEndRef: React.RefObject<HTMLDivElement>;
}

export const MessagesList = React.memo<MessagesListProps>(({
  currentSession,
  isLoading,
  wideLayout = false,
  searchQuery,
  activeMatchId,
  onSend,
  onSuggestionClick,
  onOpenArtifact,
  messagesEndRef
}) => {
  const isAdmin = getStoredUser()?.role === 'admin';
  const displayMessages = useMemo(() => {
    if (isAdmin || !currentSession) return currentSession?.messages;
    return currentSession.messages.map((message) => sanitizeForNonAdmin(message));
  }, [currentSession?.messages, isAdmin]);

  if (!currentSession) {
    return <ChatSuggestions onSelect={onSuggestionClick} />;
  }

  const lastMessage = currentSession.messages[currentSession.messages.length - 1];
  const showTyping = isLoading && !(lastMessage?.role === 'model');
  const streamingMessageId = isLoading && lastMessage?.role === 'model' ? lastMessage.id : null;

  const renderMessage = (
    message: Message,
    idx: number,
    key: string | number = message.id
  ) => (
    <ChatMessage
      key={key}
      message={message}
      index={idx}
      isStreaming={message.id === streamingMessageId}
      wideLayout={wideLayout}
      isAdmin={isAdmin}
      searchQuery={searchQuery}
      activeMatchId={activeMatchId}
      onOpenArtifact={onOpenArtifact}
    />
  );

  const messages = displayMessages || currentSession.messages;
  const typingIndicator = showTyping ? (
    <div role="status" aria-live="polite" aria-label="AI 正在输入">
      <ChatMessage isTyping={true} index={currentSession.messages.length} wideLayout={wideLayout} />
    </div>
  ) : null;

  // 未达阈值：保持原有平铺渲染，行为与优化前完全一致
  if (messages.length <= VIRTUALIZATION_THRESHOLD) {
    return (
      <div className="space-y-5 pb-4">
        {messages.map((message, idx) => renderMessage(message, idx))}
        {typingIndicator}
        <div ref={messagesEndRef} />
      </div>
    );
  }

  return (
    <VirtualizedMessages
      messages={messages}
      wideLayout={wideLayout}
      isAdmin={isAdmin}
      searchQuery={searchQuery}
      activeMatchId={activeMatchId}
      onOpenArtifact={onOpenArtifact}
      renderMessage={renderMessage}
      typingIndicator={typingIndicator}
      messagesEndRef={messagesEndRef}
    />
  );
});

interface VirtualizedMessagesProps {
  messages: Message[];
  wideLayout: boolean;
  isAdmin: boolean;
  searchQuery: string;
  activeMatchId: string | null;
  onOpenArtifact: (artifact: Artifact) => void;
  renderMessage: (message: Message, idx: number, key?: string | number) => React.ReactElement;
  typingIndicator: React.ReactNode;
  messagesEndRef: React.RefObject<HTMLDivElement>;
}

/**
 * 长会话虚拟化列表。
 *
 * 与 useChatScroll 协议的衔接：
 * - 滚动容器仍是 ChatMainArea 里那个 `overflow-y-auto` 的 div，虚拟列表
 *   不接管滚动（`useWindowScroll` 关闭），所以 handleScroll / scrollToBottom /
 *   `useScroll({ container: scrollRef })` 全部照旧工作。
 * - followOutput 负责流式输出时保持贴底；用户手动上滚时 Virtuoso 会自动
 *   停止跟随，与原先 `isUserScrolledUp` 的行为一致。
 */
const VirtualizedMessages = React.memo<VirtualizedMessagesProps>(({
  messages,
  searchQuery,
  activeMatchId,
  renderMessage,
  typingIndicator,
  messagesEndRef,
}) => {
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  // 搜索跳转：虚拟化后目标消息可能未挂载，scrollIntoView 找不到 DOM，
  // 这里先按索引滚过去，等它渲染出来再由 ChatMessage 自己完成高亮。
  const activeIndex = useMemo(
    () => (activeMatchId ? messages.findIndex((m) => m.id === activeMatchId) : -1),
    [messages, activeMatchId]
  );

  useEffect(() => {
    if (activeIndex < 0) return;
    virtuosoRef.current?.scrollToIndex({
      index: activeIndex,
      align: 'center',
      behavior: 'smooth',
    });
  }, [activeIndex]);

  return (
    <Virtuoso
      ref={virtuosoRef}
      // 外层 div 已经是滚动容器，这里不要让 Virtuoso 再套一层滚动
      useWindowScroll={false}
      style={{ height: '100%' }}
      totalCount={messages.length}
      // 保持贴底：仅当用户本来就在底部时才跟随，上滚阅读时不抢滚动
      followOutput={(isAtBottom) => (isAtBottom ? 'smooth' : false)}
      itemContent={(_index, message) => renderMessage(message, _index)}
      computeItemKey={(_index, message) => message.id}
      // 预渲染窗口外的少量内容，避免快速滚动出现白屏
      increaseViewportBy={{ top: 600, bottom: 1200 }}
      components={{
        List: ({ children, ref, ...props }) => (
          <div {...props} ref={ref as React.Ref<HTMLDivElement>} className="space-y-5 pb-4">
            {children}
          </div>
        ),
        Footer: () => (
          <>
            {typingIndicator}
            <div ref={messagesEndRef} />
          </>
        ),
      }}
    />
  );
});