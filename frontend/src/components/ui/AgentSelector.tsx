import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { MascotHappy, ChevronDownIcon } from './AnimatedIcons';
import { AgentProfile } from '../../services/agentProfileService';

interface AgentSelectorProps {
  agents: AgentProfile[];
  selectedId: number | null;
  onSelect: (agent: AgentProfile) => void;
  variant?: 'full' | 'compact';
  disabled?: boolean;
  className?: string;
}

export const AgentSelector: React.FC<AgentSelectorProps> = ({
  agents,
  selectedId,
  onSelect,
  variant = 'full',
  disabled = false,
  className,
}) => {
  const [showMenu, setShowMenu] = useState(false);
  const [focusIndex, setFocusIndex] = useState(-1);
  const menuRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const selected = agents.find((a) => a.id === selectedId);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false);
      }
    };
    if (showMenu) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showMenu]);

  useEffect(() => {
    if (showMenu && focusIndex >= 0 && itemRefs.current[focusIndex]) {
      itemRefs.current[focusIndex]?.focus();
    }
  }, [focusIndex, showMenu]);

  useEffect(() => {
    if (!showMenu) setFocusIndex(-1);
  }, [showMenu]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusIndex((prev) => (prev + 1) % agents.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusIndex((prev) => (prev - 1 + agents.length) % agents.length);
      } else if (e.key === 'Enter' && focusIndex >= 0) {
        e.preventDefault();
        const agent = agents[focusIndex];
        if (agent) {
          onSelect(agent);
          setShowMenu(false);
        }
      } else if (e.key === 'Escape') {
        setShowMenu(false);
      }
    },
    [agents, focusIndex, onSelect],
  );

  if (variant === 'compact') {
    return (
      <div className={cn('relative', className)} ref={menuRef}>
        <button
          onClick={() => !disabled && setShowMenu(!showMenu)}
          className={cn(
            'flex items-center justify-center rounded-full p-2.5 text-slate-400 transition-all hover:text-sky-600',
            disabled ? 'cursor-not-allowed opacity-60' : 'border border-transparent hover:border-sky-100 hover:bg-sky-50 active:scale-95',
          )}
          title={disabled ? '对话已开始，无法更改智能体' : '选择智能体'}
          aria-label="选择智能体"
        >
          <div className={cn(
            'flex h-5 w-5 items-center justify-center rounded-md border-2 text-[10px] font-bold',
            selectedId ? 'border-zinc-900 bg-zinc-900 text-white' : 'border-slate-300 text-slate-400',
          )}>
            <MascotHappy size={12} />
          </div>
        </button>

        <AnimatePresence>
          {showMenu && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: -10 }}
              exit={{ opacity: 0, scale: 0.95, y: -20 }}
              className="absolute bottom-full left-0 z-40 mb-4 max-h-[360px] w-64 overflow-y-auto rounded-3xl border border-slate-200/50 bg-white/95 p-2 shadow-2xl ring-1 ring-black/5 backdrop-blur-2xl"
              onKeyDown={handleKeyDown}
            >
              {selected && (
                <div className="mb-2 rounded-2xl border border-sky-100 bg-sky-50/70 px-3 py-2 text-xs font-bold text-sky-700">
                  当前：{selected.name}
                </div>
              )}
              {agents.map((agent, idx) => (
                <button
                  key={agent.id}
                  ref={(el) => { itemRefs.current[idx] = el; }}
                  onClick={() => {
                    onSelect(agent);
                    setShowMenu(false);
                  }}
                  className={cn(
                    'mb-1 flex w-full items-center gap-3 rounded-2xl p-2.5 text-left transition-all last:mb-0 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60',
                    selectedId === agent.id ? 'bg-sky-50/70 ring-1 ring-sky-100' : '',
                  )}
                >
                  <span className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-xl text-sm shadow-sm transition-transform',
                    selectedId === agent.id ? 'bg-sky-500 text-white' : 'bg-slate-100 text-slate-500',
                  )}>
                    <MascotHappy size={20} />
                  </span>
                  <div className="min-w-0 flex flex-col">
                    <span className={cn('truncate text-xs font-bold transition-colors', selectedId === agent.id ? 'text-sky-700' : 'text-slate-700')}>
                      {agent.name}
                    </span>
                    <span className="truncate text-[9px] font-medium text-slate-400">
                      {agent.description || '智能体'}
                    </span>
                  </div>
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    );
  }

  return (
    <div className={cn('relative', className)} ref={menuRef}>
      <button
        onClick={() => setShowMenu(!showMenu)}
        className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-2xl text-sm font-bold transition-all active:scale-95 border border-slate-200/50"
        aria-label="选择智能体"
      >
        <div className={cn(
          'w-6 h-6 rounded-lg flex items-center justify-center transition-all shadow-sm',
          selectedId ? 'bg-sky-500 text-white shadow-glow' : 'bg-slate-200',
        )}>
          <MascotHappy size={14} />
        </div>
        {selected?.name || '选择智能体'}
        <ChevronDownIcon size={14} className={cn('transition-transform', showMenu && 'rotate-180')} />
      </button>

      <AnimatePresence>
        {showMenu && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="absolute bottom-full left-0 mb-2 max-h-64 w-56 overflow-y-auto bg-white/95 backdrop-blur-xl border border-slate-200/50 rounded-3xl shadow-2xl z-40 p-2"
            onKeyDown={handleKeyDown}
          >
            {agents.map((agent, idx) => (
              <button
                key={agent.id}
                ref={(el) => { itemRefs.current[idx] = el; }}
                onClick={() => {
                  onSelect(agent);
                  setShowMenu(false);
                }}
                className={cn(
                  'mb-1 flex w-full items-center gap-3 rounded-2xl p-2.5 text-left transition-all last:mb-0 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60',
                  selectedId === agent.id ? 'bg-sky-50/70 ring-1 ring-sky-100' : '',
                )}
              >
                <span className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-xl text-sm shadow-sm transition-transform',
                  selectedId === agent.id ? 'bg-sky-500 text-white' : 'bg-slate-100 text-slate-500',
                )}>
                  <MascotHappy size={20} />
                </span>
                <div className="min-w-0 flex flex-col">
                  <span className={cn('truncate text-xs font-bold transition-colors', selectedId === agent.id ? 'text-sky-700' : 'text-slate-700')}>
                    {agent.name}
                  </span>
                  <span className="truncate text-[9px] font-medium text-slate-400">
                    {agent.description || '智能体'}
                  </span>
                </div>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
