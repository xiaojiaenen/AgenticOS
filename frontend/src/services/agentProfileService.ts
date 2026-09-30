import { apiFetch } from './apiClient';
import { AgentMode, ToolCatalogItem } from './toolConfigService';

export type AgentProfileTool = {
  tool_name: string;
  enabled: boolean;
  requires_approval: boolean;
  approval_sub_tools: string[];
};

export type AgentProfileSkill = {
  id: number;
  name: string;
  slug: string;
  description: string;
  enabled: boolean;
  has_python_scripts: boolean;
  script_paths: string[];
  has_references: boolean;
  reference_paths: string[];
};

export type AgentProfileAudienceUser = {
  id: number;
  name: string;
  email: string;
};

export type AgentProfile = {
  id: number;
  name: string;
  slug: string;
  description: string;
  system_prompt: string;
  response_mode: AgentMode;
  avatar?: string | null;
  enabled: boolean;
  listed: boolean;
  is_builtin: boolean;
  installed: boolean;
  audience_mode: 'all' | 'selected';
  audience_users: AgentProfileAudienceUser[];
  tools: AgentProfileTool[];
  skills: AgentProfileSkill[];
  external_systems?: { system_id: number; system_name: string; enabled: boolean }[];
  max_steps?: number | null;
  created_at: string;
  updated_at: string;
};

export type AgentProfileListResponse = {
  catalog: ToolCatalogItem[];
  available_skills: AgentProfileSkill[];
  items: AgentProfile[];
};

export type AgentProfilePayload = {
  name: string;
  slug?: string;
  description: string;
  system_prompt: string;
  response_mode: AgentMode;
  avatar?: string | null;
  enabled: boolean;
  listed: boolean;
  audience_mode: 'all' | 'selected';
  audience_user_ids: number[];
  tools: AgentProfileTool[];
  skill_ids: number[];
  external_systems?: { system_id: number; enabled: boolean }[];
  max_steps?: number | null;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const AGENT_PROFILES_ENDPOINT = `${API_BASE_URL}/api/v1/agent-profiles`;
const AGENT_STORE_ENDPOINT = `${API_BASE_URL}/api/v1/agent-store`;
const MY_AGENTS_ENDPOINT = `${API_BASE_URL}/api/v1/my/agents`;

export async function getAgentProfiles(): Promise<AgentProfileListResponse> {
  return apiFetch<AgentProfileListResponse>(AGENT_PROFILES_ENDPOINT, {}, '智能体配置加载失败');
}

export async function createAgentProfile(payload: AgentProfilePayload): Promise<AgentProfile> {
  return apiFetch<AgentProfile>(
    AGENT_PROFILES_ENDPOINT,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '创建智能体失败',
  );
}

export async function updateAgentProfile(profileId: number, payload: Partial<AgentProfilePayload>): Promise<AgentProfile> {
  return apiFetch<AgentProfile>(
    `${AGENT_PROFILES_ENDPOINT}/${profileId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '更新智能体失败',
  );
}

export async function deleteAgentProfile(profileId: number): Promise<void> {
  await apiFetch<void>(`${AGENT_PROFILES_ENDPOINT}/${profileId}`, { method: 'DELETE' }, '删除智能体失败');
}

export async function getAgentStore(): Promise<AgentProfileListResponse> {
  return apiFetch<AgentProfileListResponse>(AGENT_STORE_ENDPOINT, {}, '智能体商店加载失败');
}

export async function installAgent(profileId: number): Promise<AgentProfile> {
  return apiFetch<AgentProfile>(`${AGENT_STORE_ENDPOINT}/${profileId}/install`, { method: 'POST' }, '安装智能体失败');
}

export async function uninstallAgent(profileId: number): Promise<void> {
  await apiFetch<void>(`${AGENT_STORE_ENDPOINT}/${profileId}/install`, { method: 'DELETE' }, '卸载智能体失败');
}

export async function getMyAgents(): Promise<AgentProfileListResponse> {
  return apiFetch<AgentProfileListResponse>(MY_AGENTS_ENDPOINT, {}, '我的智能体加载失败');
}
