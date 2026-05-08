import { useState, useRef, useCallback } from 'react';

export function useChatScroll() {
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior,
    });
  }, []);

  const handleJumpToBottom = useCallback(() => {
    setIsUserScrolledUp(false);
    scrollToBottom('smooth');
  }, [scrollToBottom]);

  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setIsUserScrolledUp(scrollHeight - scrollTop - clientHeight > 120);
  }, []);

  return {
    scrollRef,
    messagesEndRef,
    isUserScrolledUp,
    setIsUserScrolledUp,
    scrollToBottom,
    handleJumpToBottom,
    handleScroll,
  };
}
