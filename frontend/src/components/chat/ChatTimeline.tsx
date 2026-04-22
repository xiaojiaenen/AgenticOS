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

  const scrollToRound = (round: any) => {
    const rowEl = document.getElementById(`msg-${round.id}`);
    const bubbleEl = document.getElementById(`bubble-${round.id}`);
    
    if (rowEl) {
      rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    
      if (bubbleEl) {
        bubbleEl.classList.add('scale-[1.03]', 'shadow-[0_0_24px_rgba(24,24,27,0.15)]', 'ring-2', 'ring-zinc-900');
        setTimeout(() => {
          bubbleEl.classList.remove('scale-[1.03]', 'shadow-[0_0_24px_rgba(24,24,27,0.15)]', 'ring-2', 'ring-zinc-900');
        }, 1500);
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
            className="absolute right-[calc(100%+16px)] -translate-y-1/2 w-64 bg-white/95 backdrop-blur-xl border border-slate-200/60 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.15)] rounded-2xl p-4 pointer-events-none z-50 flex flex-col gap-2"
          >
            <div className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest flex items-center gap-1.5 mb-1">
              <div className="w-1.5 h-1.5 bg-zinc-400 rounded-full shadow-[0_0_8px_rgba(24,24,27,0.4)] animate-pulse" />
              第 {hoveredRound.index} 轮对话
            </div>
            
            {hoveredRound.userMessage && (
               <div className="text-xs text-slate-600 line-clamp-2 leading-relaxed bg-slate-50 p-2.5 rounded-xl border border-slate-100">
                 <span className="font-bold text-slate-400 mr-1.5">Q:</span>
                 {hoveredRound.userMessage.text}
               </div>
            )}
            {hoveredRound.aiMessage && (
               <div className="text-xs text-slate-600 line-clamp-2 leading-relaxed bg-slate-100/80 p-2.5 rounded-xl border border-slate-200/50">
                 <span className="font-bold text-zinc-700 mr-1.5">A:</span>
                 {hoveredRound.aiMessage.text}
               </div>
            )}

            {/* Arrow pointing to dot */}
            <div className="absolute top-1/2 -right-[5px] -translate-y-1/2 w-2.5 h-2.5 bg-white border-t border-r border-slate-200/60 rotate-45" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main scrollable dots container */}
      <div className="bg-white/80 backdrop-blur-xl border border-white/60 shadow-[0_8px_32px_-12px_rgba(0,0,0,0.1)] rounded-full py-4 px-1.5 flex flex-col items-center gap-2 max-h-[60vh] overflow-y-auto [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-slate-200 [&::-webkit-scrollbar-thumb]:rounded-full hover:[&::-webkit-scrollbar-thumb]:bg-slate-300 transition-all group hover:shadow-md hover:bg-white/95">
        <div className="mb-1 text-slate-300 opacity-60 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>
        </div>
        
        {rounds.map((round) => (
          <div 
            key={round.id} 
            onClick={() => scrollToRound(round)}
            onMouseEnter={(e) => {
              const wrapperRect = wrapperRef.current?.getBoundingClientRect();
              const dotRect = e.currentTarget.getBoundingClientRect();
              if (wrapperRect) {
                setTooltipTop(dotRect.top - wrapperRect.top + dotRect.height / 2);
                setHoveredRound(round);
              }
            }}
            className="w-7 h-7 rounded-full flex items-center justify-center cursor-pointer relative group/item hover:bg-zinc-800 hover:shadow-md transition-all flex-shrink-0"
          >
            <span className="text-[10px] font-bold text-slate-400 group-hover/item:text-white transition-colors">
              {round.index}
            </span>
          </div>
        ))}
        
        <div className="mt-1 text-slate-300 opacity-60 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
        </div>
      </div>
    </motion.div>
  );
};
