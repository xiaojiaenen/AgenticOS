/**
 * 工作流服务：CRUD / 运行 / 运行记录 / 人工输入恢复。
 * 后端见 backend/app/api/v1/endpoints/workflows.py。
 */
import { apiFetch } from './apiClient';

const API = '/api/v1';

export interface WorkflowGraphNode {
  id: string;
  type: string;
  params?: Record<string, unknown>;
}

export interface WorkflowGraphEdge {
  from: string;
  to: string;
  label?: string;
}

export interface WorkflowGraph {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
}

export interface WorkflowSummary {
  id: number;
  name: string;
  description: string;
  enabled: boolean;
  node_count: number;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Workflow extends WorkflowSummary {
  graph: WorkflowGraph;
}

export interface WorkflowStepTrace {
  node_id: string;
  type: string;
  status: 'done' | 'failed' | 'skipped';
  duration_ms: number;
  output_preview: string | null;
  error: string | null;
}

export interface WorkflowRun {
  id: number;
  workflow_id: number;
  status: 'running' | 'waiting_input' | 'succeeded' | 'failed';
  error: string | null;
  waiting_node_id: string | null;
  waiting_prompt: string | null;
  triggered_by: number | null;
  started_at: string | null;
  finished_at: string | null;
  steps?: WorkflowStepTrace[];
  outputs?: unknown;
  inputs?: unknown;
}

export async function listWorkflows() {
  return apiFetch<{ items: WorkflowSummary[]; total: number }>(
    `${API}/workflows`,
    {},
    '获取工作流列表失败',
  );
}

export async function getWorkflow(id: number) {
  return apiFetch<Workflow>(`${API}/workflows/${id}`, {}, '获取工作流详情失败');
}

export async function createWorkflow(payload: {
  name: string;
  description: string;
  graph: WorkflowGraph;
  enabled: boolean;
}) {
  return apiFetch<Workflow>(
    `${API}/workflows`,
    { method: 'POST', body: JSON.stringify(payload) },
    '创建工作流失败',
  );
}

export async function updateWorkflow(
  id: number,
  payload: { name: string; description: string; graph: WorkflowGraph; enabled: boolean },
) {
  return apiFetch<Workflow>(
    `${API}/workflows/${id}`,
    { method: 'PUT', body: JSON.stringify(payload) },
    '保存工作流失败',
  );
}

export async function setWorkflowEnabled(id: number, enabled: boolean) {
  return apiFetch<{ id: number; enabled: boolean }>(
    `${API}/workflows/${id}/enabled`,
    { method: 'PUT', body: JSON.stringify({ enabled }) },
    '更新工作流状态失败',
  );
}

export async function deleteWorkflow(id: number) {
  return apiFetch<{ deleted: boolean; id: number }>(
    `${API}/workflows/${id}`,
    { method: 'DELETE' },
    '删除工作流失败',
  );
}

export async function runWorkflow(id: number, inputs: Record<string, unknown>) {
  return apiFetch<WorkflowRun>(
    `${API}/workflows/${id}/run`,
    { method: 'POST', body: JSON.stringify({ inputs }), timeoutMs: 360_000 },
    '运行工作流失败',
  );
}

export async function listWorkflowRuns(id: number) {
  return apiFetch<{ items: WorkflowRun[]; total: number }>(
    `${API}/workflows/${id}/runs`,
    {},
    '获取运行记录失败',
  );
}

export async function getWorkflowRun(runId: number) {
  return apiFetch<WorkflowRun>(`${API}/workflows/runs/${runId}`, {}, '获取运行详情失败');
}

export async function resumeWorkflowRun(runId: number, value: unknown) {
  return apiFetch<WorkflowRun>(
    `${API}/workflows/runs/${runId}/resume`,
    { method: 'POST', body: JSON.stringify({ value }), timeoutMs: 360_000 },
    '恢复运行失败',
  );
}
