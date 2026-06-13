import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { MascotHappy, MascotGeneral, MascotPPT, MascotWebsite, MascotVideo, MascotEmail, MascotBigData, ChevronDownIcon } from './AnimatedIcons';
import { AgentProfile } from '../../services/agentProfileService';

// 不同模式的小精灵组件和颜色
const MODE_STYLES: Record<string, { Mascot: React.FC<{ size?: number; className?: string }>; bg: string; ring: string; text: string; selectedBg: string }> = {
  general: { Mascot: MascotGeneral, bg: 'bg-sky-500',    ring: 'ring-sky-100',    text: 'text-sky-700',    selectedBg: 'bg-sky-100/70' },
  ppt:     { Mascot: MascotPPT,     bg: 'bg-violet-500',  ring: 'ring-violet-100', text: 'text-violet-700', selectedBg: 'bg-violet-100/70' },
  website: { Mascot: MascotWebsite, bg: 'bg-emerald-500', ring: 'ring-emerald-100',text: 'text-emerald-700',selectedBg: 'bg-emerald-100/70' },
  video:   { Mascot: MascotVideo,   bg: 'bg-purple-500',  ring: 'ring-purple-100', text: 'text-purple-700', selectedBg: 'bg-purple-100/70' },
  email:   { Mascot: MascotEmail,   bg: 'bg-blue-500',    ring: 'ring-blue-100',   text: 'text-blue-700',   selectedBg: 'bg-blue-100/70' },
  bigdata: { Mascot: MascotBigData, bg: 'bg-orange-500',  ring: 'ring-orange-100', text: 'text-orange-700', selectedBg: 'bg-orange-100/70' },
};

function getModeStyle(mode?: string) {
  return MODE_STYLES[mode || ''] || MODE_STYLES.general;
}

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
          aria-expanded={showMenu}
          aria-haspopup="listbox"
          aria-label="选择智能体"
        >
          <div className={cn(
            'flex h-5 w-5 items-center justify-center rounded-md border-2 text-[10px] font-bold',
            selectedId ? `${getModeStyle(selected?.response_mode).bg} border-transparent text-white` : 'border-slate-300 text-slate-400',
          )}>
            {(() => { const M = selected ? getModeStyle(selected.response_mode).Mascot : null; return M ? <M size={12} /> : <MascotHappy size={12} />; })()}
          </div>
        </button>

        <AnimatePresence>
          {showMenu && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: -10 }}
              exit={{ opacity: 0, scale: 0.95, y: -20 }}
              className="absolute bottom-full left-0 z-40 mb-4 max-h-[360px] w-64 overflow-y-auto rounded-3xl border border-white/60 bg-white/95 p-2 shadow-2xl ring-1 ring-black/5 backdrop-blur-2xl"
              role="listbox"
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
                  role="option"
                  aria-selected={selectedId === agent.id}
                  className={cn(
                    'mb-1 flex w-full items-center gap-3 rounded-2xl p-2.5 text-left transition-all last:mb-0 hover:bg-sky-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60',
                    selectedId === agent.id ? `${getModeStyle(agent.response_mode).selectedBg} ring-1 ${getModeStyle(agent.response_mode).ring}` : '',
                  )}
                >
                  <span className={cn(
                    'flex h-8 w-8 items-center justify-center rounded-xl text-sm shadow-sm transition-transform',
                    selectedId === agent.id ? `${getModeStyle(agent.response_mode).bg} text-white` : 'bg-sky-50 text-slate-500',
                  )}>
                    {getModeStyle(agent.response_mode).Mascot ? React.createElement(getModeStyle(agent.response_mode).Mascot, { size: 20 }) : <MascotHappy size={20} />}
                  </span>
                  <div className="min-w-0 flex flex-col">
                    <span className={cn('truncate text-xs font-bold transition-colors', selectedId === agent.id ? getModeStyle(agent.response_mode).text : 'text-slate-700')}>
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
        onClick={() => !disabled && setShowMenu(!showMenu)}
        disabled={disabled}
        className="flex items-center gap-2 px-4 py-2 bg-white/60 hover:bg-sky-50 text-slate-600 rounded-2xl text-sm font-bold transition-all active:scale-95 border border-white/60 disabled:opacity-50 disabled:cursor-not-allowed"
        aria-expanded={showMenu}
        aria-haspopup="listbox"
        aria-label="选择智能体"
      >
        <div className={cn(
          'w-6 h-6 rounded-lg flex items-center justify-center transition-all shadow-sm',
          selectedId ? `${getModeStyle(selected?.response_mode).bg} text-white shadow-glow` : 'bg-sky-100',
        )}>
          {(() => { const M = selected ? getModeStyle(selected.response_mode).Mascot : null; return M ? <M size={14} /> : <MascotHappy size={14} />; })()}
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
            className="absolute bottom-full left-0 mb-2 max-h-64 w-56 overflow-y-auto bg-white/95 backdrop-blur-xl border border-white/60 rounded-3xl shadow-2xl z-40 p-2"
            role="listbox"
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
                role="option"
                aria-selected={selectedId === agent.id}
                className={cn(
                  'mb-1 flex w-full items-center gap-3 rounded-2xl p-2.5 text-left transition-all last:mb-0 hover:bg-sky-50/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400/60',
                  selectedId === agent.id ? `${getModeStyle(agent.response_mode).selectedBg} ring-1 ${getModeStyle(agent.response_mode).ring}` : '',
                )}
              >
                <span className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-xl text-sm shadow-sm transition-transform',
                  selectedId === agent.id ? `${getModeStyle(agent.response_mode).bg} text-white` : 'bg-sky-50 text-slate-500',
                )}>
                  {React.createElement(getModeStyle(agent.response_mode).Mascot, { size: 20 })}
                </span>
                <div className="min-w-0 flex flex-col">
                  <span className={cn('truncate text-xs font-bold transition-colors', selectedId === agent.id ? getModeStyle(agent.response_mode).text : 'text-slate-700')}>
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
