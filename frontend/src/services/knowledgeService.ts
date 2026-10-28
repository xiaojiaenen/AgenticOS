/**
 * 知识库 API 服务
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const KB_ENDPOINT = `${API_BASE_URL}/api/v1/knowledge`;

import { apiFetch } from './apiClient';

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
  /** 0~1 的相对相关度（BM25 归一化 0.6 + 向量余弦 0.4） */
  score: number;
  sources: string[];
  authority_level: string;
  /** 页内与查询最相关的一段 */
  snippet?: string;
  /** 命中的通道：bm25 / vector */
  matched_by?: string[];
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

// ---------------------------------------------------------------------------
// Knowledge Base CRUD
// ---------------------------------------------------------------------------

export async function getKnowledgeBases(): Promise<KnowledgeBase[]> {
  return apiFetch<KnowledgeBase[]>(
          `${KB_ENDPOINT}/bases`,
          {
  }
        );}

export async function createKnowledgeBase(payload: KnowledgeBasePayload): Promise<KnowledgeBase> {
  return apiFetch<KnowledgeBase>(
          `${KB_ENDPOINT}/bases`,
          {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
        );}

export async function updateKnowledgeBase(id: number, payload: Partial<KnowledgeBasePayload>): Promise<KnowledgeBase> {
  return apiFetch<KnowledgeBase>(
          `${KB_ENDPOINT}/bases/${id}`,
          {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }
        );}

export async function deleteKnowledgeBase(id: number): Promise<void> {
  await apiFetch<unknown>(
          `${KB_ENDPOINT}/bases/${id}`,
          {
    method: 'DELETE',
  }
        );}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function getDocuments(kbId: number): Promise<KBDocument[]> {
  return apiFetch<KBDocument[]>(
          `${KB_ENDPOINT}/bases/${kbId}/documents`,
          {
  }
        );}

export async function uploadDocument(kbId: number, file: File): Promise<KBDocument> {
  const form = new FormData();
  form.append('file', file);
  return apiFetch<KBDocument>(
          `${KB_ENDPOINT}/bases/${kbId}/documents`,
          {
    method: 'POST',
    body: form,
  }
        );}

export async function deleteDocument(kbId: number, docId: number): Promise<void> {
  await apiFetch<unknown>(
          `${KB_ENDPOINT}/bases/${kbId}/documents/${docId}`,
          {
    method: 'DELETE',
  }
        );}

// ---------------------------------------------------------------------------
// Wiki Pages
// ---------------------------------------------------------------------------

export async function getWikiPages(kbId: number, pageType?: string): Promise<WikiPage[]> {
  const params = pageType ? `?page_type=${encodeURIComponent(pageType)}` : '';
  return apiFetch<WikiPage[]>(
          `${KB_ENDPOINT}/bases/${kbId}/wiki/pages${params}`,
          {
  }
        );}

export async function getWikiPage(kbId: number, pageId: number): Promise<WikiPage> {
  return apiFetch<WikiPage>(
          `${KB_ENDPOINT}/bases/${kbId}/wiki/pages/${pageId}`,
          {
  }
        );}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export async function searchKnowledgeBase(
  kbId: number,
  query: string,
  maxResults = 10,
): Promise<SearchResult[]> {
  return apiFetch<SearchResult[]>(
          `${KB_ENDPOINT}/bases/${kbId}/search`,
          {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, max_results: maxResults }),
  }
        );}

export type RecallTestCase = {
  question: string;
  hits: { page_id: number | null; title: string; score: number; page_type: string }[];
  matched: boolean;
  rank_of_first_expected: number | null;
  score_of_first_expected: number | null;
};

export type RecallReport = {
  total: number;
  matched: number;
  hit_rate: number;
  avg_rank: number | null;
  cases: RecallTestCase[];
  params: { top_k: number; score_threshold: number | null; page_type: string | null };
};

/**
 * 召回测试：跑一批问题并返回命中率报告。
 * questions 留空时后端用知识库页面标题自动生成探针问题。
 */
export async function runRecallTest(
  kbId: number,
  options: {
    questions?: string[];
    topK?: number;
    scoreThreshold?: number;
    pageType?: string;
  } = {},
): Promise<RecallReport> {
  return apiFetch<RecallReport>(
    `${KB_ENDPOINT}/bases/${kbId}/recall-test`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        questions: options.questions ?? [],
        top_k: options.topK ?? 5,
        score_threshold: options.scoreThreshold ?? null,
        page_type: options.pageType ?? null,
      }),
      timeoutMs: 120_000,
    },
    '召回测试失败',
  );
}

// ---------------------------------------------------------------------------
// Reindex（向量索引重建）
// ---------------------------------------------------------------------------

export interface ReindexStats {
  knowledge_base_id: number;
  checked: number;
  embedded: number;
  skipped: number;
  failed: number;
  /** 本次写入的段级切片数 */
  chunks?: number;
  /** 其中成功向量化的段数 */
  chunks_embedded?: number;
  enabled: boolean;
  message: string;
}

/**
 * 重建知识库向量索引与段级切片。
 * force=true 时全部重算（换过 embedding 模型后用）；否则只补「缺向量或缺切片」的页面。
 */
