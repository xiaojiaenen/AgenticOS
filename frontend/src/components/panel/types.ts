/**
 * 会话级面板的共享类型。
 *
 * 「会话级」= 不属于某条消息的产物，而是整个对话共用的视图
 * （产物库 / 工作区文件 / 运行日志）。它们共用右侧栏，同一时刻显示一个
 * 标签页；右上角入口负责展开整条侧栏。
 *
 * 新增面板：写一个接收 SessionPanelProps 的组件，在 registry.tsx 注册即可，
 * 宿主（SessionPanelHost）与入口（SessionPanelTrigger）不用改。
 */
import type { ComponentType, ReactNode } from 'react';
import type { Message } from '../../types';

export type SessionPanelId = 'artifacts' | 'files' | 'run-log';

/** 所有会话级面板统一的 props。新面板用不上的字段忽略即可。 */
export interface SessionPanelProps {
  sessionId: string;
  messages: Message[];
  onClose: () => void;
}

export interface SessionPanelDefinition {
  id: SessionPanelId;
  title: string;
  /** 标签条上的短名 */
  tabLabel: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  render: (props: SessionPanelProps) => ReactNode;
}

/** 侧栏标签顺序（UI 单一事实来源） */
export const SESSION_PANEL_ORDER: SessionPanelId[] = ['artifacts', 'files', 'run-log'];
