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

/**
 * 用量路由审计（管理员排障视图）。
 *
 * 注意口径：这里的 token 数**不是分摊依据** —— 企业网关的账号是系统级共享池，
 * 一个号被多人共用，按号聚合出来的数字不能回推给任何个体。
 * 「谁用了多少」看 /stats 的 user_usage 或用户自己的 /my-usage。
 */
export type UsageRouteTotals = {
  runs: number;
  total_tokens: number;
  estimated_runs: number;
  /** 迁移前的历史行：没有路由信息，不能归到任何提供商头上 */
  legacy_runs: number;
  /** 走 .env 兜底的行：说明这些流量没经过提供商配置 */
  env_fallback_runs: number;
};

export type UsageRouteProvider = {
  provider_id: number | null;
  provider_slug: string | null;
  provider_name: string | null;
  runs: number;
  llm_calls: number;
  total_tokens: number;
  last_at: string | null;
};

export type UsageRouteAccount = {
  credential_id: number | null;
  account_label: string;
  provider_slug: string | null;
  runs: number;
  llm_calls: number;
  total_tokens: number;
  last_at: string | null;
};

export type UsageRouteModel = {
  name: string;
  runs: number;
  total_tokens: number;
};

export type UsageRoutesData = {
  days: number;
  totals: UsageRouteTotals;
  providers: UsageRouteProvider[];
  accounts: UsageRouteAccount[];
  models: UsageRouteModel[];
};

export async function getUsageRoutes(days?: number): Promise<UsageRoutesData> {
  const qs = days ? `?days=${days}` : '';
  return apiFetch<UsageRoutesData>(`${DASHBOARD_ENDPOINT}/usage-routes${qs}`, {}, '用量路由数据加载失败');
}

/**
 * 当前用户自己的 token 用量。
 *
 * 口径严格按 user_id 归属，**不包含**提供商 / 凭据信息 —— 企业网关的账号是
 * 系统级共享池，按账号聚合的数字对任何个体都不成立，暴露出来只会造成误解。
 */
export type MyUsageDailyPoint = {
  date: string;
  runs: number;
  tokens: number;
};

export type MyUsageModel = {
  name: string;
  tokens: number;
  runs: number;
};

export type MyUsageSession = {
  session_id: string;
  tokens: number;
  runs: number;
  last_at: string | null;
};

export type MyUsageData = {
  days: number;
  runs: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  tool_calls: number;
  /** 其中有多少次是估算值（上游没回流 usage） */
  estimated_runs: number;
  daily: MyUsageDailyPoint[];
  models: MyUsageModel[];
  sessions: MyUsageSession[];
};

export async function getMyUsage(days?: number): Promise<MyUsageData> {
  const qs = days ? `?days=${days}` : '';
  return apiFetch<MyUsageData>(`${DASHBOARD_ENDPOINT}/my-usage${qs}`, {}, '用量数据加载失败');
}
