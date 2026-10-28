/**
 * API Key 管理：外部软件用 sk-agenticos-* 调用本平台的 OpenAI 兼容网关（/v1/*）。
 * 注意与「企业上游」无关——网关只路由到本地智能体，不存在上游透传。
 */
import { apiFetch } from './apiClient';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const API_KEYS_ENDPOINT = `${API_BASE_URL}/api/v1/api-keys`;

/** 外部软件应填写的 base_url（形如 https://平台地址/v1） */
export const GATEWAY_BASE_URL = `${
  API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : '')
}/v1`;

export type ApiKey = {
  id: number;
  user_id: number;
  name: string;
  /** 明文前 16 位，用于在列表中辨识 */
  prefix: string;
  /** 形如 sk-agenticos-AbCd…wxyz */
  key_masked: string;
  enabled: boolean;
  last_used_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  /** 归属人：管理员可见全部 Key 时需要，普通用户列表里同样带上 */
  owner_name?: string;
  owner_email?: string | null;
};

/** 创建响应额外带明文 key —— 仅在创建时返回一次，之后无法再取回 */
export type CreatedApiKey = ApiKey & { key: string };

export async function listApiKeys(): Promise<ApiKey[]> {
  const res = await apiFetch<{ items: ApiKey[] }>(API_KEYS_ENDPOINT, {}, '加载 API Key 列表失败');
  return res.items ?? [];
}

export async function createApiKey(name: string): Promise<CreatedApiKey> {
  return apiFetch<CreatedApiKey>(
    API_KEYS_ENDPOINT,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() || 'default' }),
    },
    '创建 API Key 失败',
  );
}

export async function setApiKeyEnabled(keyId: number, enabled: boolean): Promise<ApiKey> {
  return apiFetch<ApiKey>(
    `${API_KEYS_ENDPOINT}/${keyId}/enabled`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    },
    '更新 API Key 状态失败',
  );
}

export async function deleteApiKey(keyId: number): Promise<void> {
  await apiFetch<void>(`${API_KEYS_ENDPOINT}/${keyId}`, { method: 'DELETE' }, '删除 API Key 失败');
}
