import { authHeaders } from "./authService";

export type CredentialField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  placeholder?: string;
  help_url?: string;
  help_text?: string;
};

export type IntegrationSystem = {
  id: number;
  name: string;
  description: string;
  category: string;
  base_url: string;
  auth_type: string;
  credential_template: Record<string, CredentialField>;
  oauth_auth_url: string | null;
  oauth_token_url: string | null;
  oauth_scope: string | null;
  oauth_refresh_token_url: string | null;
  jwt_login_url: string | null;
  jwt_refresh_url: string | null;
  jwt_refresh_body_template: string | null;
  jwt_refresh_token_path: string | null;
  jwt_request_body_template: string | null;
  jwt_response_token_path: string | null;
  jwt_response_expires_path: string | null;
  jwt_response_token_header: string | null;
  login_token_source: string | null;
  login_inject_mode: string | null;
  login_inject_header_name: string | null;
  published: boolean;
  headers: Record<string, string>;
  advanced_auth: Record<string, any>;
  enabled: boolean;
  api_count: number;
  created_by: number | null;
  created_at: string;
  updated_at: string;
};

export type IntegrationApiParam = {
  name: string;
  param_type: string;
  data_type: string;
  required: boolean;
  description: string;
  default_value: string | null;
};

export type IntegrationApi = {
  id: number;
  name: string;
  display_name: string;
  description: string;
  method: string;
  path: string;
  request_body_schema: string | null;
  response_example: string | null;
  requires_approval: boolean;
  timeout_seconds: number;
  enabled: boolean;
  params: IntegrationApiParam[];
  created_at: string;
  updated_at: string;
};

export type UserConnection = {
  id: number;
  system_id: number;
  system_name: string;
  connection_status: string;
  connected_at: string;
  last_checked_at: string | null;
};

export type IntegrationApiPayload = {
  name: string;
  display_name: string;
  description: string;
  method: string;
  path: string;
  request_body_schema?: string;
  response_example?: string;
  requires_approval: boolean;
  timeout_seconds: number;
  params: IntegrationApiParam[];
};

export type IntegrationSystemPayload = {
  name: string;
  description: string;
  base_url: string;
  auth_type: string;
  credential_template: Record<string, CredentialField>;
  oauth_client_id?: string;
  oauth_client_secret?: string;
  oauth_auth_url?: string;
  oauth_token_url?: string;
  oauth_scope?: string;
  oauth_refresh_token_url?: string;
  jwt_login_url?: string;
  jwt_refresh_url?: string;
  jwt_refresh_body_template?: string;
  jwt_refresh_token_path?: string;
  jwt_request_body_template?: string;
  jwt_response_token_path?: string;
  jwt_response_expires_path?: string;
  jwt_response_token_header?: string;
  login_token_source?: string;
  login_inject_mode?: string;
  login_inject_header_name?: string;
  published: boolean;
  headers: Record<string, string>;
  advanced_auth?: Record<string, any>;
};

export type IntegrationTestResult = {
  success: boolean;
  status_code: number;
  body: string;
  elapsed_ms: number;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const ADMIN_ENDPOINT = `${API_BASE_URL}/api/v1/external-systems`;
const USER_ENDPOINT = `${API_BASE_URL}/api/v1/integrations`;

async function parseResponse<T>(response: Response): Promise<T> {
  // 先读 text，避免 json() 消费 body 后 text() 报 "body stream already read"
  const raw = await response.text();
  if (response.ok) {
    return JSON.parse(raw) as T;
  }
  let message = "Request failed";
  try {
    const payload = JSON.parse(raw);
    if (typeof payload.detail === "string") message = payload.detail;
  } catch {
    if (raw) message = raw;
  }
  throw new Error(message);
}

export async function listSystems(): Promise<{ items: IntegrationSystem[] }> {
  const response = await fetch(ADMIN_ENDPOINT, { headers: authHeaders() });
  return parseResponse(response);
}

export async function getSystem(systemId: number): Promise<IntegrationSystem> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}`, { headers: authHeaders() });
  return parseResponse(response);
}

export async function createSystem(payload: IntegrationSystemPayload): Promise<IntegrationSystem> {
  const response = await fetch(ADMIN_ENDPOINT, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function updateSystem(systemId: number, payload: Partial<IntegrationSystemPayload>): Promise<IntegrationSystem> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function deleteSystem(systemId: number): Promise<void> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) await parseResponse(response);
}

export async function listApis(systemId: number): Promise<{ items: IntegrationApi[] }> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}/apis`, { headers: authHeaders() });
  return parseResponse(response);
}

