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
