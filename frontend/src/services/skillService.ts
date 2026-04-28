import { authHeaders } from './authService';

export type Skill = {
  id: number;
  name: string;
  slug: string;
  description: string;
  enabled: boolean;
  instruction: string;
  root_dir: string;
  has_python_scripts: boolean;
  script_paths: string[];
  created_at: string;
  updated_at: string;
};

export type SkillListResponse = {
  items: Skill[];
};

export type SkillPayload = {
  name: string;
  slug?: string;
  description: string;
  enabled: boolean;
  instruction: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SKILLS_ENDPOINT = `${API_BASE_URL}/api/v1/skills`;

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

export async function getSkills(): Promise<SkillListResponse> {
  const response = await fetch(SKILLS_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse<SkillListResponse>(response);
}

export async function createSkill(payload: SkillPayload): Promise<Skill> {
  const response = await fetch(SKILLS_ENDPOINT, {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<Skill>(response);
}

export async function updateSkill(skillId: number, payload: Partial<SkillPayload>): Promise<Skill> {
  const response = await fetch(`${SKILLS_ENDPOINT}/${skillId}`, {
    method: 'PATCH',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<Skill>(response);
}

export async function deleteSkill(skillId: number): Promise<void> {
  const response = await fetch(`${SKILLS_ENDPOINT}/${skillId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}

export async function uploadSkill(file: File, slug?: string, enabled = true): Promise<Skill> {
  const formData = new FormData();
  formData.append('file', file);
  if (slug) formData.append('slug', slug);
  formData.append('enabled', String(enabled));

  const response = await fetch(`${SKILLS_ENDPOINT}/upload`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  return parseResponse<Skill>(response);
}
