import { authHeaders } from './authService'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

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
  const response = await fetch(`${API_BASE_URL}/api/v1/website/deploy`, {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      project_slug: projectSlug,
      stack,
      target_domain: targetDomain || null,
    }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Deploy request failed: ${response.status}`)
  }
  return await response.json()
}

export async function getDeployStatus(deployId: number): Promise<DeployRecord> {
  const response = await fetch(`${API_BASE_URL}/api/v1/website/deploy/${deployId}`)
  if (!response.ok) {
    throw new Error(`Failed to get deploy status: ${response.status}`)
  }
  return await response.json()
}

export async function getDeployByProject(projectSlug: string): Promise<DeployRecord> {
  const response = await fetch(`${API_BASE_URL}/api/v1/website/deploy/project/${projectSlug}`)
  if (!response.ok) {
    throw new Error(`Failed to get deploy: ${response.status}`)
  }
  return await response.json()
}

export async function listPendingDeploys(): Promise<DeployRecord[]> {
  const response = await fetch(`${API_BASE_URL}/api/v1/admin/website/deploys`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    throw new Error(`Failed to list deploys: ${response.status}`)
  }
  return await response.json()
}

export async function decideDeploy(
  deployId: number,
  status: 'approved' | 'rejected',
  reason?: string,
): Promise<DeployRecord> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/admin/website/deploys/${deployId}/decision`,
    {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, reason: reason || null }),
    },
  )
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail || `Decision failed: ${response.status}`)
  }
  return await response.json()
}
