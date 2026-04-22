export type ToolCall = {
  name: string;
  status: 'pending' | 'success';
  result?: string;
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
};
