import { apiFetch, API_BASE_URL } from './apiClient';

const API = `${API_BASE_URL}/api/v1`;

export type IssueType = 'bug' | 'feature' | 'question' | 'other';
export type IssueStatus = 'open' | 'confirmed' | 'in_progress' | 'resolved' | 'shipped' | 'closed';
export type IssuePriority = 'low' | 'medium' | 'high';
export type IssueVisibility = 'public' | 'private';

export interface FeedbackAuthor {
  id: number;
  name: string;
  role: string;
}

export interface FeedbackIssue {
  id: number;
  type: IssueType;
  title: string;
  body: string;
  status: IssueStatus;
  priority: IssuePriority;
  visibility: IssueVisibility;
  author: FeedbackAuthor;
  vote_count: number;
  comment_count: number;
  my_vote: boolean;
  context: Record<string, string>;
  resolution_note: string | null;
  shipped_version: string | null;
  resolved_by: FeedbackAuthor | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackComment {
  id: number;
  issue_id: number;
  author: FeedbackAuthor | null;
  body: string;
  is_official: boolean;
  is_system: boolean;
  created_at: string;
}

export interface FeedbackIssueDetail {
  issue: FeedbackIssue;
  comments: FeedbackComment[];
}

export interface FeedbackListResponse {
  items: FeedbackIssue[];
  total: number;
  page: number;
  page_size: number;
}

export interface FeedbackStats {
  total: number;
  open: number;
  in_progress: number;
  resolved: number;
  shipped: number;
  closed: number;
  resolved_this_week: number;
  created_this_week: number;
  avg_resolve_hours: number | null;
  resolve_rate: number;
}

export interface ListFeedbackParams {
  page?: number;
  page_size?: number;
  status?: IssueStatus | '';
  type?: IssueType | '';
  search?: string;
  sort?: 'votes' | 'newest' | 'active';
  mine?: boolean;
}

function qs(params: Record<string, unknown>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const listFeedback = (params: ListFeedbackParams = {}, admin = false) =>
  apiFetch<FeedbackListResponse>(
    `${API}${admin ? '/admin/feedback' : '/feedback'}${qs(params as Record<string, unknown>)}`,
    {},
    '加载反馈失败',
  );

export const getFeedbackStats = (admin = false) =>
  apiFetch<FeedbackStats>(`${API}${admin ? '/admin/feedback' : '/feedback'}/stats`, {}, '加载反馈统计失败');

export const getFeedback = (id: number) =>
  apiFetch<FeedbackIssueDetail>(`${API}/feedback/${id}`, {}, '加载反馈详情失败');

export const createFeedback = (payload: {
  type: IssueType;
  title: string;
  body?: string;
  visibility?: IssueVisibility;
  context?: Record<string, string>;
}) =>
  apiFetch<FeedbackIssue>(
    `${API}/feedback`,
    { method: 'POST', body: JSON.stringify(payload) },
    '提交反馈失败',
  );

export const voteFeedback = (id: number) =>
  apiFetch<{ voted: boolean; vote_count: number }>(
    `${API}/feedback/${id}/vote`,
    { method: 'POST' },
    '投票失败',
  );

export const commentFeedback = (id: number, body: string) =>
  apiFetch<FeedbackComment>(
    `${API}/feedback/${id}/comments`,
    { method: 'POST', body: JSON.stringify({ body }) },
    '评论失败',
  );

export const adminUpdateFeedback = (
  id: number,
  payload: { status: IssueStatus; priority?: IssuePriority; resolution_note?: string; shipped_version?: string },
) =>
  apiFetch<FeedbackIssue>(
    `${API}/admin/feedback/${id}`,
    { method: 'PATCH', body: JSON.stringify(payload) },
    '更新反馈失败',
  );

export const adminReplyFeedback = (id: number, body: string) =>
  apiFetch<FeedbackComment>(
    `${API}/admin/feedback/${id}/reply`,
    { method: 'POST', body: JSON.stringify({ body }) },
    '回复失败',
  );

export const adminDeleteFeedback = (id: number) =>
  apiFetch<void>(`${API}/admin/feedback/${id}`, { method: 'DELETE' }, '删除反馈失败');

// ── 在线状态 / 每用户分析 ──
export const presenceHeartbeat = () =>
  apiFetch<{ online: boolean }>(`${API}/presence/heartbeat`, { method: 'POST', skip401: true }, '');

export interface UserAnalyticsRow {
  user_id: number;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  online: boolean;
  last_active_at: string | null;
  last_use_at: string | null;
  sessions: number;
  runs: number;
  total_tokens: number;
  tool_calls: number;
  llm_calls: number;
  top_tools: { name: string; count: number }[];
  top_modes: { name: string; count: number }[];
}

export const listUserAnalytics = (days = 14) =>
  apiFetch<{ items: UserAnalyticsRow[]; online_count: number; days: number }>(
    `${API}/admin/user-analytics${qs({ days })}`,
    {},
    '加载用户分析失败',
  );

export interface UserAnalyticsDetail {
  user_id: number;
  name: string;
  email: string;
  role: string;
  online: boolean;
  last_active_at: string | null;
  days: number;
  summary: { runs: number; total_tokens: number; tool_calls: number; llm_calls: number };
  daily: { date: string; runs: number; tokens: number; tool_calls: number }[];
  tool_distribution: { name: string; value: number }[];
  mode_distribution: { name: string; value: number }[];
  model_distribution: { name: string; value: number }[];
  recent_sessions: { session_id: string; updated_at: string | null }[];
}

export const getUserAnalytics = (userId: number, days = 30) =>
  apiFetch<UserAnalyticsDetail>(
    `${API}/admin/user-analytics/${userId}${qs({ days })}`,
    {},
    '加载用户详情失败',
  );
