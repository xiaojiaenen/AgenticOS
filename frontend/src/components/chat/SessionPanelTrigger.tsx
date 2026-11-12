/**
 * 右侧栏入口（右上角）。
 *
 * 侧栏是 IDE 式的：点会话里的产物卡片 → 开一个标签；这个按钮负责
 * 「不带具体产物时」也能展开侧栏（默认开最后一个产物，或显示可打开列表）。
 */
import React from 'react';
import { PanelRightOpen } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { cn } from '../../lib/utils';
import { collectTabs } from '../panel/IdeSidebar';
import type { Message } from '../../types';

export const SessionPanelTrigger: React.FC<{ sessionId: string | null; messages: Message[] }> = ({ sessionId, messages }) => {
  const sidebarOpen = useChatStore((s) => s.sidebarOpen);
  const setSidebarOpen = useChatStore((s) => s.setSidebarOpen);
  const closeSidebar = useChatStore((s) => s.closeSidebar);
  const openTab = useChatStore((s) => s.openSidebarTab);

  const toggle = () => {
    if (sidebarOpen) {
      closeSidebar();
      return;
    }
    // 展开时若会话已有产物，直接开最后一个（省一次点击）；否则只展开空侧栏
    const tabs = collectTabs(messages, sessionId ?? '');
    if (tabs.length > 0) openTab(tabs[tabs.length - 1]);
    else setSidebarOpen(true);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={sidebarOpen}
      aria-label={sidebarOpen ? '收起侧栏' : '展开侧栏'}
      title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
      className={cn(
        'absolute right-4 top-4 z-40 inline-flex h-9 items-center gap-1.5 rounded-xl border px-2.5 shadow-sm backdrop-blur transition-all active:scale-95',
        sidebarOpen
          ? 'border-[var(--ring)] bg-[var(--surface-2)] text-[var(--foreground)]'
          : 'border-[var(--border-subtle)] bg-[var(--surface-1)]/90 text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:shadow-md',
      )}
    >
      <PanelRightOpen size={15} />
      <span className="hidden text-[11px] font-medium sm:inline">侧栏</span>
    </button>
  );
};
