import React, { useMemo, useCallback } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
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
    toolCalls: message.toolCalls?.map((tc) => ({
      id: tc.id,
      name: tc.name,
      status: tc.status,
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

  const messages = displayMessages || currentSession?.messages || [];
  const lastMessage = currentSession?.messages[currentSession.messages.length - 1];
  const showTyping = isLoading && !(lastMessage?.role === 'model');
  const streamingMessageId = isLoading && lastMessage?.role === 'model' ? lastMessage.id : null;

  // Virtuoso item renderer
  const itemContent = useCallback((index: number) => {
    if (index === messages.length) {
      // Typing indicator or bottom sentinel
      if (showTyping) {
        return (
          <div role="status" aria-live="polite" aria-label="AI 正在输入">
            <ChatMessage isTyping={true} index={messages.length} wideLayout={wideLayout} />
          </div>
        );
      }
      return <div ref={messagesEndRef} />;
    }
    const message = messages[index];
    return (
      <ChatMessage
        key={message.id}
        message={message}
        index={index}
        isStreaming={message.id === streamingMessageId}
        wideLayout={wideLayout}
        isAdmin={isAdmin}
        searchQuery={searchQuery}
        activeMatchId={activeMatchId}
        onOpenArtifact={onOpenArtifact}
      />
    );
  }, [messages, streamingMessageId, wideLayout, isAdmin, searchQuery, activeMatchId, onOpenArtifact, showTyping, messagesEndRef]);

  if (!currentSession) {
    return <ChatSuggestions onSelect={onSuggestionClick} />;
  }

  // Total items = messages + optional typing indicator / bottom sentinel
  const totalCount = messages.length + 1;

  return (
    <Virtuoso
      ref={messagesEndRef as any}
      data={messages}
      totalCount={totalCount}
      followOutput="smooth"
      atBottomStateChange={(atBottom) => {
        // Keep scroll behavior consistent with existing useChatScroll
        if (atBottom && messagesEndRef.current) {
          messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
      }}
      increaseViewportBy={{ top: 400, bottom: 400 }}
      className="flex-1"
      style={{ overflow: 'hidden' }}
      itemContent={itemContent}
      components={{
        // Remove default Virtuoso list wrapper styling to keep existing layout
        List: React.forwardRef<HTMLDivElement, { style?: React.CSSProperties; children?: React.ReactNode }>(
          ({ style, children, ...props }, ref) => (
            <div ref={ref} style={{ ...style, paddingBottom: '1rem' }} className="space-y-5" {...props}>
              {children}
            </div>
          ),
        ),
      }}
    />
  );
};
