import { useState, useEffect } from 'react';
import { Session } from '../types';

export const useChatSearch = (currentSession: Session | undefined) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [searchCurrentIndex, setSearchCurrentIndex] = useState(0);
  const [searchMatches, setSearchMatches] = useState<string[]>([]);

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

  const scrollToMatch = (index: number) => {
    const matchId = searchMatches[index - 1];
    if (matchId) {
      const el = document.getElementById(matchId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-4', 'ring-yellow-400/30', 'transition-all');
        setTimeout(() => el.classList.remove('ring-4', 'ring-yellow-400/30'), 2000);
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
