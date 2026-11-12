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
  title?: string,
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
      title: title || null,
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
  /** 可读作品名（后端从会话标题派生；旧数据可能缺省，回退 project_slug） */
  title?: string;
  stack: string;
  visibility: 'public' | 'private';
  deploy_url: string | null;
  access_url?: string;
  status: string;
  updated_at: string | null;
  /** 封面图 URL（后端 Playwright 截图 + 压缩；缺失表示尚未生成） */
  cover_url?: string | null;
  view_count?: number;
  last_viewed_at?: string | null;
  /** 作者（后端返回 requested_by 对应展示名，可选） */
  author_name?: string | null;
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

// ─── 网站预览令牌 ───

export type PreviewTokenResponse = {
  token: string;
  /** 可直接给 iframe src 用的完整路径（令牌在 path 段，相对资源能继承前缀） */
  url: string;
  expires_in: number;
};

/**
 * 现签一个预览 URL（15 分钟 TTL）。
 *
 * 为什么需要"现签"而不是复用旧 URL：预览令牌绑定用户+会话+项目且短时有效，
 * 内存里缓存的 artifact.previewUrl 一旦超过 TTL，iframe 就会渲染 403 错误页
 * （典型场景：页面开着超过 15 分钟后点「重新打开产物预览」）。凡是从内存
 * 复用 artifact 的入口，打开面板前都应先调这里拿新 URL；拿不到时调用方
 * 退回 preview_html 内联 srcDoc（自包含、永不过期）。
 */
export async function issueWebsitePreviewUrl(
  sessionId: string,
  projectSlug: string,
): Promise<PreviewTokenResponse> {
  const qs = `slug=${encodeURIComponent(projectSlug)}&session_id=${encodeURIComponent(sessionId)}`;
  return apiFetch<PreviewTokenResponse>(
    `/api/v1/website/preview-token?${qs}`,
    { method: 'POST' },
    '签发预览链接失败',
  );
}
