import { authHeaders } from './authService';

export type AgentMode = 'general' | 'ppt' | 'website';

export type ToolCatalogItem = {
  name: string;
  label: string;
  description: string;
  approval_scope: string[];
};

export type AgentModeToolConfig = {
  mode: AgentMode;
  tool_name: string;
  enabled: boolean;
  requires_approval: boolean;
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
      })),
    }),
  });
  return parseResponse<ToolConfigResponse>(response);
}
