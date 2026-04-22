import React from 'react';
import { ChatMessage } from './ChatMessage';
import { ChatSuggestions } from './ChatSuggestions';
import { Message } from '../../types';

interface MessagesListProps {
  currentSession: { messages: Message[] } | undefined;
  isLoading: boolean;
  searchQuery: string;
  activeMatchId: string | null;
  onSend: (text: string) => void;
  onSuggestionClick: (text: string) => void;
  onOpenArtifact: (code: string, language: string) => void;
  messagesEndRef: React.RefObject<HTMLDivElement>;
}

export const MessagesList: React.FC<MessagesListProps> = ({
  currentSession,
  isLoading,
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
          searchQuery={searchQuery}
          activeMatchId={activeMatchId}
          onOpenArtifact={onOpenArtifact}
        />
      ))}
      {showTyping && (
        <ChatMessage isTyping={true} index={currentSession.messages.length} />
      )}
      <div ref={messagesEndRef} />
    </div>
  );
};
