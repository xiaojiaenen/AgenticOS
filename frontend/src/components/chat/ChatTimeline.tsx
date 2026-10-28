import React, { useMemo, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Message } from '../../types';

export const ChatTimeline = ({ messages }: { messages: Message[] }) => {
  const [hoveredRound, setHoveredRound] = useState<any>(null);
  const [tooltipTop, setTooltipTop] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);

  const rounds = useMemo(() => {
    const r: Array<{ id: string; index: number; userMessage: Message | null; aiMessage: Message | null }> = [];
    let currentRound: any = null;
    
    messages.forEach((m) => {
      if (m.role === 'user') {
        if (currentRound) r.push(currentRound);
        currentRound = { id: m.id, userMessage: m, aiMessage: null, index: r.length + 1 };
      } else {
        if (currentRound && !currentRound.aiMessage) {
          currentRound.aiMessage = m;
        } else if (!currentRound) {
           currentRound = { id: m.id, userMessage: null, aiMessage: m, index: r.length + 1 };
        }
      }
    });
    if (currentRound) r.push(currentRound);
    return r;
  }, [messages]);

  const maxVisibleRounds = 8;
  const visibleRounds = rounds.length > maxVisibleRounds
    ? [rounds[0], ...rounds.slice(-(maxVisibleRounds - 1))]
    : rounds;
  const hiddenRoundsCount = Math.max(0, rounds.length - visibleRounds.length);

  const scrollToRound = (round: any) => {
    const rowEl = document.getElementById(`msg-${round.id}`);
    if (rowEl) {
      rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  const showTooltipFor = (round: any, el: HTMLElement) => {
    const wrapperRect = wrapperRef.current?.getBoundingClientRect();
    const dotRect = el.getBoundingClientRect();
    if (wrapperRect) {
      setTooltipTop(dotRect.top - wrapperRect.top + dotRect.height / 2);
      setHoveredRound(round);
    }
  };

  // Only show if there are multiple rounds
  if (rounds.length < 2) return null;

  return (
    <motion.div 
      ref={wrapperRef}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      className="absolute right-6 top-1/2 -translate-y-1/2 z-30 flex items-center"
      onMouseLeave={() => setHoveredRound(null)}
    >
      {/* Dynamic Tooltip placed outside the overflow container to prevent clipping */}
      <AnimatePresence>
        {hoveredRound && (
          <motion.div 
            initial={{ opacity: 0, x: 10, scale: 0.95 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 5, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            style={{ top: tooltipTop }}
            className="absolute right-[calc(100%+16px)] -translate-y-1/2 w-64 bg-[var(--surface-1)]/95 backdrop-blur-xl border border-[var(--border-subtle)] shadow-md rounded-2xl p-4 pointer-events-none z-50 flex flex-col gap-2"
          >
            <div className="text-[10px] font-semibold text-[var(--muted-foreground)] uppercase tracking-widest flex items-center gap-1.5 mb-1">
              <div className="w-1.5 h-1.5 bg-[var(--muted-foreground)] rounded-full animate-pulse" />
              第 {hoveredRound.index} 轮对话
            </div>
            
            {hoveredRound.userMessage && (
               <div className="text-xs text-[var(--muted-foreground)] line-clamp-2 leading-relaxed bg-[var(--surface-2)] p-2.5 rounded-xl border border-[var(--border-subtle)]">
                 <span className="font-semibold text-[var(--muted-foreground)] mr-1.5">Q:</span>
                 {hoveredRound.userMessage.text}
               </div>
            )}
            {hoveredRound.aiMessage && (
               <div className="text-xs text-[var(--muted-foreground)] line-clamp-2 leading-relaxed bg-[var(--surface-2)] p-2.5 rounded-xl border border-[var(--border-subtle)]">
                 <span className="font-semibold text-[var(--muted-foreground)] mr-1.5">A:</span>
                 {hoveredRound.aiMessage.text}
               </div>
            )}

            {/* Arrow pointing to dot */}
            <div className="absolute top-1/2 -right-[5px] -translate-y-1/2 w-2.5 h-2.5 bg-[var(--surface-1)] border-t border-r border-[var(--border-subtle)] rotate-45" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bounded round navigator */}
      <div className="bg-[var(--surface-1)] backdrop-blur-xl border border-[var(--border-subtle)] shadow-md rounded-full py-4 px-1.5 flex flex-col items-center gap-2 transition-all group hover:shadow-md hover:bg-[var(--surface-2)]">
        <div className="mb-1 text-[var(--muted-foreground)] opacity-60 group-hover:opacity-100 transition-opacity flex-shrink-0" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>
        </div>
        
        {visibleRounds.map((round, idx) => (
          <React.Fragment key={round.id}>
            {hiddenRoundsCount > 0 && idx === 1 && (
              <div className="flex h-7 w-7 items-center justify-center rounded-full text-[9px] font-semibold text-[var(--muted-foreground)]" aria-hidden="true">
                +{hiddenRoundsCount}
              </div>
            )}
          <button
            type="button"
            onClick={() => scrollToRound(round)}
            onMouseEnter={(e) => showTooltipFor(round, e.currentTarget)}
            onFocus={(e) => showTooltipFor(round, e.currentTarget)}
            onBlur={() => setHoveredRound(null)}
            aria-label={`跳到第 ${round.index} 轮对话`}
            className="w-7 h-7 rounded-full flex items-center justify-center cursor-pointer relative group/item hover:bg-[var(--primary)] hover:shadow-md transition-all flex-shrink-0 focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:outline-none"
          >
            <span className="text-[10px] font-semibold text-[var(--muted-foreground)] group-hover/item:text-[var(--primary-foreground)] transition-colors">
              {round.index}
            </span>
          </button>
          </React.Fragment>
        ))}
        
        <div className="mt-1 text-[var(--muted-foreground)] opacity-60 group-hover:opacity-100 transition-opacity flex-shrink-0" aria-hidden="true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </div>
      </div>
    </motion.div>
  );
};
