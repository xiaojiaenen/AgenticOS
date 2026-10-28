/**
 * MCP 服务器管理（MCP = Model Context Protocol，Agent 接入外部工具的事实标准）。
 */
import { apiFetch } from './apiClient';

export type MCPServer = {
  id: number;
  name: string;
  description: string;
  transport: 'stdio' | 'http' | 'sse';
  url?: string | null;
  command?: string | null;
  args: string[];
  env: Record<string, string>;
  headers: Record<string, string>;
  timeout: number;
  enabled: boolean;
  /** 是否校验 TLS 证书。内网自签证书需置 false。 */
  verify_tls: boolean;
  /** 平台连接本服务时允许的网段（CIDR 逗号分隔）。留空 = 不限制。 */
  allowed_cidrs: string;
  /** 是否允许被普通智能体使用。false 时须在智能体上显式授权。 */
  user_accessible: boolean;
  /** 凭据来源集成 id。$CREDENTIAL.<字段> 从该集成的用户凭据注入。 */
  external_system_id?: number | null;
  last_error?: string | null;
  last_connected_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type MCPTool = {
  name: string;
  label: string;
  description: string;
  source: string;
};

export type MCPServerPayload = {
  name: string;
  description?: string;
  transport: MCPServer['transport'];
  url?: string | null;
  command?: string | null;
  args?: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  timeout?: number;
  enabled?: boolean;
  /** 不传 = 保持原值（避免保存其他字段时把自签证书设置重置回校验）。 */
  verify_tls?: boolean;
  allowed_cidrs?: string;
  user_accessible?: boolean;
  external_system_id?: number | null;
};

export type ProfileMCPRef = {
  server_name: string;
  enabled: boolean;
};

export async function getMcpServers(): Promise<{ items: MCPServer[] }> {
  return apiFetch<{ items: MCPServer[] }>('/api/v1/admin/mcp/servers', {}, '加载 MCP 服务器失败');
}

export async function upsertMcpServer(payload: MCPServerPayload): Promise<MCPServer> {
  return apiFetch<MCPServer>(
    '/api/v1/admin/mcp/servers',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      timeoutMs: 30_000,
    },
    '保存 MCP 服务器失败',
  );
}

export async function deleteMcpServer(name: string): Promise<void> {
  return apiFetch<void>(
    `/api/v1/admin/mcp/servers/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
    '删除 MCP 服务器失败',
  );
}

export async function connectMcpServers(): Promise<{
  connected: boolean;
  error?: string | null;
  tools: MCPTool[];
}> {
  return apiFetch(
    '/api/v1/admin/mcp/connect',
    { method: 'POST', timeoutMs: 120_000 },
    '连接 MCP 服务器失败',
  );
}

export async function getMcpTools(): Promise<{
  connected: boolean;
  error?: string | null;
  tools: MCPTool[];
}> {
  return apiFetch('/api/v1/admin/mcp/tools', {}, '加载 MCP 工具失败');
}

export async function getProfileMcpServers(profileId: number): Promise<{ items: ProfileMCPRef[] }> {
  return apiFetch<{ items: ProfileMCPRef[] }>(
    `/api/v1/admin/mcp/profiles/${profileId}/servers`,
    {},
    '加载智能体的 MCP 授权失败',
  );
}

export async function setProfileMcpServers(
  profileId: number,
  servers: ProfileMCPRef[],
): Promise<{ items: ProfileMCPRef[] }> {
  return apiFetch<{ items: ProfileMCPRef[] }>(
    `/api/v1/admin/mcp/profiles/${profileId}/servers`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ servers }),
    },
    '保存智能体的 MCP 授权失败',
  );
}
