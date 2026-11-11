import React from 'react';
import { Activity, FolderTree } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import type { SessionPanelId } from '../panel/types';

/**
 * 会话级面板入口：运行日志 / 会话文件。
 *
 * 为什么单独成组件：这类面板不属于任何「产物」，是整个对话唯一的视图。
 * 做成与产物面板并列的轻量入口，而不是塞进产物区逻辑里，能让右侧栏的
 * 打开状态保持集中在 store（sessionPanel）一处。
 *
 * 有产物面板在右侧时让位（隐藏入口），避免两个视图抢同一块区域 ——
 * 互斥语义与 Chat.tsx 的传参层一致。
 */

const BUTTON_CLASS = [
  'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1',
  'border-[var(--border-subtle)] bg-[var(--surface-1)] text-[11px] font-medium',
  'text-[var(--muted-foreground)] transition-colors',
  'hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
].join(' ');

const ENTRIES: Array<{
  id: SessionPanelId;
  label: string;
  title: string;
  Icon: typeof Activity;
}> = [
  { id: 'run-log', label: '运行日志', title: '查看本轮工具调用与状态', Icon: Activity },
  { id: 'files', label: '文件', title: '浏览会话工作区文件', Icon: FolderTree },
];

export const SessionPanelTrigger: React.FC = () => {
  const sessionPanel = useChatStore((s) => s.sessionPanel);
  const setSessionPanel = useChatStore((s) => s.setSessionPanel);
  const artifact = useChatStore((s) => s.artifact);

  // 有产物面板在右侧时让位 —— 避免两个入口抢同一个栏位。
  if (artifact) return null;

  return (
    <div className="mx-auto mt-2 flex max-w-4xl items-center justify-end gap-1.5 px-4">
      {ENTRIES.map(({ id, label, title, Icon }) => {
        const active = sessionPanel === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setSessionPanel(active ? null : id)}
            aria-pressed={active}
            title={title}
            className={`${BUTTON_CLASS} ${active ? 'border-[var(--ring)] text-[var(--foreground)]' : ''}`}
          >
            <Icon size={12} />
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
};