export async function createApi(systemId: number, payload: IntegrationApiPayload): Promise<IntegrationApi> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}/apis`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function updateApi(systemId: number, apiId: number, payload: Partial<IntegrationApiPayload>): Promise<IntegrationApi> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}/apis/${apiId}`, {
    method: "PATCH",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function deleteApi(systemId: number, apiId: number): Promise<void> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}/apis/${apiId}`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) await parseResponse(response);
}

export async function testApi(systemId: number, apiId: number, params: Record<string, unknown>, credentialData?: Record<string, string>): Promise<IntegrationTestResult> {
  const response = await fetch(`${ADMIN_ENDPOINT}/${systemId}/apis/${apiId}/test`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ params, credential_data: credentialData }),
  });
  return parseResponse(response);
}

export type IntegrationCategory = {
  key: string;
  label: string;
  icon: string;
};

export async function listCategories(): Promise<{ items: IntegrationCategory[] }> {
  const response = await fetch(`${USER_ENDPOINT}/categories`, { headers: authHeaders() });
  return parseResponse(response);
}

export async function listIntegrations(): Promise<{ items: IntegrationSystem[] }> {
  const response = await fetch(USER_ENDPOINT, { headers: authHeaders() });
  return parseResponse(response);
}

export async function connectIntegration(systemId: number, credentialData: Record<string, string>): Promise<UserConnection> {
  const response = await fetch(`${USER_ENDPOINT}/${systemId}/connect`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ credential_data: credentialData }),
  });
  return parseResponse(response);
}

export async function disconnectIntegration(systemId: number): Promise<void> {
  const response = await fetch(`${USER_ENDPOINT}/${systemId}/disconnect`, { method: "DELETE", headers: authHeaders() });
  if (!response.ok) await parseResponse(response);
}

export async function getConnectionStatus(systemId: number): Promise<UserConnection> {
  const response = await fetch(`${USER_ENDPOINT}/${systemId}/status`, { headers: authHeaders() });
  return parseResponse(response);
}

export async function listMyConnections(): Promise<{ items: UserConnection[] }> {
  const response = await fetch(`${USER_ENDPOINT}/my/connections`, { headers: authHeaders() });
  return parseResponse(response);
}

// ── OpenAPI Import ─────────────────────────────────────────────────────────

export type OpenApiPreview = {
  system_name: string;
  system_description: string;
  base_url: string;
  auth_type: string;
  apis: Array<{
    name: string;
    display_name: string;
    description: string;
    method: string;
    path: string;
    requires_approval: boolean;
    timeout_seconds: number;
    params: IntegrationApiParam[];
  }>;
};

export async function previewOpenApiImport(openapiJson?: string, openapiUrl?: string): Promise<OpenApiPreview> {
  const response = await fetch(`${ADMIN_ENDPOINT}/import-openapi/preview`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ openapi_json: openapiJson, openapi_url: openapiUrl }),
  });
  return parseResponse(response);
}

export async function confirmOpenApiImport(preview: OpenApiPreview): Promise<IntegrationSystem> {
  const response = await fetch(`${ADMIN_ENDPOINT}/import-openapi/confirm`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(preview),
  });
  return parseResponse(response);
}
