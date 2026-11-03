import { apiFetch, API_BASE_URL } from './apiClient'

export type DeployStatus = 'pending' | 'approved' | 'rejected' | 'deploying' | 'deployed' | 'failed'

export type DeployRecord = {
  id: number
  session_id: string
  project_slug: string
  stack: string
  dist_path: string
  target_domain: string | null
  deploy_url: string | null
  status: DeployStatus
  requested_by: number
  approved_by: number | null
  reason: string | null
  created_at: string | null
  updated_at: string | null
}

/**
 * 请求部署网站。
 * @param sessionId 会话 ID（首参必须是 sessionId，不是 artifactId）
 * @param projectSlug 项目 slug
 * @param stack 技术栈
 * @param targetDomain 可选目标域名
 */
export async function requestDeploy(
  sessionId: string,
  projectSlug: string,
  stack: string,
  targetDomain?: string,
  visibility?: 'public' | 'private',
): Promise<DeployRecord> {
  if (!sessionId) {
    throw new Error('requestDeploy requires sessionId (not artifactId)')
  }
  return apiFetch<DeployRecord>(`${API_BASE_URL}/api/v1/website/deploy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      project_slug: projectSlug,
      stack,
      target_domain: targetDomain || null,
      visibility: visibility || 'private',
    }),
  }, 'Deploy request failed')
}

export async function getDeployStatus(deployId: number): Promise<DeployRecord> {
  return apiFetch<DeployRecord>(`${API_BASE_URL}/api/v1/website/deploy/${deployId}`)
}

export async function getDeployByProject(projectSlug: string): Promise<DeployRecord> {
  return apiFetch<DeployRecord>(`${API_BASE_URL}/api/v1/website/deploy/project/${projectSlug}`)
}

export async function listPendingDeploys(): Promise<DeployRecord[]> {
  return apiFetch<DeployRecord[]>(`${API_BASE_URL}/api/v1/admin/website/deploys`)
}

export async function listAllDeploys(): Promise<DeployRecord[]> {
  return apiFetch<DeployRecord[]>(`${API_BASE_URL}/api/v1/admin/website/deploys/all`)
}

export async function decideDeploy(
  deployId: number,
  decision: { status: 'approved' | 'rejected'; reason?: string },
): Promise<DeployRecord> {
  return apiFetch<DeployRecord>(
    `${API_BASE_URL}/api/v1/admin/website/deploys/${deployId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(decision),
    },
    'Decision failed',
  )
}


// ─── 作品库（gallery） ───

export type GalleryItem = {
  id: number;
  project_slug: string;
  stack: string;
  visibility: 'public' | 'private';
  deploy_url: string | null;
  access_url?: string;
  status: string;
  updated_at: string | null;
};

export async function listGallery(): Promise<GalleryItem[]> {
  return apiFetch<GalleryItem[]>('/api/v1/website/gallery', {}, '获取作品库失败');
}

export async function resetSiteAccess(deployId: number): Promise<{ access_url: string }> {
  return apiFetch<{ access_url: string }>(
    `/api/v1/website/deploy/${deployId}/reset-access`,
    { method: 'POST' },
    '重置访问链接失败',
  );
}
