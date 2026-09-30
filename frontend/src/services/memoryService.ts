import { authHeaders } from './authService';

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
};

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

export async function getMemories(userId?: number): Promise<MemoryResponse> {
  const params = userId ? `?user_id=${userId}` : '';
  const response = await fetch(`${MEMORY_ENDPOINT}${params}`, {
    headers: authHeaders(),
  });
  return parseResponse<MemoryResponse>(response);
}

export async function searchMemories(query: string, limit = 5, userId?: number): Promise<MemoryResponse> {
  let url = `${MEMORY_ENDPOINT}/search?q=${encodeURIComponent(query)}&limit=${limit}`;
  if (userId) url += `&user_id=${userId}`;
  const response = await fetch(url, {
    headers: authHeaders(),
  });
  return parseResponse<MemoryResponse>(response);
}

export async function deleteMemory(memoryId: number): Promise<void> {
  const response = await fetch(`${MEMORY_ENDPOINT}/${memoryId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    await parseResponse(response);
  }
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
  const response = await fetch(`${MEMORY_ENDPOINT}?${params.toString()}`, {
    method: 'POST',
    headers: {
      ...authHeaders(),
    },
  });
  return parseResponse<{ id: number; success: boolean }>(response);
}
