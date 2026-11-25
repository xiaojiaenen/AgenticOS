import { Message } from '../../types';
import { apiFetch } from '../apiClient';
import { mapBackendMessages } from '../backendMessageMapper';
import {
  AGENT_ENDPOINT,
  AgentApproval, AgentSessionState,
  AgentWebsiteArtifact, AgentSheetArtifact, AgentDocumentArtifact, AgentPptArtifact,
  createTitleFromText,
} from './shared';

export async function submitApprovalDecision(
  approvalId: string,
  status: 'approved' | 'rejected' | 'respond',
  reason?: string,
  modifiedArguments?: Record<string, unknown>,
  response?: string,
): Promise<AgentApproval> {
  return apiFetch<AgentApproval>(
    `${AGENT_ENDPOINT}/approvals/${approvalId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 用户在预览面板里改过内容/模板时，把改后的工具参数一起回传；
      // 后端批准执行时用它们替换原始参数。
      // status=respond（人工代答）时 response 携带用户答案回灌给模型。
      body: JSON.stringify({
        status,
        reason,
        ...(modifiedArguments ? { modified_arguments: modifiedArguments } : {}),
        ...(response ? { response } : {}),
      }),
    },
    '审批提交失败',
  );
}

/** 邮件模板预览：切换模板时不经 AI，后端纯函数重渲染，毫秒级返回。 */
export type EmailTemplateChoice = { id: string; label: string };
export type EmailTemplatePreview = {
  html: string;
  is_html: boolean;
  template: string;
  needs_ai: boolean;
};

export async function listEmailTemplates(): Promise<EmailTemplateChoice[]> {
  return apiFetch<EmailTemplateChoice[]>(
    '/api/v1/email/templates',
    {},
    '加载邮件模板失败',
  );
}

export async function previewEmailTemplate(payload: {
  template: string;
  subject: string;
  body: string;
  button_label?: string;
  button_url?: string;
  signer?: string;
}): Promise<EmailTemplatePreview> {
  return apiFetch<EmailTemplatePreview>(
    '/api/v1/email/templates/preview',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '邮件模板预览失败',
  );
}

export async function submitUserDecision(
  decisionId: string,
  answer: string,
): Promise<{ ok: boolean; decision_id: string; answer: string }> {
  return apiFetch<{ ok: boolean; decision_id: string; answer: string }>(
    `${AGENT_ENDPOINT}/decisions/${decisionId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    },
    '决策提交失败',
  );
}

export async function getAgentSessionState(sessionId: string): Promise<AgentSessionState> {
  return apiFetch<AgentSessionState>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}`,
    {},
    '会话状态读取失败',
  );
}

/** 后端消息原始格式（映射逻辑见 backendMessageMapper.ts） */
type BackendMessage = import('../backendMessageMapper').BackendMessage;

/** 会话最新制品信息（用于会话重新打开时恢复预览面板） */
export type SessionArtifacts = {
  ppt_artifact: {
    artifact_id: string;
    session_id: string;
    title: string;
    slide_count: number;
    html: string;
    theme?: string;
  } | null;
  website_artifact: AgentWebsiteArtifact | null;
  sheet_artifact: AgentSheetArtifact | null;
  document_artifact: AgentDocumentArtifact | null;
};

/** 从后端加载会话关联的最新制品（PPT/网站） */
export async function getSessionArtifacts(sessionId: string): Promise<SessionArtifacts> {
  return apiFetch<SessionArtifacts>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/artifacts`,
    {},
    '加载会话制品失败',
  );
}

/** 按 artifactId 获取 PPT 预览 HTML（用于懒加载） */
export async function getPptPreviewHtml(artifactId: string): Promise<string> {
  return apiFetch<string>(
    `${AGENT_ENDPOINT}/ppt/preview/${artifactId}`,
    { responseType: 'text' },
    '加载 PPT 预览失败',
  );
}

export type PolishPromptResult = {
  polished: string;
  original: string;
  changed: boolean;
};

