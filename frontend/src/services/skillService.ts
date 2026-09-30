import { apiFetch } from './apiClient';

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
  has_references: boolean;
  reference_paths: string[];
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

export async function getSkills(): Promise<SkillListResponse> {
  return apiFetch<SkillListResponse>(SKILLS_ENDPOINT, {}, '技能列表加载失败');
}

export async function createSkill(payload: SkillPayload): Promise<Skill> {
  return apiFetch<Skill>(
    SKILLS_ENDPOINT,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '创建技能失败',
  );
}

export async function updateSkill(skillId: number, payload: Partial<SkillPayload>): Promise<Skill> {
  return apiFetch<Skill>(
    `${SKILLS_ENDPOINT}/${skillId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '更新技能失败',
  );
}

export async function deleteSkill(skillId: number): Promise<void> {
  await apiFetch<void>(`${SKILLS_ENDPOINT}/${skillId}`, { method: 'DELETE' }, '删除技能失败');
}

export type SkillUploadResponse = Skill | { items: Skill[]; count: number };

export async function uploadSkill(file: File, slug?: string, enabled = true): Promise<SkillUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (slug) formData.append('slug', slug);
  formData.append('enabled', String(enabled));

  return apiFetch<SkillUploadResponse>(
    `${SKILLS_ENDPOINT}/upload`,
    {
      method: 'POST',
      body: formData,
    },
    '上传技能失败',
  );
}
