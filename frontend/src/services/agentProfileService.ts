import { authHeaders } from './authService';
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

export async function getAgentProfiles(): Promise<AgentProfileListResponse> {
  const response = await fetch(AGENT_PROFILES_ENDPOINT, { headers: authHeaders() });
  return parseResponse<AgentProfileListResponse>(response);
}

export async function createAgentProfile(payload: AgentProfilePayload): Promise<AgentProfile> {
  const response = await fetch(AGENT_PROFILES_ENDPOINT, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<AgentProfile>(response);
}

export async function updateAgentProfile(profileId: number, payload: Partial<AgentProfilePayload>): Promise<AgentProfile> {
  const response = await fetch(`${AGENT_PROFILES_ENDPOINT}/${profileId}`, {
    method: 'PATCH',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<AgentProfile>(response);
}

export async function deleteAgentProfile(profileId: number): Promise<void> {
  const response = await fetch(`${AGENT_PROFILES_ENDPOINT}/${profileId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}

export async function getAgentStore(): Promise<AgentProfileListResponse> {
  const response = await fetch(AGENT_STORE_ENDPOINT, { headers: authHeaders() });
  return parseResponse<AgentProfileListResponse>(response);
}

export async function installAgent(profileId: number): Promise<AgentProfile> {
  const response = await fetch(`${AGENT_STORE_ENDPOINT}/${profileId}/install`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return parseResponse<AgentProfile>(response);
}

export async function uninstallAgent(profileId: number): Promise<void> {
  const response = await fetch(`${AGENT_STORE_ENDPOINT}/${profileId}/install`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}

export async function getMyAgents(): Promise<AgentProfileListResponse> {
  const response = await fetch(MY_AGENTS_ENDPOINT, { headers: authHeaders() });
  return parseResponse<AgentProfileListResponse>(response);
}