/**
 * 提示词润色：分析用户意图后改写为更可执行的长提示词。
 * 传入 signal 可在用户点「取消润色」时中断请求。
 */
export async function polishPrompt(
  text: string,
  signal?: AbortSignal,
): Promise<PolishPromptResult> {
  return apiFetch<PolishPromptResult>(
    `${AGENT_ENDPOINT}/polish-prompt`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      // 润色要过一次 LLM，放宽默认超时
      timeoutMs: 90_000,
      ...(signal ? { signal } : {}),
    },
    '提示词润色失败',
  );
}

export type ArtifactKind = 'ppt' | 'website' | 'sheet' | 'document';

export type ArtifactVersion = {
  kind: ArtifactKind;
  version: number;
  /** ppt 为 artifact_id；website / sheet 为版本号 "v{n}" */
  reference: string;
  title?: string;
  created_at?: string | null;
  slide_count?: number;
};

/** 列出会话的全部产物版本（PPT 每轮一条记录 + 网站每轮快照） */
export async function listSessionVersions(sessionId: string): Promise<{ versions: ArtifactVersion[] }> {
  return apiFetch<{ versions: ArtifactVersion[] }>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/versions`,
    {},
    '加载历史版本失败',
  );
}

/** 加载指定版本的产物，用于"回看历史版本" */
export async function loadArtifactVersion(
  sessionId: string,
  kind: ArtifactKind,
  reference: string,
): Promise<{
  ppt_artifact?: { artifact_id: string; title: string; slide_count: number; html: string; theme?: string };
  website_artifact?: {
    artifact_id: string;
    title: string;
    project_slug: string;
    stack?: string;
    preview_html: string;
  };
  sheet_artifact?: AgentSheetArtifact;
  document_artifact?: AgentDocumentArtifact;
}> {
  return apiFetch(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/versions/${kind}/${encodeURIComponent(reference)}`,
    {},
    '加载该版本失败',
  );
}

/** 从后端加载会话的完整消息历史 */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  const raw = await apiFetch<BackendMessage[]>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/messages`,
    {},
    '加载消息历史失败',
  );
  return mapBackendMessages(raw);
}

export async function generateTitle(history: Message[]): Promise<string> {
  const firstUserMessage = history.find((item) => item.role === 'user')?.text ?? '';
  const lastAssistantMessage = [...history].reverse().find((item) => item.role === 'model')?.text ?? '';
  return createTitleFromText(firstUserMessage || lastAssistantMessage);
}

export type AgentSessionListItem = {
  session_id: string;
  summary?: string | null;
  /** 会话展示标题（首条用户消息摘录）；summary 是上下文压缩摘要，不能当标题用 */
  title?: string | null;
  metadata?: Record<string, unknown>;
  message_count: number;
  created_at?: string;
  updated_at?: string;
};

export async function listSessions(): Promise<AgentSessionListItem[]> {
  return apiFetch<AgentSessionListItem[]>(`${AGENT_ENDPOINT}/sessions`, {}, '获取会话列表失败');
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch<void>(`${AGENT_ENDPOINT}/sessions/${sessionId}`, { method: 'DELETE' }, '删除会话失败');
}

export async function submitUserInput(sessionId: string, apiName: string, values: Record<string, string>): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/user-input`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_name: apiName, values }),
    },
    '提交用户输入失败',
  );
}

export async function submitApiApproval(sessionId: string, approved: boolean, allowAll?: boolean): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/api-approval`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved, allow_all: allowAll }),
    },
    '提交审批决定失败',
  );
}

/** 保存用户对文档产物的修改。 */
export async function saveDocumentSnapshot(
  sessionId: string,
  directory: string,
  snapshot: Record<string, unknown>,
): Promise<void> {
  await apiFetch<{ ok: boolean }>(
    `${AGENT_ENDPOINT}/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(directory)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot }),
    },
    '保存文档失败',
  );
}

