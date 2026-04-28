import { authHeaders } from './authService';

export type DashboardSummary = {
  total_users: number;
  active_users: number;
  total_sessions: number;
  total_runs: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  avg_latency_ms: number;
};

export type DashboardTrendPoint = {
  date: string;
  runs: number;
  tokens: number;
  tool_calls: number;
};

export type DashboardDistributionItem = {
  name: string;
  value: number;
};

export type DashboardUserUsage = {
  user_id: number;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  sessions: number;
  runs: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  avg_latency_ms: number;
};

export type DashboardStats = {
  summary: DashboardSummary;
  trend: DashboardTrendPoint[];
  model_distribution: DashboardDistributionItem[];
  tool_distribution: DashboardDistributionItem[];
  user_usage: DashboardUserUsage[];
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

export async function getDashboardStats(): Promise<DashboardStats> {
  const response = await fetch(`${DASHBOARD_ENDPOINT}/stats`, {
    headers: authHeaders(),
  });
  return parseResponse<DashboardStats>(response);
}
