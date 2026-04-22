import React from 'react';
import { motion, AnimatePresence } from 'motion/react';

interface ChatSearchProps {
  showSearch: boolean;
  searchQuery: string;
  setSearchQuery: (val: string) => void;
  searchCurrentIndex: number;
  searchMatchesCount: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}

export const ChatSearch: React.FC<ChatSearchProps> = ({
  showSearch,
  searchQuery,
  setSearchQuery,
  searchCurrentIndex,
  searchMatchesCount,
  onPrev,
  onNext,
  onClose
}) => {
  return (
    <AnimatePresence>
      {showSearch && (
        <motion.div
          initial={{ opacity: 0, y: -40, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -40, scale: 0.95 }}
          className="sticky top-0 z-30 mb-6 flex justify-center w-full"
        >
          <div className="bg-white/80 backdrop-blur-3xl border border-white/60 shadow-[0_8px_30px_rgba(0,0,0,0.08)] rounded-[2rem] px-6 py-2 flex items-center gap-3 w-full max-w-lg focus-within:ring-2 ring-sky-500/20 transition-all">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-slate-400">
              <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
            </svg>
            <input 
              autoFocus
              type="text"
              placeholder="在当前会话中搜索..."
              className="bg-transparent border-none outline-none w-full text-slate-800 placeholder:text-slate-400 font-medium py-2"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            
            {searchQuery && (
              <div className="flex items-center gap-2 pr-2 border-r border-slate-200 mr-2">
                <span className="text-[10px] font-bold bg-slate-100 text-slate-500 px-2.5 py-1 rounded-lg tabular-nums whitespace-nowrap">
                  {searchCurrentIndex} / {searchMatchesCount}
                </span>
                <div className="flex items-center">
                  <button 
                    onClick={onPrev}
                    className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
                    title="上一个"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="rotate-180"><path d="m6 9 6 6 6-6"/></svg>
                  </button>
                  <button 
                    onClick={onNext}
                    className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
                    title="下一个"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="m6 9 6 6 6-6"/></svg>
                  </button>
                </div>
              </div>
            )}

            {searchQuery && (
              <button 
                onClick={() => setSearchQuery('')}
                className="p-1 hover:bg-slate-100 rounded-full text-slate-400"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            )}
            <button 
              onClick={onClose}
              className="text-xs font-bold text-slate-400 hover:text-slate-600 px-3 py-1 bg-slate-50 hover:bg-slate-100 rounded-full transition-colors whitespace-nowrap"
            >
              取消
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
