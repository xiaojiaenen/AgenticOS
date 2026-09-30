import { apiFetch } from './apiClient';

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

export async function getDashboardStats(days?: number): Promise<DashboardStats> {
  const qs = days ? `?days=${days}` : "";
  return apiFetch<DashboardStats>(`${DASHBOARD_ENDPOINT}/stats${qs}`, {}, '仪表盘数据加载失败');
}

export type AnalyticsTimelinePoint = { date: string; count: number };
export type AnalyticsHourlyPoint = { hour: number; count: number };
export type AnalyticsModePoint = { mode: string; count: number };

export type AnalyticsData = {
  session_timeline: AnalyticsTimelinePoint[];
  hourly_distribution: AnalyticsHourlyPoint[];
  tool_frequency: Record<string, number>;
  mode_distribution: AnalyticsModePoint[];
};

export async function getAnalytics(days?: number): Promise<AnalyticsData> {
  const qs = days ? `?days=${days}` : '';
  return apiFetch<AnalyticsData>(`${DASHBOARD_ENDPOINT}/analytics${qs}`, {}, '分析数据加载失败');
}
