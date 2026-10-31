/**
 * LLMOps 服务：运行追踪 / 消息标注 / Prompt 版本 / 发布为应用 / 评测。
 * 后端见 backend/app/api/v1/endpoints/llmops.py。
 */
import { apiFetch } from './apiClient';

const API = '/api/v1';

export interface TraceStep {
  kind: string;
  name: string;
  ts_ms: number;
  detail: string;
}

export interface TraceSummary {
  id: number;
  session_id: string;
  user_id: number | null;
  agent_profile_id: number | null;
  mode: string;
  status: 'running' | 'done' | 'error';
  text_chars: number;
  reasoning_chars: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  steps?: TraceStep[];
}

export async function listTraces(params?: { session_id?: string; limit?: number; offset?: number }) {
  const search = new URLSearchParams();
  if (params?.session_id) search.set('session_id', params.session_id);
  search.set('limit', String(params?.limit ?? 50));
  search.set('offset', String(params?.offset ?? 0));
  return apiFetch<{ items: TraceSummary[]; total: number }>(
    `${API}/agent/traces?${search.toString()}`,
    {},
    '获取运行追踪失败',
  );
}

export async function getTrace(id: number) {
  return apiFetch<TraceSummary>(`${API}/agent/traces/${id}`, {}, '获取追踪详情失败');
}

export async function submitFeedback(payload: {
  session_id: string;
  message_index: number;
  rating: 'up' | 'down';
  comment?: string;
  fingerprint?: string;
}) {
  return apiFetch<{ success: boolean; id: number }>(
    `${API}/agent/feedback`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    '提交反馈失败',
  );
}

// ── Prompt 版本 ──

export interface ProfileVersion {
  id: number;
  version: number;
  note: string | null;
  created_by: number | null;
  created_at: string | null;
}

export const saveProfileVersion = (profileId: number, note?: string) =>
  apiFetch<{ success: boolean; version: number }>(
    `${API}/agent/profiles/${profileId}/versions/save`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note }) },
    '保存版本失败',
  );

export const listProfileVersions = (profileId: number) =>
  apiFetch<{ items: ProfileVersion[] }>(`${API}/agent/profiles/${profileId}/versions`, {}, '获取版本失败');

export const restoreProfileVersion = (profileId: number, version: number) =>
  apiFetch<{ success: boolean }>(
    `${API}/agent/profiles/${profileId}/versions/${version}/restore`,
    { method: 'POST' },
    '回滚失败',
  );

// ── 发布为应用 ──

export interface PublishStatus {
  published: boolean;
  slug: string | null;
  chat_url: string | null;
  config: { title: string; welcome: string; has_access_code: boolean };
}

export const getPublishStatus = (profileId: number) =>
  apiFetch<PublishStatus>(`${API}/agent/profiles/${profileId}/publish`, {}, '获取发布状态失败');

export const publishProfile = (
  profileId: number,
  payload: { title?: string; welcome?: string; access_code?: string },
) =>
  apiFetch<{ success: boolean; slug: string; chat_url: string; widget_url: string }>(
    `${API}/agent/profiles/${profileId}/publish`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    '发布失败',
  );

export const unpublishProfile = (profileId: number) =>
  apiFetch<{ success: boolean }>(`${API}/agent/profiles/${profileId}/publish`, { method: 'DELETE' }, '下线失败');

// ── 评测 ──

export interface EvalDataset {
  id: number;
  name: string;
  description: string;
  case_count: number;
  created_at: string | null;
}

export interface EvalCase {
  id: number;
  input: string;
  expected: { contains?: string[]; not_contains?: string[] };
  note?: string | null;
}

export interface EvalCaseResult {
  case_id: number;
  input: string;
  output: string;
  passed: boolean;
  reason: string | null;
  error: string | null;
  duration_ms: number;
  tool_calls: number;
}

export interface EvalRun {
  id: number;
  dataset_id: number;
  profile_id: number;
  status: 'running' | 'done' | 'error';
  total: number;
  passed: number;
  results?: EvalCaseResult[];
  error?: string | null;
  created_at: string | null;
  finished_at: string | null;
}

export const listEvalDatasets = () =>
  apiFetch<{ items: EvalDataset[] }>(`${API}/agent/evals/datasets`, {}, '获取数据集失败');

export const createEvalDataset = (payload: { name: string; description?: string }) =>
  apiFetch<{ id: number; name: string }>(
    `${API}/agent/evals/datasets`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    '创建数据集失败',
  );

export const deleteEvalDataset = (id: number) =>
  apiFetch<{ success: boolean }>(`${API}/agent/evals/datasets/${id}`, { method: 'DELETE' }, '删除失败');

export const getEvalDataset = (id: number) =>
  apiFetch<{ id: number; name: string; description: string; cases: EvalCase[] }>(
    `${API}/agent/evals/datasets/${id}`,
    {},
    '获取数据集失败',
  );

export const addEvalCase = (
  datasetId: number,
  payload: { input: string; expected?: EvalCase['expected']; note?: string },
) =>
  apiFetch<{ id: number }>(
    `${API}/agent/evals/datasets/${datasetId}/cases`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) },
    '添加用例失败',
  );

export const deleteEvalCase = (caseId: number) =>
  apiFetch<{ success: boolean }>(`${API}/agent/evals/cases/${caseId}`, { method: 'DELETE' }, '删除失败');

export const startEvalRun = (datasetId: number, profileId: number) =>
  apiFetch<{ run_id: number; status: string }>(
    `${API}/agent/evals/datasets/${datasetId}/run`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_id: profileId }) },
    '启动评测失败',
  );

export const getEvalRun = (runId: number) =>
  apiFetch<EvalRun>(`${API}/agent/evals/runs/${runId}`, {}, '获取评测结果失败');

export const listEvalRuns = (datasetId?: number) => {
  const search = new URLSearchParams();
  if (datasetId) search.set('dataset_id', String(datasetId));
  return apiFetch<{ items: EvalRun[] }>(`${API}/agent/evals/runs?${search.toString()}`, {}, '获取评测记录失败');
};
