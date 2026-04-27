import React from 'react';
import { ChatMessage } from './ChatMessage';
import { ChatSuggestions } from './ChatSuggestions';
import { Message } from '../../types';

interface MessagesListProps {
  currentSession: { messages: Message[] } | undefined;
  isLoading: boolean;
  wideLayout?: boolean;
  searchQuery: string;
  activeMatchId: string | null;
  onSend: (text: string) => void;
  onSuggestionClick: (text: string) => void;
  onOpenArtifact: (code: string, language: 'html' | 'svg' | 'pptdeck') => void;
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
  if (!currentSession) {
    return <ChatSuggestions onSelect={onSuggestionClick} />;
  }

  const lastMessage = currentSession.messages[currentSession.messages.length - 1];
  const showTyping = isLoading && !(lastMessage?.role === 'model');
  const streamingMessageId = isLoading && lastMessage?.role === 'model' ? lastMessage.id : null;

  return (
    <div className="space-y-8 pb-4">
      {currentSession.messages.map((message, idx) => (
        <ChatMessage 
          key={message.id} 
          message={message} 
          index={idx}
          isStreaming={message.id === streamingMessageId}
          wideLayout={wideLayout}
          searchQuery={searchQuery}
          activeMatchId={activeMatchId}
          onOpenArtifact={onOpenArtifact}
        />
      ))}
      {showTyping && (
        <ChatMessage isTyping={true} index={currentSession.messages.length} wideLayout={wideLayout} />
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};