/** 保存用户对表格产物的修改（编辑器里点「保存」时调用）。 */
export async function saveSheetSnapshot(
  sessionId: string,
  directory: string,
  snapshot: Record<string, unknown>,
): Promise<void> {
  await apiFetch<{ ok: boolean }>(
    `${AGENT_ENDPOINT}/sessions/${encodeURIComponent(sessionId)}/sheets/${encodeURIComponent(directory)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot }),
    },
    '保存表格失败',
  );
}

/** 导出选项：转场 / 动画留空 = 用后端默认（fade / mixed）。 */
export type PptExportOptions = {
  /** 页面转场：fade / push / push-left / push-up / push-down / wipe / … */
  transition?: string;
  /** 元素入场动画：mixed / random / none / 具体动画名 */
  animation?: string;
  /** 是否写入演讲者备注（默认 true） */
  enableNotes?: boolean;
};

export async function exportPptx(
  artifactId: string,
  options?: PptExportOptions,
): Promise<Blob> {
  return apiFetch<Blob>(
    `${AGENT_ENDPOINT}/ppt/export`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        artifact_id: artifactId,
        transition: options?.transition,
        animation: options?.animation,
        enable_notes: options?.enableNotes ?? true,
      }),
      responseType: 'blob',
      timeoutMs: 120_000, // PPT 导出耗时较长
    },
    'PPT 导出失败',
  );
}

//: 导出时可选的转场（与后端 TRANSITIONS 表一致）
export const PPT_TRANSITIONS: { value: string; label: string }[] = [
  { value: 'fade', label: '淡入淡出' },
  { value: 'push', label: '推进（右）' },
  { value: 'push-left', label: '推进（左）' },
  { value: 'push-up', label: '推进（上）' },
  { value: 'push-down', label: '推进（下）' },
  { value: 'wipe', label: '擦除' },
  { value: 'none', label: '无转场' },
];

// PPT 主题相关 API
export type PptTheme = {
  name: string;
  primary_color: string;
  bg_color: string;
  text_color: string;
  /** WCAG 对比度等级（正文/背景等固定组合的最差档）：AAA / AA / AA-Large / FAIL / null(审计失败) */
  contrast_grade?: string | null;
};

export async function listPptThemes(): Promise<PptTheme[]> {
  return apiFetch<PptTheme[]>(`${AGENT_ENDPOINT}/ppt/themes`, {}, '获取主题列表失败');
}

/**
 * PPT 视觉风格（与配色主题**正交**）。
 *
 * 主题管色值 / 字体族 / 圆角 / 阴影；视觉风格管形状语言、装饰密度、
 * 留白节奏、纹理层次。上游 ppt-master 把这两层分开，本地此前只有主题层，
 * 用户切主题只看到颜色变化、觉得"样式没变"。
 */
export type PptVisualStyle = {
  id: string;
  /** 中文名（瑞士极简 / 杂志编辑 …） */
  label: string;
  /** 上游的英文一句特征 */
  label_en?: string;
  /** corporate | editorial | expressive | hand_drawn | specialty */
  category: string;
  summary: string;
  /** core | supportive | sparse —— 插画在画面中的主导程度 */
  illustration?: string;
};

export const VISUAL_STYLE_CATEGORY_LABELS: Record<string, string> = {
  corporate: '商务 / 产品',
  editorial: '编辑 / 出版',
  expressive: '表现 / 印刷',
  hand_drawn: '手绘 / 笔刷',
  specialty: '专门',
};

/** 18 种视觉风格目录（与配色主题组合使用）。 */
export async function listPptVisualStyles(): Promise<PptVisualStyle[]> {
  return apiFetch<PptVisualStyle[]>(
    `${AGENT_ENDPOINT}/ppt/visual-styles`,
    {},
    '获取视觉风格列表失败',
  );
}

export async function rethemePpt(artifactId: string, theme: string): Promise<AgentPptArtifact & { theme: string }> {
  return apiFetch<AgentPptArtifact & { theme: string }>(
    `${AGENT_ENDPOINT}/ppt/${artifactId}/retheme`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme }),
    },
    '主题切换失败',
  );
}

