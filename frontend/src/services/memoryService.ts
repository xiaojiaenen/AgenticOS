import { authHeaders } from './authService';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const MEMORY_ENDPOINT = `${API_BASE_URL}/api/v1/memory`;

export type MemoryItem = {
  id: string;
  content: string;
  memory_type: string;
  importance: number;
  tags: string[];
  created_at: string | null;
};

export type MemoryResponse = {
  items: MemoryItem[];
  count: number;
};

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

export async function getMemories(): Promise<MemoryResponse> {
  const response = await fetch(MEMORY_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse<MemoryResponse>(response);
}

export async function searchMemories(query: string, limit = 5): Promise<MemoryResponse> {
  const response = await fetch(`${MEMORY_ENDPOINT}/search?q=${encodeURIComponent(query)}&limit=${limit}`, {
    headers: authHeaders(),
  });
  return parseResponse<MemoryResponse>(response);
}

export async function deleteMemory(memoryId: string): Promise<void> {
  const response = await fetch(`${MEMORY_ENDPOINT}/${memoryId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}
