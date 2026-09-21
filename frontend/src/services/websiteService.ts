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

export async function requestDeploy(
  sessionId: string,
  projectSlug: string,
  stack: string,
  targetDomain?: string,
): Promise<DeployRecord> {
  return apiFetch<DeployRecord>(`${API_BASE_URL}/api/v1/website/deploy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      project_slug: projectSlug,
      stack,
      target_domain: targetDomain || null,
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
