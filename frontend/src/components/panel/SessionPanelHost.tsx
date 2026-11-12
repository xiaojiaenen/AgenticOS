/**
 * 会话级面板宿主：右侧栏的通用壳层（header + 标签条 + 内容区）。
 *
 * 与 ChatArtifactArea 平级：同一时刻右侧栏要么显示产物、要么显示
 * 会话面板（互斥由 Chat.tsx 在传参层保证：sessionPanel 打开时给产物区
 * 传 null artifact）。宿主自己读 store，Chat.tsx 只需要挂一行。
 *
 * 标签顺序与定义全部来自 registry / SESSION_PANEL_ORDER，新增面板只改那两处。
 */
import * as React from 'react';
import { motion } from 'motion/react';
import { X } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useChatStore } from '../../stores/chatStore';
import { SESSION_PANELS } from './registry';
import { SESSION_PANEL_ORDER, type SessionPanelId } from './types';

export interface SessionPanelHostProps {
  sessionId: string | null;
  messages: import('../../types').Message[];
}

export const SessionPanelHost: React.FC<SessionPanelHostProps> = ({ sessionId, messages }) => {
  const panel = useChatStore((s) => s.sessionPanel);
  const setSessionPanel = useChatStore((s) => s.setSessionPanel);

  if (!panel) return null;
  const def = SESSION_PANELS[panel];
  if (!def) return null;
  const Icon = def.icon;
  const close = () => setSessionPanel(null);

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '100%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
      className="relative flex h-full min-w-0 flex-col overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--surface-1)]"
      aria-label={def.title}
    >
      <header className="flex shrink-0 items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-2)] text-[var(--muted-foreground)]">
          <Icon size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-[var(--foreground)]">{def.title}</h2>
        </div>
        <button
          type="button"
          onClick={close}
          aria-label="关闭侧栏"
          className="shrink-0 rounded-md p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
        >
          <X size={16} />
        </button>
      </header>

      {/* 标签条：一个右侧栏内切换多个视图，不用来回开关 */}
      <nav
        className="flex shrink-0 gap-1 border-b border-[var(--border-subtle)] px-3 py-2"
        aria-label="侧栏视图"
      >
        {SESSION_PANEL_ORDER.map((id) => {
          const entry = SESSION_PANELS[id];
          const TabIcon = entry.icon;
          const active = id === panel;
          return (
            <button
              key={id}
              type="button"
              onClick={() => setSessionPanel(id as SessionPanelId)}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-medium transition-colors',
                active
                  ? 'bg-[var(--surface-2)] text-[var(--foreground)]'
                  : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
              )}
            >
              <TabIcon size={13} /> {entry.tabLabel}
            </button>
          );
        })}
      </nav>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {def.render({ sessionId: sessionId ?? '', messages, onClose: close })}
      </div>
    </motion.aside>
  );
};

export type { SessionPanelId };