export async function reindexKnowledgeBase(
  kbId: number,
  options: { force?: boolean; limit?: number } = {},
): Promise<ReindexStats> {
  const params = new URLSearchParams();
  if (options.force) params.set('force', 'true');
  if (options.limit) params.set('limit', String(options.limit));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<ReindexStats>(
    `${KB_ENDPOINT}/bases/${kbId}/reindex${qs}`,
    { method: 'POST', timeoutMs: 600_000 },
    '重建索引失败',
  );
}

// ---------------------------------------------------------------------------
// 冲突巡检（跨页面配对扫描）
// ---------------------------------------------------------------------------

export interface ConflictScanStats {
  knowledge_base_id: number;
  pages_scanned: number;
  /** 通过「标题相似 + 正文同主题」双重闸门的页面对数 */
  pairs_checked: number;
  candidate_pairs: number;
  conflicts_found: number;
  /** 新写入复核队列的条数 */
  created: number;
  /** 因已有待裁决项而跳过的对数（幂等保证） */
  skipped_existing: number;
  /** 页面数超过单次扫描上限，本轮只扫了一部分 */
  truncated: boolean;
}

/**
 * 触发知识库冲突巡检。
 *
 * 编译期的冲突检测只比「新页 vs 旧页」，两个已存在的页面之间的矛盾会永久漏掉；
 * 本接口做全库跨页扫描补齐。**只写复核队列，不改正文**，可反复调用。
 * 定时版本由后端 arq cron 每周一凌晨自动执行。
 */
export async function scanKnowledgeBaseConflicts(
  kbId: number,
  options: { useLlm?: boolean; maxPages?: number } = {},
): Promise<ConflictScanStats> {
  const params = new URLSearchParams();
  if (options.useLlm) params.set('use_llm', 'true');
  if (options.maxPages) params.set('max_pages', String(options.maxPages));
  const qs = params.toString() ? `?${params.toString()}` : '';
  return apiFetch<ConflictScanStats>(
    `${KB_ENDPOINT}/bases/${kbId}/conflicts/scan${qs}`,
    { method: 'POST', timeoutMs: 300_000 },
    '冲突巡检失败',
  );
}

// ---------------------------------------------------------------------------
// 共享成员（知识库行级 ACL）
// ---------------------------------------------------------------------------

export type KBACLRole = 'viewer' | 'editor' | 'admin';

export interface KBACLItem {
  id: number;
  principal_type: 'user';
  principal_id: number;
  role: KBACLRole;
  email: string | null;
  name: string | null;
  granted_by: number;
  created_at: string;
}

export interface KBACLPayloadEntry {
  principal_id?: number;
  principal_email?: string;
  role: KBACLRole;
}

export async function getKnowledgeBaseAcl(kbId: number): Promise<KBACLItem[]> {
  const data = await apiFetch<{ knowledge_base_id: number; items: KBACLItem[] }>(
    `${KB_ENDPOINT}/bases/${kbId}/acl`,
    {},
  );
  return data.items ?? [];
}

/** 整体替换共享成员（幂等）。只允许知识库创建者或管理员调用。 */
export async function replaceKnowledgeBaseAcl(
  kbId: number,
  entries: KBACLPayloadEntry[],
): Promise<KBACLItem[]> {
  const data = await apiFetch<{ knowledge_base_id: number; items: KBACLItem[] }>(
    `${KB_ENDPOINT}/bases/${kbId}/acl`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries }),
    },
    '保存共享成员失败',
  );
  return data.items ?? [];
}

// ---------------------------------------------------------------------------
// Reviews
// ---------------------------------------------------------------------------

export async function getReviewItems(kbId: number, status?: string): Promise<ReviewItem[]> {
  const params = status ? `?status_filter=${encodeURIComponent(status)}` : '';
  return apiFetch<ReviewItem[]>(
          `${KB_ENDPOINT}/bases/${kbId}/reviews${params}`,
          {
  }
        );}

/**
 * 更新审核任务。
 * 后端 knowledge.py 的 PATCH /bases/{kb_id}/reviews/{review_id}
 * 使用 Query 参数（status: Query(...), resolution_note: str = ""），
 * 因此这里通过 query string 发送，避免 422。
 */
export async function updateReview(
  kbId: number,
  reviewId: number,
  status: 'approved' | 'rejected' | 'resolved',
  resolutionNote = '',
): Promise<{ id: number; status: string }> {
  const params = new URLSearchParams({
    status,
    resolution_note: resolutionNote,
  });
  return apiFetch<{ id: number; status: string }>(
          `${KB_ENDPOINT}/bases/${kbId}/reviews/${reviewId}?${params.toString()}`,
          {
    method: 'PATCH',
  }
        );}

// ---------------------------------------------------------------------------
// Knowledge Graph
// ---------------------------------------------------------------------------

export interface GraphNode {
  id: number;
  label: string;
  type: string;
  authority: string;
}

export interface GraphEdge {
  source: number;
  target: number;
  type: string;
}

export interface KnowledgeGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export async function getKnowledgeGraph(kbId: number): Promise<KnowledgeGraphData> {
  return apiFetch<KnowledgeGraphData>(
          `${KB_ENDPOINT}/bases/${kbId}/graph`,
          {
  }
        );}
