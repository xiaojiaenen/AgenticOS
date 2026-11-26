import { useState, useEffect, useRef } from 'react';
import { Session } from '../types';

/**
 * 消息内容指纹：流式期间消息对象引用每帧变化，但搜索匹配只关心文本内容。
 * 用「条数 + 末条文本长度 + 末条文本」做指纹，保证流式新增内容后重算，
 * 又不会因无关状态更新（比如 toolCalls / artifact 变化）反复重算。
 */
export function messageFingerprint(messages: Array<{ text?: string }> | undefined): string {
  const last = messages?.[messages.length - 1]?.text ?? '';
  return `${messages?.length ?? 0}:${last.length}:${last}`;
}

export const useChatSearch = (
  currentSession: Session | undefined,
  scrollToMessageFallback?: (messageId: string) => void,
) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const [searchCurrentIndex, setSearchCurrentIndex] = useState(0);
  const [searchMatches, setSearchMatches] = useState<string[]>([]);
  const highlightTimeoutRef = useRef<number | null>(null);

  // 消息指纹：流式期间 messages 引用每帧变化，但依赖里放整个 session 会在
  // 每次 setSessions 时重算。指纹只随文本内容变化，捕获流式新增。
  const fingerprint = messageFingerprint(currentSession?.messages);

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
    // fingerprint 覆盖流式新增内容；session.id 覆盖会话切换
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQuery, currentSession?.id, fingerprint]);

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
