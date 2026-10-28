/**
 * AI 提供商 API 服务。
 *
 * 三条硬约定：
 * 1. 后端**从不**返回 api_key / password / cookie 的明文或片段，
 *    前端也不该发明「显示密钥」这类交互 —— 它只会是假的。
 * 2. 所有写操作失败都以 ApiError 抛出，由调用方 toast。
 * 3. 企业网关是**账号池**：凡涉及「标记失效 / 重新登录 / 贴 Cookie」的
 *    操作都必须带 accountId，否则会作用到错误的账号上。
 */

import { apiFetch } from './apiClient';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const ENDPOINT = `${API_BASE_URL}/api/v1/settings/llm-providers`;

export type ProviderType = 'openai_compatible' | 'enterprise_cookie';

/** LLM 负载用途。企业网关常常按用途分模型。 */
export type ModelRole = 'chat' | 'reasoner' | 'fast' | 'vision' | 'image';

export interface ProviderTypeOption {
  value: ProviderType;
  label: string;
}

export interface ProviderPreset {
  slug: string;
  label: string;
  provider_type: ProviderType;
  base_url: string;
  model: string;
  login_url: string;
  needs_cookie: boolean;
  notes: string;
  roles: Record<string, string>;
}

export interface RoleOption {
  value: string;
  label: string;
}

export interface CredentialStatus {
  id: number;
  /** 展示名；留空时后端回退成 username */
  label: string;
  username: string;
  has_password: boolean;
  has_cookie: boolean;
  login_url: string | null;
  /** pending 从未登录 / active / expired / failed / disabled（人工停用） */
  status: 'pending' | 'active' | 'expired' | 'failed' | 'disabled';
  auto_refresh: boolean;
  priority: number;
  failure_count: number;
  disabled: boolean;
  /** 连续失败已达阈值，不会再被轮换选中 */
  excluded_from_rotation: boolean;
  expire_at: string | null;
  last_login_at: string | null;
  last_used_at: string | null;
  last_error: string | null;
  updated_at: string | null;
}

