import React, { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { MascotHappy, ChevronDownIcon } from './AnimatedIcons';
import { AgentProfile } from '../../services/agentProfileService';
import { AgentIcon, getAgentIcon } from './AgentIcon';

/**
 * 不同模式的小精灵组件和颜色。
 *
 * 颜色在这里是**功能标识**（一眼分辨 PPT / 网站 / 数据），所以刻意保留彩色，
 * 但每个色都配了 dark: 变体 —— 浅色下用深色文字，深色下换成亮色文字，
 * 否则暗色主题下「天蓝底 + 天蓝字」会糊成一团。
 */
const MODE_STYLES: Record<string, { bg: string; ring: string; text: string; selectedBg: string }> = {
  amber:   { bg: 'bg-amber-500',   ring: 'ring-amber-200 dark:ring-amber-500/40',   text: 'text-amber-700 dark:text-amber-300',   selectedBg: 'bg-amber-100/70 dark:bg-amber-500/20' },
  sky:     { bg: 'bg-sky-500',     ring: 'ring-sky-200 dark:ring-sky-500/40',       text: 'text-sky-700 dark:text-sky-300',       selectedBg: 'bg-sky-100/70 dark:bg-sky-500/20' },
  emerald: { bg: 'bg-emerald-500', ring: 'ring-emerald-200 dark:ring-emerald-500/40',text: 'text-emerald-700 dark:text-emerald-300',selectedBg: 'bg-emerald-100/70 dark:bg-emerald-500/20' },
  violet:  { bg: 'bg-violet-500',  ring: 'ring-violet-200 dark:ring-violet-500/40', text: 'text-violet-700 dark:text-violet-300',  selectedBg: 'bg-violet-100/70 dark:bg-violet-500/20' },
  slate:   { bg: 'bg-slate-700',   ring: 'ring-slate-200 dark:ring-slate-500/40',   text: 'text-slate-700 dark:text-slate-300',   selectedBg: 'bg-slate-100/70 dark:bg-slate-500/20' },
};

function getModeStyle(avatar?: string | null) {
  const tone = getAgentIcon(avatar).tone.replace('aos-tone-', '');
  return MODE_STYLES[tone] || MODE_STYLES.violet;
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
  const listboxId = React.useId();

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

  // 选中项的 id，供 combobox 的 aria-activedescendant 使用
  const activeOptionId = focusIndex >= 0 && agents[focusIndex]
    ? `${listboxId}-option-${agents[focusIndex].id}`
    : undefined;

  const renderOption = (agent: AgentProfile, idx: number) => {
    const modeStyle = getModeStyle(agent.avatar);
    const isSelected = selectedId === agent.id;
    return (
      <button
        key={agent.id}
        id={`${listboxId}-option-${agent.id}`}
        ref={(el) => { itemRefs.current[idx] = el; }}
        onClick={() => {
          onSelect(agent);
          setShowMenu(false);
        }}
        role="option"
        aria-label={agent.name}
        aria-selected={isSelected}
        className={cn(
          'mb-1 flex w-full items-center gap-3 rounded-2xl p-2.5 text-left transition-all last:mb-0',
          'hover:bg-[var(--surface-2)] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
          isSelected ? `${modeStyle.selectedBg} ring-1 ${modeStyle.ring}` : '',
        )}
      >
        <span className={cn(
          'flex h-8 w-8 items-center justify-center rounded-xl text-sm shadow-sm transition-transform',
          isSelected ? `${modeStyle.bg} text-white` : 'bg-[var(--surface-2)] text-[var(--muted-foreground)]',
        )}>
          <AgentIcon avatar={agent.avatar} size={20} />
        </span>
        <div className="min-w-0 flex flex-col">
          <span className={cn('truncate text-xs font-semibold transition-colors', isSelected ? modeStyle.text : 'text-[var(--foreground)]')}>
            {agent.name}
          </span>
          <span className="truncate text-[9px] font-medium text-[var(--muted-foreground)]">
            {agent.description || '智能体'}
          </span>
        </div>
      </button>
    );
  };

  if (variant === 'compact') {
    return (
      <div className={cn('relative', className)} ref={menuRef}>
        <button
          onClick={() => !disabled && setShowMenu(!showMenu)}
          className={cn(
            'flex items-center justify-center rounded-full p-2.5 transition-all',
            'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
            'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
            disabled ? 'cursor-not-allowed opacity-60' : 'border border-transparent hover:border-[var(--border-subtle)] hover:bg-[var(--surface-2)] active:scale-95',
          )}
          title={disabled ? '对话已开始，无法更改智能体' : '选择智能体'}
          role="combobox"
          aria-expanded={showMenu}
          aria-haspopup="listbox"
          aria-controls={listboxId}
          aria-activedescendant={activeOptionId}
          aria-label={selected?.name ? `当前智能体：${selected.name}` : '选择智能体'}
        >
          <div className={cn(
            'flex h-5 w-5 items-center justify-center rounded-md border-2 text-[10px] font-semibold',
            selectedId ? `${getModeStyle(selected?.avatar).bg} border-transparent text-white` : 'border-[var(--border-strong)] text-[var(--muted-foreground)]',
          )}>
            {selected ? <AgentIcon avatar={selected.avatar} size={12} /> : <MascotHappy size={12} />}
          </div>
        </button>

        <AnimatePresence>
          {showMenu && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: -10 }}
              exit={{ opacity: 0, scale: 0.95, y: -20 }}
              className="aos-glass-rail absolute bottom-full left-0 z-40 mb-4 max-h-[360px] w-64 overflow-y-auto rounded-3xl p-2 shadow-2xl"
              id={listboxId}
              role="listbox"
              onKeyDown={handleKeyDown}
            >
              {selected && (
                <div className="mb-2 rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-xs font-semibold text-[var(--foreground)]">
                  当前：{selected.name}
                </div>
              )}
              {agents.map(renderOption)}
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
        className="aos-glass-surface flex items-center gap-2 rounded-2xl px-3.5 py-2 text-sm font-medium text-[var(--foreground)] transition-all hover:border-[var(--primary)]/35 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]"
        role="combobox"
        aria-expanded={showMenu}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-activedescendant={activeOptionId}
        aria-label={selected?.name ? `当前智能体：${selected.name}` : '选择智能体'}
      >
        <div className={cn(
          'flex h-6 w-6 items-center justify-center rounded-lg transition-all shadow-sm',
          selectedId ? `${getModeStyle(selected?.avatar).bg} text-white` : 'bg-[var(--surface-2)]',
        )}>
          {selected ? <AgentIcon avatar={selected.avatar} size={14} /> : <MascotHappy size={14} />}
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
            className="aos-glass-rail absolute bottom-full left-0 z-40 mb-2 max-h-64 w-60 overflow-y-auto rounded-3xl p-2 shadow-2xl"
            id={listboxId}
            role="listbox"
            onKeyDown={handleKeyDown}
          >
            {agents.map(renderOption)}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
