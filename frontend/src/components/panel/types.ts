/**
 * 会话级面板的共享类型。
 *
 * 「会话级」= 不属于某条消息的产物，而是整个对话共用的视图
 * （运行日志 / 工作区文件）。它们和产物面板共用右侧栏，同一时刻只显示一个。
 *
 * 新增面板：写一个接收 SessionPanelProps 的组件，在 registry.ts 注册即可，
 * 宿主（SessionPanelHost）与触发器（SessionPanelTrigger）不用改。
 */
import type { ComponentType, ReactNode } from 'react';
import type { Message } from '../../types';

export type SessionPanelId = 'run-log' | 'files';

/** 所有会话级面板统一的 props。新面板用不上的字段忽略即可。 */
export interface SessionPanelProps {
  sessionId: string;
  messages: Message[];
  onClose: () => void;
}

export interface SessionPanelDefinition {
  id: SessionPanelId;
  title: string;
  icon: ComponentType<{ size?: number; className?: string }>;
  render: (props: SessionPanelProps) => ReactNode;
}
