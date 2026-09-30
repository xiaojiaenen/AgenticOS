import { apiFetch } from './apiClient';

export type AdminConversation = {
  session_id: string;
  user_id?: number | null;
  user_name?: string | null;
  user_email?: string | null;
  agent_profile_name?: string | null;
  summary?: string | null;
  first_message?: string | null;
  last_message?: string | null;
  message_count: number;
  model_names: string[];
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  avg_latency_ms: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ConversationListResponse = {
  items: AdminConversation[];
  total: number;
};

export type AdminConversationDetailMessage = {
  id: number;
  role?: string | null;
  text: string;
  reasoning_text?: string | null;
  tool_calls?: Array<{
    id?: string | null;
    name: string;
    arguments?: Record<string, unknown> | null;
  }>;
  tool_results?: Array<{
    tool_call_id?: string | null;
    name?: string | null;
    status: string;
    result: string;
  }>;
  created_at?: string | null;
};

export type AdminConversationDetail = {
  session_id: string;
  user_id?: number | null;
  user_name?: string | null;
  user_email?: string | null;
  agent_profile_name?: string | null;
  summary?: string | null;
  message_count: number;
  model_names: string[];
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  avg_latency_ms: number;
  created_at?: string | null;
  updated_at?: string | null;
  messages_offset: number;
  messages_limit: number;
  messages: AdminConversationDetailMessage[];
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const DASHBOARD_ENDPOINT = `${API_BASE_URL}/api/v1/dashboard`;

export async function listConversations(params: { search?: string; offset?: number; limit?: number }): Promise<ConversationListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  query.set('offset', String(params.offset ?? 0));
  query.set('limit', String(params.limit ?? 20));

  return apiFetch<ConversationListResponse>(
    `${DASHBOARD_ENDPOINT}/conversations?${query.toString()}`,
    {},
    '会话列表加载失败',
  );
}

export async function getConversationDetail(
  sessionId: string,
  params: { messagesOffset?: number; messagesLimit?: number } = {},
): Promise<AdminConversationDetail> {
  const query = new URLSearchParams();
  query.set('messages_offset', String(params.messagesOffset ?? 0));
  query.set('messages_limit', String(params.messagesLimit ?? 20));

  return apiFetch<AdminConversationDetail>(
    `${DASHBOARD_ENDPOINT}/conversations/${encodeURIComponent(sessionId)}?${query.toString()}`,
    {},
    '会话详情加载失败',
  );
}

export async function deleteConversation(sessionId: string): Promise<void> {
  await apiFetch<void>(
    `${DASHBOARD_ENDPOINT}/conversations/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
    '删除会话失败',
  );
}
