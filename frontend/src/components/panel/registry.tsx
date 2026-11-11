/**
 * 右侧会话面板的注册表。
 *
 * 「会话级面板」与产物面板共用右侧栏但来源不同：产物挂在消息上，
 * 会话面板（运行日志 / 工作区文件）挂在会话上。新增面板只需在这里
 * 注册一条 definition，宿主与触发器自动生效。
 */
import { Activity, FolderTree } from 'lucide-react';
import { RunLogPanel } from './RunLogPanel';
import { FilesPanel } from './FilesPanel';
import type { SessionPanelDefinition, SessionPanelId } from './types';

export type { SessionPanelId } from './types';

export const SESSION_PANELS: Record<SessionPanelId, SessionPanelDefinition> = {
  'run-log': {
    id: 'run-log',
    title: '运行日志',
    icon: Activity,
    render: (props) => <RunLogPanel {...props} />,
  },
  files: {
    id: 'files',
    title: '会话文件',
    icon: FolderTree,
    render: (props) => <FilesPanel {...props} />,
  },
};
