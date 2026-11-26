/**
 * 后端 artifact payload → 消息快照的统一映射。
 *
 * useChatStream（流式挂载）与 useChatSessions（回源挂载）此前各自内联了这组
 * 映射 —— 挂载逻辑写了三份拷贝，是「实时空白、刷新正常」类漂移 bug 的温床
 * （挂载顺序/字段差异只改了一处忘掉另一处）。统一到这里后，新增 artifact
 * 字段只改一处。
 */
import type { Message } from '../types';

export type PptMessageArtifact = NonNullable<Message['pptArtifact']>;
export type WebsiteMessageArtifact = NonNullable<Message['websiteArtifact']>;
export type SheetMessageArtifact = NonNullable<Message['sheetArtifact']>;

/** 流式事件与回源接口共用的 payload 形状（snake_case，后端直出） */
type PptPayload = {
  artifact_id: string;
  title: string;
  slide_count: number;
  html: string;
  theme?: string;
};

type WebsitePayload = {
  artifact_id: string;
  title: string;
  project_slug: string;
  stack: string;
  preview_html: string;
  /** 后端 payload 自带，但流式路径刻意不消费（TTL 问题，见下） */
  preview_url?: string | null;
};

type SheetPayload = {
  artifact_id: string;
  title: string;
  sheet_names: string[];
  sheet_count: number;
};

export function pptMessageArtifact(p: PptPayload): PptMessageArtifact {
  return {
    status: 'ready',
    artifactId: p.artifact_id,
    title: p.title,
    slideCount: p.slide_count,
    html: p.html,
    mode: 'ppt',
    theme: p.theme,
  };
}

export function websiteMessageArtifact(
  p: WebsitePayload,
  /** 仅回源路径传入：预览令牌 15 分钟 TTL。流式路径**不要**存 preview_url
   *  进内存态 artifact（切走再切回时早已过期，iframe 渲染 403 错误页）——
   *  实时预览一律走 preview_html 内联 srcDoc，带签名 URL 现用现签。 */
  opts?: { previewUrl?: string | null },
): WebsiteMessageArtifact {
  return {
    status: 'ready',
    artifactId: p.artifact_id,
    title: p.title,
    projectSlug: p.project_slug,
    stack: p.stack,
    previewUrl: opts?.previewUrl ?? undefined,
    html: p.preview_html,
  };
}

export function sheetMessageArtifact(p: SheetPayload): SheetMessageArtifact {
  return {
    status: 'ready',
    artifactId: p.artifact_id,
    title: p.title,
    sheetNames: p.sheet_names,
    sheetCount: p.sheet_count,
  };
}

/**
 * 把 patch 应用到 messages 中最后一条 model 消息（回源挂载的统一入口）。
 * 找不到 model 消息时原样返回同一数组引用。
 */
export function patchLastModelMessage<T extends { role: string }>(
  messages: T[],
  patch: (message: T) => T,
): T[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === 'model') {
      return messages.map((message, index) => (index === i ? patch(message) : message));
    }
  }
  return messages;
}

/** 产物恢复判定所需的最小消息形状（两种 helper 共用）。 */
export type ArtifactSnapshotMsg = {
  role: string;
  pptArtifact?: { status?: string; html?: string };
  websiteArtifact?: { status?: string; html?: string };
};

/** 缓存剥离 artifact HTML 后，是否还要等回源补全（此时过早恢复会拿到空预览）。 */
export function hasPendingArtifactHtml(messages: ArtifactSnapshotMsg[]): boolean {
  return messages.some(
    (m) =>
      m.role === 'model' &&
      ((m.pptArtifact && !m.pptArtifact.html) || (m.websiteArtifact && !m.websiteArtifact.html)),
  );
}

/**
 * 从消息里挑出可恢复的产物（后往前，PPT 优先于网站）。
 * Chat.tsx 的恢复 effect 用它做纯决策，effect 本身只管 ref / 异步回源时序。
 */
export function findRestorableArtifact(messages: ArtifactSnapshotMsg[]): 'ppt' | 'website' | null {
  const reversed = [...messages].reverse();
  const ppt = reversed.find(
    (m) => m.role === 'model' && m.pptArtifact?.status === 'ready' && m.pptArtifact.html,
  );
  if (ppt) return 'ppt';
  const website = reversed.find(
    (m) => m.role === 'model' && m.websiteArtifact?.status === 'ready' && m.websiteArtifact.html,
  );
  return website ? 'website' : null;
}

/**
 * 无产物的会话是否应清空当前面板：只清「明确属于其它会话」的，或本来就是空的。
 * 流式刚设置、尚未带 sessionId 的产物不动（避免迟到响应把用户刚打开的面板打掉）。
 */
export function shouldClearStaleArtifact(
  artifact: { sessionId?: string } | null | undefined,
  currentSessionId: string,
): boolean {
  if (!artifact) return true;
  if ('sessionId' in artifact && typeof artifact.sessionId === 'string') {
    return artifact.sessionId !== currentSessionId;
  }
  return false;
}
