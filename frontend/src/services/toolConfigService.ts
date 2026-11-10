import { apiFetch } from './apiClient';

export type AgentMode = 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'office';

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

/**
 * 工具名 → 中文标签。对话页显示的是内部工具名（read_text_file 之类），
 * 直接展示对用户毫无意义。这份映射由后端 TOOL_CATALOG 提供，避免前后端
 * 各维护一份中文名而漂移。
 */
export type ToolLabelMap = Record<string, string>;

/** 轻量目录（只含 label），所有登录用户可读；模块级缓存，整个会话只拉一次。 */
let toolLabelsPromise: Promise<ToolLabelMap> | null = null;

export function loadToolLabels(): Promise<ToolLabelMap> {
  if (!toolLabelsPromise) {
    toolLabelsPromise = apiFetch<{ labels: ToolLabelMap }>(
      `${TOOL_CONFIG_ENDPOINT}/catalog/labels`,
      {},
      '加载工具名称失败',
    )
      .then((res) => res.labels ?? {})
      .catch((err) => {
        // 失败不缓存，下次进对话页重试；这里返回空表让界面退回原始工具名
        toolLabelsPromise = null;
        throw err;
      });
  }
  return toolLabelsPromise;
}

export async function updateModeToolConfig(
  mode: AgentMode,
  tools: AgentModeToolConfig[],
): Promise<ToolConfigResponse> {
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
