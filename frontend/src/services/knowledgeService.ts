/**
 * 知识库 API 服务
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const KB_ENDPOINT = `${API_BASE_URL}/api/v1/knowledge`;

import { authHeaders } from './authService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface KnowledgeBase {
  id: number;
  name: string;
  slug: string;
  description: string;
  purpose: string;
  scope: 'org' | 'team' | 'personal';
  visibility: 'public' | 'restricted' | 'private';
  is_active: boolean;
  owner_id: number;
  document_count: number;
  page_count: number;
  created_at: string;
  updated_at: string;
}

export interface KBDocument {
  id: number;
  knowledge_base_id: number;
  title: string;
  file_type: string;
  file_size: number;
  status: 'pending' | 'compiling' | 'compiled' | 'failed';
  compiled_at: string | null;
  error_message: string | null;
  created_at: string;
}

export interface WikiPage {
  id: number;
  knowledge_base_id: number;
  title: string;
  slug: string;
  page_type: string;
  content: string;
  sources: string[];
  authority_level: string;
  created_at: string;
  updated_at: string;
}

export interface SearchResult {
  page_id: number;
  title: string;
  content: string;
  page_type: string;
  score: number;
  sources: string[];
  authority_level: string;
}

export interface ReviewItem {
  id: number;
  knowledge_base_id: number;
  review_type: string;
  title: string;
  description: string;
  options: { action: string; label: string }[];
  status: string;
  resolved_by: number | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
}

export interface KnowledgeBasePayload {
  name: string;
  slug?: string;
  description?: string;
  purpose?: string;
  scope?: 'org' | 'team' | 'personal';
  visibility?: 'public' | 'restricted' | 'private';
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function parseResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  if (response.ok) return JSON.parse(raw) as T;
  let message = `请求失败 (${response.status})`;
  try {
    const err = JSON.parse(raw);
    if (err.detail) message = typeof err.detail === 'string' ? err.detail : err.detail.message || message;
  } catch {
    if (raw) message = raw;
  }
  throw new Error(message);
}

// ---------------------------------------------------------------------------
// Knowledge Base CRUD
// ---------------------------------------------------------------------------

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  const res = await fetch(`${KB_ENDPOINT}/bases`, {
    headers: { ...authHeaders() },
  });
  return parseResponse<KnowledgeBase[]>(res);
}

export async function createKnowledgeBase(payload: KnowledgeBasePayload): Promise<KnowledgeBase> {
  const res = await fetch(`${KB_ENDPOINT}/bases`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<KnowledgeBase>(res);
}

export async function updateKnowledgeBase(id: number, payload: Partial<KnowledgeBasePayload>): Promise<KnowledgeBase> {
  const res = await fetch(`${KB_ENDPOINT}/bases/${id}`, {
    method: 'PATCH',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return parseResponse<KnowledgeBase>(res);
}

export async function deleteKnowledgeBase(id: number): Promise<void> {
  const res = await fetch(`${KB_ENDPOINT}/bases/${id}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });
  if (!res.ok && res.status !== 204) throw new Error(`删除失败 (${res.status})`);
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function getDocuments(kbId: number): Promise<KBDocument[]> {
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/documents`, {
    headers: { ...authHeaders() },
  });
  return parseResponse<KBDocument[]>(res);
}

export async function uploadDocument(kbId: number, file: File): Promise<KBDocument> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/documents`, {
    method: 'POST',
    headers: { ...authHeaders() },
    body: form,
  });
  return parseResponse<KBDocument>(res);
}

export async function deleteDocument(kbId: number, docId: number): Promise<void> {
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/documents/${docId}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });
  if (!res.ok && res.status !== 204) throw new Error(`删除失败 (${res.status})`);
}

// ---------------------------------------------------------------------------
// Wiki Pages
// ---------------------------------------------------------------------------

export async function getWikiPages(kbId: number, pageType?: string): Promise<WikiPage[]> {
  const params = pageType ? `?page_type=${encodeURIComponent(pageType)}` : '';
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/wiki/pages${params}`, {
    headers: { ...authHeaders() },
  });
  return parseResponse<WikiPage[]>(res);
}

export async function getWikiPage(kbId: number, pageId: number): Promise<WikiPage> {
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/wiki/pages/${pageId}`, {
    headers: { ...authHeaders() },
  });
  return parseResponse<WikiPage>(res);
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export async function searchKnowledgeBase(
  kbId: number,
  query: string,
  maxResults = 10,
): Promise<SearchResult[]> {
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/search`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, max_results: maxResults }),
  });
  return parseResponse<SearchResult[]>(res);
}

// ---------------------------------------------------------------------------
// Reviews
// ---------------------------------------------------------------------------

export async function getReviewItems(kbId: number, status?: string): Promise<ReviewItem[]> {
  const params = status ? `?status_filter=${encodeURIComponent(status)}` : '';
  const res = await fetch(`${KB_ENDPOINT}/bases/${kbId}/reviews${params}`, {
    headers: { ...authHeaders() },
  });
  return parseResponse<ReviewItem[]>(res);
}