export interface LlmProvider {
  id: number;
  name: string;
  slug: string;
  provider_type: ProviderType;
  provider_type_label: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  timeout_seconds: number;
  max_tokens: number | null;
  extra: Record<string, unknown>;
  preset: string | null;
  roles: Record<string, string>;
  description: string;
  enabled: boolean;
  is_default: boolean;
  /** 是否为当前生效的提供商 */
  is_active: boolean;
  needs_cookie: boolean;
  account_count: number | null;
  credential?: CredentialStatus | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ActiveProviderInfo {
  provider_id: number | null;
  name: string;
  slug: string;
  provider_type: ProviderType;
  base_url: string;
  model: string;
  source: 'database' | 'env';
  needs_cookie: boolean;
}

export interface EnvFallbackInfo {
  slug: string;
  base_url: string;
  model: string;
  has_api_key: boolean;
  usable: boolean;
}

export interface ProviderListResponse {
  items: LlmProvider[];
  active: ActiveProviderInfo;
  env_fallback: EnvFallbackInfo;
  provider_types: ProviderTypeOption[];
  presets: ProviderPreset[];
  model_roles: RoleOption[];
}

export interface ProbeStage {
  stage: string;
  ok: boolean;
  elapsed_ms: number;
  url?: string;
  status_code?: number;
  message?: string;
  hint?: string;
  /** 上游返回的原始响应体。可能很长（网关错误 JSON 常有几百字符），
   *  界面上折叠展示，绝不进 toast。 */
  detail?: string | null;
  auth_kind?: string;
  model_count?: number;
  content?: string;
  total_tokens?: number;
  /** 流式阶段收到的 SSE 帧数（界面走的是流式，这一项最能反映实际可用性） */
  frames?: number;
  content_type?: string;
  has_reasoning?: boolean;
  accepted?: boolean;
  returned_tool_calls?: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  stage: string;
  url?: string;
  status_code?: number;
  message?: string;
  hint?: string;
  /** 全部通过时仍然值得显示的补充说明（例如「模型清单受限但对话可用」） */
  note?: string;
  /** 分阶段结果：network → auth → chat → stream → tools（deep 模式才跑后三步） */
  stages: ProbeStage[];
  models?: string[] | null;
  model_names?: string[] | null;
  model_count?: number;
  configured_model_available?: boolean | null;
  elapsed_ms?: number;
}

export interface ProviderCreateInput {
  name: string;
  slug: string;
  provider_type?: ProviderType;
  base_url?: string;
  model?: string;
  api_key?: string;
  timeout_seconds?: number;
  max_tokens?: number | null;
  extra?: Record<string, unknown>;
  /** 厂商预设：后端用它补全地址/模型/登录动作 */
  preset?: string | null;
  description?: string;
  enabled?: boolean;
  is_default?: boolean;
}

/** 局部更新。api_key 三态：不传 = 不变；传 '' = 清空；传值 = 覆盖。 */
export type ProviderUpdateInput = Partial<Omit<ProviderCreateInput, 'slug'>>;

export interface DiscoveredModel {
  id: number;
  provider_id: number;
  /** 上游的模型 ID（百通：qwen3.6-35b） */
  model_key: string;
  /** 请求体里真正要填的名字（百通：Qwen3.6-35B-A3B） */
  model_name: string;
  task_type: string;
  max_tokens: number | null;
  extra: Record<string, unknown>;
  enabled: boolean;
  updated_at: string | null;
}

export interface ModelListResponse {
  items: DiscoveredModel[];
  total: number;
  roles: Record<string, string>;
  role_options: RoleOption[];
}

export interface DiscoveryResult {
  ok: boolean;
  meta: { ok?: boolean; url?: string; stage?: string; status_code?: number; message?: string; count?: number };
  models: Array<{
    model_key: string;
    model_name: string;
    task_type: string;
    max_tokens: number | null;
    extra: Record<string, unknown>;
  }>;
  added: number;
  updated: number;
}

export interface AccountListResponse {
  items: CredentialStatus[];
  total: number;
  active: number;
  rotation_policy: string;
}

export async function listLlmProviders(): Promise<ProviderListResponse> {
  return apiFetch<ProviderListResponse>(ENDPOINT, {}, '加载 AI 提供商失败');
}

export async function createLlmProvider(input: ProviderCreateInput): Promise<LlmProvider> {
  return apiFetch<LlmProvider>(
    ENDPOINT,
    { method: 'POST', body: JSON.stringify(input) },
    '创建提供商失败',
  );
}

export async function updateLlmProvider(
  id: number,
  input: ProviderUpdateInput,
): Promise<LlmProvider> {
  return apiFetch<LlmProvider>(
    `${ENDPOINT}/${id}`,
    { method: 'PATCH', body: JSON.stringify(input) },
    '更新提供商失败',
  );
}

export async function deleteLlmProvider(id: number): Promise<void> {
  await apiFetch<void>(`${ENDPOINT}/${id}`, { method: 'DELETE' }, '删除提供商失败');
}

export async function setDefaultLlmProvider(id: number): Promise<{ active: ActiveProviderInfo }> {
  return apiFetch<{ active: ActiveProviderInfo }>(
    `${ENDPOINT}/${id}/default`,
    { method: 'POST' },
    '切换默认提供商失败',
  );
}

/**
 * 连通性诊断。失败会返回 ok=false 的诊断结果，而不是抛错。
 *
 * `deep=true` 会真实发一条对话 + 一次带 tools 的请求：这是唯一能确认
 * 「agent 能不能跑」的办法，但会消耗上游额度，所以由用户显式触发。
 */
export async function testLlmProvider(id: number, deep = false): Promise<ProviderTestResult> {
  return apiFetch<ProviderTestResult>(
    `${ENDPOINT}/${id}/test${deep ? '?deep=true' : ''}`,
    { method: 'POST', timeoutMs: deep ? 120_000 : 30_000 },
    '测试连通性失败',
  );
}

/** 保存前的试连入参：可直接提交未落库的表单值。 */
export interface ProviderDraftTestInput {
  provider_type: ProviderType;
  base_url: string;
  model: string;
  /** 编辑场景可留空，后端沿用已保存的 Key */
  api_key?: string;
  timeout_seconds?: number;
  max_tokens?: number | null;
  extra?: Record<string, unknown>;
  /** 编辑时的提供商 id：用于复用库里的 Key 与账号池 Cookie */
  provider_id?: number | null;
  deep?: boolean;
}

/**
 * 保存前试连：验证表单里尚未保存的配置。
 *
 * 与 `testLlmProvider` 的区别是它**不需要先落库** —— 地址填错、Key 失效
 * 时不会先污染配置表。
 */
export async function testLlmProviderDraft(
  input: ProviderDraftTestInput,
): Promise<ProviderTestResult> {
  return apiFetch<ProviderTestResult>(
    `${ENDPOINT}/test`,
    {
      method: 'POST',
      body: JSON.stringify(input),
      timeoutMs: input.deep ? 120_000 : 30_000,
    },
    '测试连通性失败',
  );
}

/** 把 .env 里的 OPENAI_* 配置落成一条真实记录。 */
export async function importLlmProviderFromEnv(): Promise<LlmProvider> {
  return apiFetch<LlmProvider>(
    `${ENDPOINT}/import-env`,
    { method: 'POST' },
    '从环境变量导入失败',
  );
}

// ---------------------------------------------------------------------------
// 账号池
// ---------------------------------------------------------------------------

export async function listProviderAccounts(id: number): Promise<AccountListResponse> {
  return apiFetch<AccountListResponse>(
    `${ENDPOINT}/${id}/accounts`,
    {},
    '加载账号池失败',
  );
}

export async function createProviderAccount(
  id: number,
  input: {
    label?: string;
    username?: string;
    password?: string;
    login_url?: string;
    priority?: number;
  },
): Promise<CredentialStatus> {
  return apiFetch<CredentialStatus>(
    `${ENDPOINT}/${id}/accounts`,
    { method: 'POST', body: JSON.stringify(input) },
    '新增账号失败',
  );
}

export async function updateProviderAccount(
  id: number,
  accountId: number,
  input: {
    label?: string;
    username?: string;
    password?: string;
    login_url?: string;
    priority?: number;
    auto_refresh?: boolean;
    disabled?: boolean;
  },
): Promise<CredentialStatus> {
  return apiFetch<CredentialStatus>(
    `${ENDPOINT}/${id}/accounts/${accountId}`,
    { method: 'PATCH', body: JSON.stringify(input) },
    '更新账号失败',
  );
}

export async function deleteProviderAccount(id: number, accountId: number): Promise<void> {
  await apiFetch<void>(
    `${ENDPOINT}/${id}/accounts/${accountId}`,
    { method: 'DELETE' },
    '删除账号失败',
  );
}

/** 给指定账号手贴 Cookie。多账号时必须显式指定，不能靠「默认账号」。 */
export async function saveAccountCookie(
  id: number,
  accountId: number,
  cookie: string,
  expireAt?: string,
): Promise<CredentialStatus> {
  return apiFetch<CredentialStatus>(
    `${ENDPOINT}/${id}/accounts/${accountId}/cookie`,
    { method: 'PUT', body: JSON.stringify({ cookie, expire_at: expireAt || null }) },
    '保存 Cookie 失败',
  );
}

/**
 * 触发一次自动登录（Playwright 填表）。
 * 不指定 accountId 时后端挑「最需要续期」的账号；指定则只刷那一个。
 */
export async function loginProvider(
  id: number,
  accountId?: number,
): Promise<{
  success: boolean;
  message: string;
  credential_id: number | null;
  credentials: CredentialStatus[];
}> {
  const query = accountId ? `?credential_id=${accountId}` : '';
  return apiFetch(
    `${ENDPOINT}/${id}/login${query}`,
    { method: 'POST', timeoutMs: 120_000 },
    '自动登录失败',
  );
}

// ---------------------------------------------------------------------------
// 模型目录与用途绑定
// ---------------------------------------------------------------------------

export async function listProviderModels(id: number): Promise<ModelListResponse> {
  return apiFetch<ModelListResponse>(`${ENDPOINT}/${id}/models`, {}, '加载模型清单失败');
}

/** 从上游拉模型清单。persist=false 只预演，不写库。 */
export async function discoverProviderModels(
  id: number,
  persist = true,
): Promise<DiscoveryResult> {
  return apiFetch<DiscoveryResult>(
    `${ENDPOINT}/${id}/models/discover${persist ? '' : '?persist=false'}`,
    { method: 'POST', timeoutMs: 60_000 },
    '同步模型清单失败',
  );
}

export async function deleteProviderModel(id: number, modelId: number): Promise<void> {
  await apiFetch<void>(
    `${ENDPOINT}/${id}/models/${modelId}`,
    { method: 'DELETE' },
    '删除模型失败',
  );
}

export async function updateProviderRoles(
  id: number,
  roles: Record<string, string>,
): Promise<{ roles: Record<string, string> }> {
  return apiFetch<{ roles: Record<string, string> }>(
    `${ENDPOINT}/${id}/roles`,
    { method: 'PUT', body: JSON.stringify({ roles }) },
    '保存用途绑定失败',
  );
}

// ---------------------------------------------------------------------------
// 兼容旧接口：单账号语义（等价于「默认账号」）
// ---------------------------------------------------------------------------

export async function getProviderCredential(id: number): Promise<CredentialStatus | null> {
  const accounts = await listProviderAccounts(id).catch(() => null);
  return accounts?.items[0] ?? null;
}

/** password 传空表示不修改已保存的密码。作用于默认账号。 */
export async function saveProviderCredential(
  id: number,
  input: { username: string; password?: string; login_url?: string; auto_refresh?: boolean },
): Promise<CredentialStatus> {
  return apiFetch<CredentialStatus>(
    `${ENDPOINT}/${id}/credential`,
    { method: 'PUT', body: JSON.stringify(input) },
    '保存登录凭据失败',
  );
}

export async function clearProviderCredential(id: number): Promise<CredentialStatus> {
  return apiFetch<CredentialStatus>(
    `${ENDPOINT}/${id}/credential`,
    { method: 'DELETE' },
    '清除登录凭据失败',
  );
}

/** 手动粘贴 Cookie 兜底（作用于默认账号）。 */
export async function saveManualCookie(
  id: number,
  cookie: string,
  expireAt?: string,
): Promise<CredentialStatus> {
  return apiFetch<CredentialStatus>(
    `${ENDPOINT}/${id}/credential/cookie`,
    { method: 'PUT', body: JSON.stringify({ cookie, expire_at: expireAt || null }) },
    '保存 Cookie 失败',
  );
}
