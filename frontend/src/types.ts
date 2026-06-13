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
};

export type Attachment = {
  name: string;
  type: string;
  url: string; // Base64 or ObjectURL (caution with persistence)
};

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
  videoArtifact?: {
    status: 'generating' | 'ready';
    artifactId?: string;
    title?: string;
    videoUrl?: string;
    thumbnailUrl?: string;
    duration?: number;
  };
};

export type Session = {
  id: string;
  title: string;
  messages: Message[];
  createdAt?: number;
  updatedAt: number;
  mode?: 'general' | 'ppt' | 'website' | 'video' | 'bigdata';
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
  | {language: 'ppt'; artifactId?: string; html: string; title: string; slideCount: number; theme?: string}
  | {language: 'website'; artifactId: string; html: string; title: string;
      projectSlug: string; stack?: string; fileCount?: number}
  | {language: 'video'; artifactId: string; videoUrl: string; thumbnailUrl?: string;
      title: string; duration?: number; resolution?: string; fileSize?: number};
