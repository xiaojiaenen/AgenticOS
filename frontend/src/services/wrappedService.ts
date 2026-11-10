import { apiFetch, API_BASE_URL } from './apiClient';

const API = `${API_BASE_URL}/api/v1`;

export interface WrappedData {
  year: number;
  user_id: number;
  user_name: string;
  has_data: boolean;
  total_runs: number;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  tool_calls: number;
  llm_calls: number;
  conversation_count: number;
  active_days: number;
  longest_streak: number;
  total_hours: number;
  persona: string;
  top_mode: string | null;
  top_mode_name: string | null;
  busiest_hour: number | null;
  busiest_weekday: string | null;
  first_activity: string | null;
  last_activity: string | null;
  mode_distribution: { name: string; value: number }[];
  top_tools: { name: string; count: number }[];
  top_models: { name: string; count: number }[];
}

export const getWrapped = (year: number) =>
  apiFetch<WrappedData>(`${API}/wrapped/${year}`, {}, '加载年度报告失败');

export const getWrappedYears = () =>
  apiFetch<{ years: number[]; current_year: number }>(`${API}/wrapped/years`, {}, '加载年份失败');