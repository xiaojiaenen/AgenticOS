import { apiFetch } from './apiClient';

export type AgentMode = 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'sheet';

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

export async function getToolConfig(): Promise<ToolConfigResponse> {
  return apiFetch<ToolConfigResponse>(TOOL_CONFIG_ENDPOINT, {}, '工具配置加载失败');
}

export async function updateModeToolConfig(mode: AgentMode, tools: AgentModeToolConfig[]): Promise<ToolConfigResponse> {
  return apiFetch<ToolConfigResponse>(
    `${TOOL_CONFIG_ENDPOINT}/modes/${mode}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tools: tools.map((tool) => ({
          tool_name: tool.tool_name,
          enabled: tool.enabled,
          requires_approval: tool.requires_approval,
          approval_sub_tools: tool.approval_sub_tools,
        })),
      }),
    },
    '工具配置更新失败',
  );
}
