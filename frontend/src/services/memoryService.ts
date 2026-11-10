import { apiFetch } from './apiClient';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const MEMORY_ENDPOINT = `${API_BASE_URL}/api/v1/memory`;

export type MemoryItem = {
  id: number;
  user_id?: number;
  content: string;
  memory_type: string;
  importance: number;
  tags: string[];
  source?: string;
  layer?: string;
  scenario_id?: number | null;
  access_count?: number;
  visibility?: string;
  created_at: string | null;
};

export type MemoryResponse = {
  items: MemoryItem[];
  count: number;
  /** 应用过滤（q / user_id）后的全量条数，分页控件的总页数依据 */
  total?: number;
};

export type MemoryListParams = {
  /** 管理员可指定用户；不传 = 自己（admin 则为全部用户） */
  userId?: number;
  limit?: number;
  offset?: number;
  /** 按内容模糊过滤（服务端执行，配合分页） */
  q?: string;
};

export async function getMemories(params: MemoryListParams | number = {}): Promise<MemoryResponse> {
  // 兼容旧签名 getMemories(userId?: number)
  const opts: MemoryListParams = typeof params === 'number' ? { userId: params } : params;
  const search = new URLSearchParams();
  if (opts.userId) search.set('user_id', String(opts.userId));
  if (opts.limit) search.set('limit', String(opts.limit));
  if (opts.offset) search.set('offset', String(opts.offset));
  if (opts.q?.trim()) search.set('q', opts.q.trim());
  const qs = search.toString();
  return apiFetch<MemoryResponse>(`${MEMORY_ENDPOINT}${qs ? `?${qs}` : ''}`, {}, '记忆列表加载失败');
}

export async function searchMemories(query: string, limit = 5, userId?: number): Promise<MemoryResponse> {
  let url = `${MEMORY_ENDPOINT}/search?q=${encodeURIComponent(query)}&limit=${limit}`;
  if (userId) url += `&user_id=${userId}`;
  return apiFetch<MemoryResponse>(url, {}, '记忆搜索失败');
}

export async function deleteMemory(memoryId: number): Promise<void> {
  await apiFetch<void>(`${MEMORY_ENDPOINT}/${memoryId}`, { method: 'DELETE' }, '删除记忆失败');
}

/** 批量删除：部分成功优于整批失败（越界/他人 id 记在 missing 里返回） */
export async function batchDeleteMemories(
  ids: number[],
): Promise<{ success: boolean; deleted: number; missing: number[] }> {
  return apiFetch<{ success: boolean; deleted: number; missing: number[] }>(
    `${MEMORY_ENDPOINT}/batch-delete`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) },
    '批量删除失败',
  );
}

/**
 * 对既有记忆做一次向量相似度聚类去重。
 * 历史遗留：早期蒸馏管线没有去重闸，同一句"项目代号是 ORION"存了 6 遍。
 */
export async function dedupeMemories(
  userId?: number,
  dryRun = false,
): Promise<{ success: boolean; user_id: number; groups: number; removed: number; kept: number }> {
  const search = new URLSearchParams({ dry_run: String(dryRun) });
  if (userId) search.set('user_id', String(userId));
  return apiFetch(
    `${MEMORY_ENDPOINT}/dedupe?${search.toString()}`,
    { method: 'POST' },
    '记忆去重失败',
  );
}

/**
 * 创建记忆。
 * 后端 memory.py POST /memory 的参数为简单标量（无 Body 注解），
 * FastAPI 将其解析为 query string；发送 form body 会触发 422。
 * 因此改为 query 参数。
 */
export async function createMemory(
  content: string,
  memoryType: string = 'fact',
  importance: number = 0.5,
): Promise<{ id: number; success: boolean }> {
  const params = new URLSearchParams({
    content,
    memory_type: memoryType,
    importance: String(importance),
  });
  return apiFetch<{ id: number; success: boolean }>(
    `${MEMORY_ENDPOINT}?${params.toString()}`,
    { method: 'POST' },
    '创建记忆失败',
  );
}

export type PortraitProject = { name: string; status: string; summary: string };

export type Portrait = {
  has_persona: boolean;
  identity: { name?: string; role?: string; location?: string; age_group?: string };
  preferences: { ui_style?: string; communication?: string; likes?: string[]; dislikes?: string[] };
  tech_stack: string[];
  goals: string[];
  projects: PortraitProject[];
  persona_updated_at: string | null;
  atom_count: number;
  atoms_by_type: Record<string, number>;
  scenario_count: number;
  days_known: number;
  memory_since: string | null;
  summary: string;
  recent_atoms: { id: number; content: string; memory_type: string; importance: number; created_at: string | null }[];
};

export async function getPortrait(): Promise<Portrait> {
  return apiFetch<Portrait>(`${MEMORY_ENDPOINT}/portrait`, {}, '加载画像失败');
}
