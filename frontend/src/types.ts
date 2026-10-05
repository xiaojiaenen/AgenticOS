export type ToolCall = {
  id?: string;
  name: string;
  status: 'pending' | 'approval_required' | 'approved' | 'rejected' | 'success' | 'error';
  result?: string;
  approvalId?: string;
  arguments?: Record<string, unknown>;
  reason?: string;
  sideEffect?: boolean;
  requiresApproval?: boolean;
  toolExecuted?: boolean;
  errorType?: string;
  retryable?: boolean;
  attempts?: number;
  instruction?: string;
  isApiApproval?: boolean;
};

export type Attachment = {
  name: string;
  type: string;
  url: string; // Base64 or ObjectURL (caution with persistence)
};

/**
 * 消息的有序内容块：保留"文本 / 工具 / 思考"的真实到达顺序，
 * 而不是折叠进三个独立字段。
 *
 * - text：正文片段（流式期间持续追加到最后一个 text 块）
 * - tool：一次工具调用（引用 message.toolCalls 里的同 id 项）
 * - reasoning：思考片段
 *
 * 字段缺失时（历史消息 / localStorage 旧缓存）渲染层自动回退到
 * text + reasoningText + toolCalls 的旧式布局。
 */
export type MessageBlock =
  | { kind: 'text'; text: string }
  | { kind: 'reasoning'; text: string }
  | { kind: 'tool'; toolCallId: string };

export type AuthUser = {
  id: number;
  email: string;
  name: string;
  role: 'admin' | 'user' | string;
  is_active: boolean;
};

export type Message = {
  id: string;
  role: 'user' | 'model';
  text: string;
  reasoningText?: string;
  toolCalls?: ToolCall[];
  /** 有序内容块（流式按序渲染）；缺失时回退旧式三桶布局 */
  blocks?: MessageBlock[];
  attachments?: Attachment[];
  pptArtifact?: {
    status: 'generating' | 'ready';
    artifactId?: string;
    title?: string;
    slideCount?: number;
    html?: string;
    mode?: 'ppt';
    theme?: string;
  };
  websiteArtifact?: {
    status: 'generating' | 'ready';
    artifactId?: string;
    title?: string;
    projectSlug?: string;
    stack?: string;
    html?: string;
  };
  /** snapshot 体量可能上百 KB，不进 localStorage 缓存，刷新后靠 getSessionArtifacts 回源 */
  sheetArtifact?: {
    status: 'generating' | 'ready';
    artifactId?: string;
    title?: string;
    sheetNames?: string[];
    sheetCount?: number;
  };
};

export type Session = {
  id: string;
  title: string;
  messages: Message[];
  createdAt?: number;
  updatedAt: number;
  mode?: 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'sheet';
  agentProfileId?: number | null;
  agentName?: string;
  summary?: string | null;
  contextCompressed?: boolean;
  storage?: string;
  lastUsage?: Record<string, number> | null;
  latencyMs?: number | null;
  llmCalls?: number | null;
  messageCount?: number;
};

export type PptThemeName = 'executive' | 'product' | 'minimal';

export type PptSlideType =
  | 'cover'
  | 'section'
  | 'bullets'
  | 'imageText'
  | 'comparison'
  | 'timeline'
  | 'stats'
  | 'chart'
  | 'quote'
  | 'closing';

export type PptSlide = {
  type: PptSlideType;
  title: string;
  subtitle?: string;
  eyebrow?: string;
  body?: string;
  items?: string[];
  leftTitle?: string;
  rightTitle?: string;
  leftItems?: string[];
  rightItems?: string[];
  stats?: Array<{label: string; value: string; caption?: string}>;
  chart?: {
    type?: 'bar' | 'line' | 'donut';
    labels: string[];
    values: number[];
    unit?: string;
  };
  timeline?: Array<{label: string; title: string; body?: string}>;
  quote?: string;
  author?: string;
  imageUrl?: string;
};

export type PptDeck = {
  title: string;
  subtitle?: string;
  author?: string;
  theme?: PptThemeName;
  slides: PptSlide[];
};

export type Artifact =
  | {language: 'html' | 'svg'; code: string}
  | {language: 'ppt'; artifactId?: string; html: string; title: string; slideCount: number; theme?: string; sessionId?: string}
  | {language: 'website'; artifactId: string; html: string; title: string;
      projectSlug: string; stack?: string; fileCount?: number; sessionId?: string; version?: number}
  | {language: 'email'; approvalId: string; to: string; subject: string; body: string;
      cc?: string; isHtml?: boolean}
  /** spreadsheet 的 snapshot 是 Univer 的 IWorkbookData 原样 JSON */
  | {language: 'spreadsheet'; artifactId: string; title: string;
      snapshot: Record<string, unknown>; sheetNames: string[]; sheetCount: number;
      sessionId?: string; version?: number};
