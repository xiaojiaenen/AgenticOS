/**
 * 会话工作区产物（html / csv / xlsx / json / txt / md / 图片）的纯逻辑。
 *
 * 后端 `/api/v1/files/workspace` 只返回文件树，模型用
 * `write_text_file("index.html")` 写出来的网页因此只出现在「文件」面板里，
 * 不在对话下方、也不进侧栏产物列表 —— 用户报的正是这个问题。
 *
 * 这里集中定义「什么算可展示产物」和「怎么打开/下载它」，供消息 footer、
 * 侧栏产物库、侧栏 tab 共用。全部是纯函数，便于单测锁定口径。
 */
import type { Message } from '../types';

/** 与 `/files/workspace` 返回条目一致的结构。 */
export type WorkspaceEntry = {
  name: string;
  path: string;
  type: 'dir' | 'file';
  size: number | null;
};

/** 工作区里可以在对话/侧栏展示或下载的文件扩展名。 */
export const DISPLAYABLE_OUTPUT_EXTENSIONS = [
  'html', 'htm', 'csv', 'xlsx', 'json', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp', 'gif',
] as const;

const DISPLAYABLE = new Set<string>(DISPLAYABLE_OUTPUT_EXTENSIONS);

export type OutputKind = 'html' | 'image' | 'data';

function extensionOf(path: string): string {
  const name = path.split('/').pop() ?? '';
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
}

/** 目录、隐藏文件、非白名单扩展名都不是「产物」。 */
export function isDisplayableOutput(entry: WorkspaceEntry): boolean {
  if (entry.type !== 'file') return false;
  if (!entry.name || entry.name.startsWith('.')) return false;
  return DISPLAYABLE.has(extensionOf(entry.path));
}

export function outputKind(entry: WorkspaceEntry): OutputKind {
  const ext = extensionOf(entry.path);
  if (ext === 'html' || ext === 'htm') return 'html';
  if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) return 'image';
  return 'data';
}

/** 过滤 + 去重（同一 path 只保留一条）。 */
export function collectDisplayableOutputs(entries: WorkspaceEntry[]): WorkspaceEntry[] {
  const seen = new Set<string>();
  const out: WorkspaceEntry[] = [];
  for (const entry of entries) {
    if (!isDisplayableOutput(entry) || seen.has(entry.path)) continue;
    seen.add(entry.path);
    out.push(entry);
  }
  return out;
}

/**
 * 带鉴权的文件读取端点。工作区不在静态目录下，必须走这个端点。
 * 后端会校验会话归属 + 文件名白名单，因此前端只负责拼 URL。
 */
export function outputDownloadUrl(sessionId: string, entry: WorkspaceEntry): string {
  // /files/workspace 返回相对路径（outputs/foo.csv 或根目录 index.html），
  // 后端读取端点只认文件名，取最后一段。
  const filename = entry.path.split('/').pop() ?? entry.name;
  return `/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/outputs/${encodeURIComponent(filename)}`;
}

/**
 * 消息里已有的产物数量（ppt / 网站 / 文档 / 表格 / 图片附件）。
 * 与工作区产物合并后就是「查看所有产物 (N)」里的 N。
 */
export function countMessageArtifacts(messages: Message[]): number {
  let n = 0;
  for (const m of messages) {
    if (m.pptArtifact?.status === 'ready') n += 1;
    if (m.websiteArtifact?.status === 'ready') n += 1;
    if (m.documentArtifact?.status === 'ready') n += 1;
    if (m.sheetArtifact?.status === 'ready') n += 1;
    n += (m.attachments ?? []).filter((a) => a.type?.startsWith('image/')).length;
  }
  return n;
}

/** footer 展示的总数：消息产物 + 工作区可展示文件。 */
export function countAllArtifacts(messages: Message[], outputs: WorkspaceEntry[]): number {
  return countMessageArtifacts(messages) + collectDisplayableOutputs(outputs).length;
}
