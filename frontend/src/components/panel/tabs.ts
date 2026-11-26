/**
 * 侧栏标签的**纯数据**定义与收集逻辑。
 *
 * 从 IdeSidebar.tsx 抽出来，原因有二：
 * 1. chatStore / hook 只需要类型与收集函数，不该 import 整个 UI 模块
 *    （会拖进 PptArtifactPanel / Univer 等重依赖）；
 * 2. 收集逻辑是纯函数，vitest 可以直接喂消息 + 工作区文件锁定口径。
 *
 * 产物来源有两类：
 * - 挂在消息上的结构化产物（ppt / website / document / sheet / 图片附件）；
 * - 工作区里的文件产物（html / csv / xlsx / json / txt / md / 图片），
 *   由 `collectOutputTabs` 收集。模型用 write_text_file 写出的 html 属于后者。
 */
import type { Artifact, Message } from '../../types';
import {
  collectDisplayableOutputs,
  outputKind,
  type OutputKind,
  type WorkspaceEntry,
} from '../../lib/workspaceArtifacts';

export type TabKind =
  | 'ppt' | 'website' | 'document' | 'sheet' | 'image' | 'file' | 'log' | 'output'
  // 功能面板（工作台）：会话级视图，不属于某条消息
  | 'files' | 'run-log' | 'artifacts';

/** 功能面板 tab 的稳定 id（全局唯一，与会话无关） */
export const PANEL_TAB_IDS: Record<'files' | 'run-log' | 'artifacts', string> = {
  files: 'panel:files',
  'run-log': 'panel:run-log',
  artifacts: 'panel:artifacts',
};

export interface SidebarTab {
  /** 稳定 id：kind + 业务 id */
  id: string;
  kind: TabKind;
  title: string;
  /** 直接可渲染的产物快照（website 不用，走新窗口） */
  artifact?: Artifact;
  /** 文件路径（file / output 标签） */
  path?: string;
  /** workspace 产物类型（html / image / data） */
  outputKind?: OutputKind;
  /** output 标签的带鉴权读取 URL */
  url?: string;
  /** website：项目 slug（现签预览链接用） */
  projectSlug?: string;
  /** website：技术栈（vue/react 的 SPA 不能 srcDoc 内联 —— 会劫持路由） */
  stack?: string;
}

/** 构造一个功能面板 tab */
export function panelTab(kind: 'files' | 'run-log' | 'artifacts'): SidebarTab {
  const meta = {
    files: { title: '会话文件' },
    'run-log': { title: '运行日志' },
    artifacts: { title: '会话产物' },
  }[kind];
  return { id: PANEL_TAB_IDS[kind], kind, title: meta.title };
}

/** 从消息收集「可开标签」的条目（结构化产物 + 图片附件）。 */
export function collectMessageTabs(messages: Message[], sessionId: string): SidebarTab[] {
  const out: SidebarTab[] = [];
  const seen = new Set<string>();
  const push = (tab: SidebarTab) => {
    if (seen.has(tab.id)) return;
    seen.add(tab.id);
    out.push(tab);
  };
  messages.forEach((m, i) => {
    if (m.pptArtifact?.status === 'ready') {
      // id 用真 artifactId；只有历史脏数据（早期未落库的旧消息）才退回位置序号。
      const id = m.pptArtifact.artifactId ?? `ppt-${i}`;
      push({
        id: `ppt:${id}`,
        kind: 'ppt',
        title: m.pptArtifact.title || '演示文稿',
        // artifact 始终构造（即使没有 html）：PptArtifactPanel 会按
        // artifactId 懒加载预览，工具栏（主题/导出/编辑）不依赖 html。
        artifact: {
          language: 'ppt',
          artifactId: m.pptArtifact.artifactId,
          // 空串 = 尚未加载，PptArtifactPanel 会按 artifactId 回源预览
          html: m.pptArtifact.html ?? '',
          title: m.pptArtifact.title ?? '',
          slideCount: m.pptArtifact.slideCount ?? 0,
          theme: m.pptArtifact.theme,
          sessionId,
        },
      });
    }
    if (m.websiteArtifact?.status === 'ready') {
      const id = m.websiteArtifact.artifactId ?? `web-${i}`;
      push({
        id: `website:${id}`,
        kind: 'website',
        title: m.websiteArtifact.title || '网站',
        projectSlug: m.websiteArtifact.projectSlug,
        stack: m.websiteArtifact.stack,
        /** 内联快照 —— 仅 vanilla（无路由脚本）允许 srcDoc 渲染 */
        artifact: { language: 'website', artifactId: id, html: m.websiteArtifact.html ?? '', title: m.websiteArtifact.title ?? '', projectSlug: m.websiteArtifact.projectSlug ?? '', stack: m.websiteArtifact.stack, fileCount: 0 },
      });
    }
    if (m.documentArtifact?.status === 'ready') {
      push({ id: `document:${m.documentArtifact.artifactId ?? i}`, kind: 'document', title: m.documentArtifact.title || '文档' });
    }
    if (m.sheetArtifact?.status === 'ready') {
      push({ id: `sheet:${m.sheetArtifact.artifactId ?? i}`, kind: 'sheet', title: m.sheetArtifact.title || '表格' });
    }
    m.attachments?.forEach((a, j) => {
      if (a.type?.startsWith('image/')) {
        push({ id: `image:${i}-${j}-${a.name}`, kind: 'image', title: a.name || '图片' });
      }
    });
  });
  return out;
}

/**
 * 从工作区文件收集产物标签。
 *
 * id 稳定用 `output:<path>`：同一文件流结束后重新拉取不会开重复标签，
 * 会话切换由调用方过滤（标签按 sessionId 存 store）。
 */
export function collectOutputTabs(entries: WorkspaceEntry[], _sessionId: string): SidebarTab[] {
  const out: SidebarTab[] = [];
  const seen = new Set<string>();
  for (const entry of collectDisplayableOutputs(entries)) {
    const id = `output:${entry.path}`;
    if (seen.has(id)) continue;
    seen.add(id);
    out.push({
      id,
      kind: 'output',
      title: entry.name,
      path: entry.path,
      outputKind: outputKind(entry),
      url: outputUrl(_sessionId, entry),
    });
  }
  return out;
}

/** 与 `outputDownloadUrl` 同源，但 tabs.ts 不依赖 services，避免测试拉进 fetch 栈。 */
function outputUrl(sessionId: string, entry: WorkspaceEntry): string {
  const filename = entry.path.split('/').pop() ?? entry.name;
  return `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/outputs/${encodeURIComponent(filename)}`;
}

/** 消息产物 + 工作区产物，去重后按消息产物在前的顺序返回。 */
export function collectTabs(
  messages: Message[],
  sessionId: string,
  outputs: WorkspaceEntry[] = [],
): SidebarTab[] {
  return [...collectMessageTabs(messages, sessionId), ...collectOutputTabs(outputs, sessionId)];
}
