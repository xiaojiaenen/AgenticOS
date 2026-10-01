import { useState, useEffect, useRef } from 'react';
import { Session } from '../types';

export const useChatSearch = (
  currentSession: Session | undefined,
  scrollToMessageFallback?: (messageId: string) => void,
) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [searchCurrentIndex, setSearchCurrentIndex] = useState(0);
  const [searchMatches, setSearchMatches] = useState<string[]>([]);
  const highlightTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    if (!searchQuery.trim() || !currentSession) {
      setSearchMatches([]);
      setSearchCurrentIndex(0);
      return;
    }

    const matches: string[] = [];
    currentSession.messages.forEach(m => {
      const text = m.text.toLowerCase();
      const query = searchQuery.toLowerCase();
      let pos = text.indexOf(query);
      let occurrenceCount = 0;
      while (pos !== -1) {
        matches.push(`mark-${m.id}-${occurrenceCount}`);
        occurrenceCount++;
        pos = text.indexOf(query, pos + 1);
      }
    });
    
    setSearchMatches(matches);
    setSearchCurrentIndex(matches.length > 0 ? 1 : 0);
  }, [searchQuery, currentSession?.id]);

  useEffect(() => {
    return () => {
      if (highlightTimeoutRef.current !== null) {
        clearTimeout(highlightTimeoutRef.current);
      }
    };
  }, []);

  const scrollToMatch = (index: number) => {
    const matchId = searchMatches[index - 1];
    if (matchId) {
      const highlight = (el: HTMLElement) => {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-4', 'ring-yellow-200', 'transition-all');
        if (highlightTimeoutRef.current !== null) clearTimeout(highlightTimeoutRef.current);
        highlightTimeoutRef.current = window.setTimeout(() => el.classList.remove('ring-4', 'ring-yellow-200'), 2000);
      };
      const el = document.getElementById(matchId);
      if (el) {
        highlight(el);
      } else if (scrollToMessageFallback) {
        // 虚拟化模式下目标消息可能尚未渲染进 DOM：matchId 形如 mark-{messageId}-{n}
        const parts = matchId.split('-');
        parts.pop();
        parts.shift();
        scrollToMessageFallback(parts.join('-'));
        // 等虚拟列表渲染出该项后再高亮
        window.setTimeout(() => {
          const delayed = document.getElementById(matchId);
          if (delayed) highlight(delayed);
        }, 300);
      }
    }
  };

  const nextMatch = () => {
    if (searchMatches.length === 0) return;
    const nextIdx = searchCurrentIndex >= searchMatches.length ? 1 : searchCurrentIndex + 1;
    setSearchCurrentIndex(nextIdx);
    scrollToMatch(nextIdx);
  };

  const prevMatch = () => {
    if (searchMatches.length === 0) return;
    const prevIdx = searchCurrentIndex <= 1 ? searchMatches.length : searchCurrentIndex - 1;
    setSearchCurrentIndex(prevIdx);
    scrollToMatch(prevIdx);
  };

  return {
    searchQuery,
    setSearchQuery,
    showSearch,
    setShowSearch,
    searchCurrentIndex,
    searchMatches,
    nextMatch,
    prevMatch,
    activeMatchId: searchMatches[searchCurrentIndex - 1] || null
  };
};
