import React, { useMemo } from 'react';
import { ChatMessage } from './ChatMessage';
import { ChatSuggestions } from './ChatSuggestions';
import { Artifact, Message } from '../../types';
import { getStoredUser } from '../../services/authService';

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
  messagesEndRef: React.RefObject<HTMLDivElement>;
}

export const MessagesList: React.FC<MessagesListProps> = ({
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

  return (
    <div className="space-y-5 pb-4">
      {(displayMessages || currentSession.messages).map((message, idx) => (
        <ChatMessage
          key={message.id}
          message={message}
          index={idx}
          isStreaming={message.id === streamingMessageId}
          wideLayout={wideLayout}
          isAdmin={isAdmin}
          searchQuery={searchQuery}
          activeMatchId={activeMatchId}
          onOpenArtifact={onOpenArtifact}
        />
      ))}
      {showTyping && (
        <div role="status" aria-live="polite" aria-label="AI 正在输入">
          <ChatMessage isTyping={true} index={currentSession.messages.length} wideLayout={wideLayout} />
        </div>
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};
