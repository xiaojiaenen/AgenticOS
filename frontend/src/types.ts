export type ToolCall = {
  id?: string;
  name: string;
  status: 'pending' | 'approval_required' | 'approved' | 'rejected' | 'success' | 'error';
  result?: string;
  approvalId?: string;
  arguments?: Record<string, unknown>;
  reason?: string;
};

export type Attachment = {
  name: string;
  type: string;
  url: string; // Base64 or ObjectURL (caution with persistence)
};

export type Message = {
  id: string;
  role: 'user' | 'model';
  text: string;
  toolCalls?: ToolCall[];
  attachments?: Attachment[];
};

export type Session = {
  id: string;
  title: string;
  messages: Message[];
  updatedAt: number;
  mode?: 'general' | 'ppt' | 'website';
  summary?: string | null;
  contextCompressed?: boolean;
  storage?: string;
  lastUsage?: Record<string, number> | null;
  latencyMs?: number | null;
  llmCalls?: number | null;
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
  | {language: 'pptdeck'; code: string; deck: PptDeck};
