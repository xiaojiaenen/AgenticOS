/**
 * 会话级面板宿主：右侧栏的通用壳层（header + 内容区）。
 *
 * 与 ChatArtifactArea 平级：同一时刻右侧栏要么显示产物、要么显示
 * 会话面板（互斥由 Chat.tsx 在传参层保证：sessionPanel 打开时给产物区
 * 传 null artifact）。宿主自己读 store，Chat.tsx 只需要挂一行。
 *
 * 新增面板：在 registry.ts 的 SESSION_PANELS 加一条，这里自动认得。
 */
import * as React from 'react';
import { motion } from 'motion/react';
import { X } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { SESSION_PANELS } from './registry';
import type { SessionPanelId } from './types';

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
          aria-label={`关闭${def.title}`}
          className="shrink-0 rounded-md p-1.5 text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
        >
          <X size={16} />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {def.render({ sessionId: sessionId ?? '', messages, onClose: close })}
      </div>
    </motion.aside>
  );
};

export type { SessionPanelId };
