/**
 * 右侧会话面板的注册表。
 *
 * 「会话级面板」与产物面板共用右侧栏但来源不同：产物挂在消息上，
 * 会话面板（产物库 / 工作区文件 / 运行日志）挂在会话上。新增面板只需
 * 在这里注册一条 definition，宿主与右上角入口自动生效。
 */
import { Activity, FolderTree, Layers } from 'lucide-react';
import { RunLogPanel } from './RunLogPanel';
import { FilesPanel } from './FilesPanel';
import { ArtifactsPanel } from './ArtifactsPanel';
import type { SessionPanelDefinition, SessionPanelId } from './types';

export type { SessionPanelId } from './types';

export const SESSION_PANELS: Record<SessionPanelId, SessionPanelDefinition> = {
  artifacts: {
    id: 'artifacts',
    title: '会话产物',
    tabLabel: '产物',
    icon: Layers,
    render: (props) => <ArtifactsPanel {...props} />,
  },
  files: {
    id: 'files',
    title: '会话文件',
    tabLabel: '文件',
    icon: FolderTree,
    render: (props) => <FilesPanel {...props} />,
  },
  'run-log': {
    id: 'run-log',
    title: '运行日志',
    tabLabel: '日志',
    icon: Activity,
    render: (props) => <RunLogPanel {...props} />,
  },
};
