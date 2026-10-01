import React, { useMemo } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { ChatMessage } from './ChatMessage';
import { ChatSuggestions } from './ChatSuggestions';
import { Artifact, Message } from '../../types';
import { getStoredUser } from '../../services/authService';

// 超过该阈值的消息列表启用 react-virtuoso 虚拟化：长会话逐条渲染
// ReactMarkdown 成本高；短列表走原路径，避免虚拟化带来的行为差异
const VIRTUALIZE_THRESHOLD = 50;

// 虚拟化模式的合成尾项：承载打字指示器与 messagesEndRef
const FOOTER_ITEM = { id: '__messages_footer__' } as unknown as Message;

const sanitizedCache = new WeakMap<Message, Message>();

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
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  /** 虚拟化模式下的滚动容器（ChatMainArea 的 scrollRef 绑定节点） */
  scrollParent?: HTMLDivElement | null;
  /** 虚拟化模式下暴露 Virtuoso 句柄，供搜索跳转 scrollToIndex 回退 */
  virtuosoRef?: React.MutableRefObject<VirtuosoHandle | null>;
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
  messagesEndRef,
  scrollParent,
  virtuosoRef,
}) => {
  const isAdmin = getStoredUser()?.role === 'admin';
  const messages = currentSession?.messages;
  const displayMessages = useMemo(() => {
    if (isAdmin || !messages) return messages;
    return messages.map((message) => sanitizeForNonAdmin(message));
  }, [messages, isAdmin]);

  if (!currentSession || !messages) {
    return <ChatSuggestions onSelect={onSuggestionClick} />;
  }

  const lastMessage = messages[messages.length - 1];
  const showTyping = isLoading && !(lastMessage?.role === 'model');
  const streamingMessageId = isLoading && lastMessage?.role === 'model' ? lastMessage.id : null;

  const renderMessage = (message: Message, idx: number) => (
    <ChatMessage
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

  const footer = (
    <>
      {showTyping && (
        <div role="status" aria-live="polite" aria-label="AI 正在输入">
          <ChatMessage isTyping={true} index={messages.length} wideLayout={wideLayout} />
        </div>
      )}
      <div ref={messagesEndRef} />
    </>
  );

  // 长会话：虚拟化渲染（customScrollParent 挂在外层滚动容器上，
  // Chat.tsx 的 scrollToBottom 仍直接滚动该容器，行为不变）。
  // 打字指示器/end 标记作为合成尾项渲染，避免 components.Footer 内联
  // 组件在流式期间每帧重挂载。
  if (scrollParent && virtuosoRef && messages.length > VIRTUALIZE_THRESHOLD) {
    const base = displayMessages ?? messages;
    const items = [...base, FOOTER_ITEM];
    return (
      <Virtuoso
        ref={(v) => { virtuosoRef.current = v; }}
        customScrollParent={scrollParent}
        data={items}
        computeItemKey={(_, message) => message.id}
        initialTopMostItemIndex={items.length - 1}
        increaseViewportBy={{ top: 800, bottom: 1200 }}
        itemContent={(idx, message) => (
          message.id === FOOTER_ITEM.id
            ? <div className="pt-1 pb-4">{footer}</div>
            : <div className="pb-5">{renderMessage(message, idx)}</div>
        )}
      />
    );
  }

  return (
    <div className="space-y-5 pb-4">
      {(displayMessages ?? messages).map((message, idx) => (
        <React.Fragment key={message.id}>
          {renderMessage(message, idx)}
        </React.Fragment>
      ))}
      {footer}
    </div>
  );
});
