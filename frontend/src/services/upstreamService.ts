import { apiFetch } from './apiClient';

const API = '/api/v1';

export type UpstreamCredentialStatus = {
  id: number;
  user_id: number;
  username: string;
  upstream: string;
  base_url: string;
  login_url: string;
  status: string;
  auto_refresh: boolean;
  expire_at: string | null;
  healthy: boolean;
  last_login_at: string | null;
  last_error: string | null;
  updated_at: string | null;
};

export type UpstreamHealth = {
  base_url: string;
  login_url: string;
  reachable?: boolean;
  http_status?: number;
  error?: string;
  has_cookie?: boolean;
  models_ok?: boolean;
  models_error?: string;
};

export type UpstreamStatusResponse = {
  upstream: string;
  base_url: string;
  login_url: string;
  auto_login_enabled: boolean;
  use_cookie_llm: boolean;
  mine: UpstreamCredentialStatus | null;
  health: UpstreamHealth;
  items: UpstreamCredentialStatus[];
};

export type UpstreamReloginResult = {
  success: boolean;
  message: string;
  user_id: number;
  upstream?: string;
  login_url?: string;
  expire_at?: string | null;
  has_cookie?: boolean;
  renewed?: boolean;
};

export type UpstreamApiKey = {
  id: number;
  user_id: number;
  name: string;
  prefix: string;
  key_masked?: string;
  key?: string;
  enabled: boolean;
  last_used_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  return apiFetch<T>(
    `${API}${path}`,
    {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...(init?.headers || {}),
      },
    },
    '请求失败',
  );
}

export function getUpstreamStatus(): Promise<UpstreamStatusResponse> {
  return request<UpstreamStatusResponse>('/upstream/status');
}

export function listUpstreamApiKeys(): Promise<{ items: UpstreamApiKey[] }> {
  return request('/upstream/api-keys');
}

export function createUpstreamApiKey(name: string): Promise<UpstreamApiKey> {
  return request<UpstreamApiKey>('/upstream/api-keys', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function revokeUpstreamApiKey(id: number): Promise<{ success: boolean }> {
  return request(`/upstream/api-keys/${id}`, { method: 'DELETE' });
}

export function setUpstreamApiKeyEnabled(id: number, enabled: boolean): Promise<UpstreamApiKey> {
  return request<UpstreamApiKey>(`/upstream/api-keys/${id}/enabled`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export function adminListUpstreamCredentials(): Promise<{ upstream: string; items: UpstreamCredentialStatus[] }> {
  return request('/upstream/admin/credentials');
}
