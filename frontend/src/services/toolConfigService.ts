import { authHeaders } from './authService';

export type AgentMode = 'general' | 'ppt' | 'website' | 'video' | 'bigdata';

export type SubToolInfo = {
  name: string;
  label: string;
  description: string;
};

export type ToolCatalogItem = {
  name: string;
  label: string;
  description: string;
  approval_scope: string[];
  sub_tools: SubToolInfo[];
};

export type AgentModeToolConfig = {
  mode: AgentMode;
  tool_name: string;
  enabled: boolean;
  requires_approval: boolean;
  approval_sub_tools: string[];
};

export type AgentModeConfig = {
  mode: AgentMode;
  label: string;
  description: string;
  tools: AgentModeToolConfig[];
};

export type ToolConfigResponse = {
  catalog: ToolCatalogItem[];
  modes: AgentModeConfig[];
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const TOOL_CONFIG_ENDPOINT = `${API_BASE_URL}/api/v1/tool-config`;

async function parseResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  if (response.ok) return JSON.parse(raw) as T;
  let message = 'Request failed';
  try {
    const payload = JSON.parse(raw);
    if (typeof payload.detail === 'string') message = payload.detail;
  } catch {
    if (raw) message = raw;
  }
  throw new Error(message);
}

export async function getToolConfig(): Promise<ToolConfigResponse> {
  const response = await fetch(TOOL_CONFIG_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse<ToolConfigResponse>(response);
}

export async function updateModeToolConfig(mode: AgentMode, tools: AgentModeToolConfig[]): Promise<ToolConfigResponse> {
  const response = await fetch(`${TOOL_CONFIG_ENDPOINT}/modes/${mode}`, {
    method: 'PUT',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      tools: tools.map((tool) => ({
        tool_name: tool.tool_name,
        enabled: tool.enabled,
        requires_approval: tool.requires_approval,
        approval_sub_tools: tool.approval_sub_tools,
      })),
    }),
  });
  return parseResponse<ToolConfigResponse>(response);
}
