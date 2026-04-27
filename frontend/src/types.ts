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
