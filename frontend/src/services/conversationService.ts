import { authHeaders } from './authService';

export type AdminConversation = {
  session_id: string;
  user_id?: number | null;
  user_name?: string | null;
  user_email?: string | null;
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
  created_at?: string | null;
};

export type AdminConversationDetail = {
  session_id: string;
  user_id?: number | null;
  user_name?: string | null;
  user_email?: string | null;
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
  messages: AdminConversationDetailMessage[];
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const DASHBOARD_ENDPOINT = `${API_BASE_URL}/api/v1/dashboard`;

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json();
  let message = 'Request failed';
  try {
    const payload = await response.json();
    if (typeof payload.detail === 'string') message = payload.detail;
  } catch {
    const text = await response.text();
    if (text) message = text;
  }
  throw new Error(message);
}

export async function listConversations(params: { search?: string; offset?: number; limit?: number }): Promise<ConversationListResponse> {
  const query = new URLSearchParams();
  if (params.search) query.set('search', params.search);
  query.set('offset', String(params.offset ?? 0));
  query.set('limit', String(params.limit ?? 20));

  const response = await fetch(`${DASHBOARD_ENDPOINT}/conversations?${query.toString()}`, {
    headers: authHeaders(),
  });
  return parseResponse<ConversationListResponse>(response);
}

export async function getConversationDetail(sessionId: string): Promise<AdminConversationDetail> {
  const response = await fetch(`${DASHBOARD_ENDPOINT}/conversations/${encodeURIComponent(sessionId)}`, {
    headers: authHeaders(),
  });
  return parseResponse<AdminConversationDetail>(response);
}

export async function deleteConversation(sessionId: string): Promise<void> {
  const response = await fetch(`${DASHBOARD_ENDPOINT}/conversations/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (response.ok) return;
  await parseResponse<unknown>(response);
}
