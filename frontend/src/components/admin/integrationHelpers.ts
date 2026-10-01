/**
 * 集成管理：共享常量、zod schema 与小型工具函数。
 * 从 IntegrationManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import * as React from 'react';
import { z } from 'zod';
import { Globe, Key, Shield } from 'lucide-react';

export const AUTH_TYPES = [
  { value: 'api_key', label: 'API Key' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'oauth2', label: 'OAuth 2.0' },
  { value: 'custom', label: '自定义' },
  { value: 'jwt_login', label: 'JWT 登录' },
];
export const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] as const;

/** 高级安全配置结构：按 section（sign / request_encrypt / response_decrypt / common）分组的字符串键值 */
export type AdvancedAuth = Record<string, Record<string, string>>;

export function authTypeLabel(t: string): string {
  return AUTH_TYPES.find((a) => a.value === t)?.label || t;
}

export function authTypeIcon(t: string): React.ComponentType<{ size?: number; className?: string }> {
  switch (t) {
    case 'api_key':
      return Key;
    case 'bearer':
    case 'oauth2':
      return Shield;
    default:
      return Globe;
  }
}

export function methodBadgeColor(m: string): string {
  switch (m) {
    case 'GET':
      return 'bg-emerald-100 text-emerald-700';
    case 'POST':
      return 'bg-indigo-100 text-indigo-700';
    case 'PUT':
      return 'bg-amber-100 text-amber-700';
    case 'DELETE':
      return 'bg-rose-100 text-rose-700';
    case 'PATCH':
      return 'bg-violet-100 text-violet-700';
    default:
      return 'bg-zinc-100 text-zinc-700';
  }
}

// ---------------------------------------------------------------------------
// zod schema
// ---------------------------------------------------------------------------

const credentialFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.string(),
  required: z.boolean(),
  placeholder: z.string(),
});

export const systemFormSchema = z.object({
  name: z.string().min(1, '请填写名称'),
  base_url: z.string().min(1, '请填写 Base URL'),
  description: z.string(),
  auth_type: z.string().min(1),
  published: z.boolean(),
  oauth_client_id: z.string(),
  oauth_client_secret: z.string(),
  oauth_auth_url: z.string(),
  oauth_token_url: z.string(),
  oauth_refresh_token_url: z.string(),
  oauth_scope: z.string(),
  jwt_login_url: z.string(),
  jwt_refresh_url: z.string(),
  jwt_refresh_body_template: z.string(),
  jwt_refresh_token_path: z.string(),
  jwt_request_body_template: z.string(),
  jwt_response_token_path: z.string(),
  jwt_response_expires_path: z.string(),
  jwt_response_token_header: z.string(),
  login_token_source: z.string(),
  login_inject_mode: z.string(),
  login_inject_header_name: z.string(),
  credential_fields: z.array(credentialFieldSchema),
});

export type SystemFormValues = z.infer<typeof systemFormSchema>;

export const apiFormSchema = z.object({
  name: z.string().min(1, '请填写接口名称'),
  display_name: z.string().min(1, '请填写展示名'),
  description: z.string(),
  method: z.enum(METHODS),
  path: z.string().min(1, '请填写路径'),
  requires_approval: z.boolean(),
  timeout_seconds: z
    .number({ error: '请输入数字' })
    .int('必须为整数')
    .min(1, '至少 1 秒'),
  body_wrapper_key: z.string(),
  params: z.array(
    z.object({
      name: z.string(),
      param_type: z.string(),
      data_type: z.string(),
      required: z.boolean(),
      description: z.string(),
      default_value: z.string().nullable(),
      param_source: z.string(),
      label: z.string().nullable(),
    }),
  ),
});

export type ApiFormValues = z.infer<typeof apiFormSchema>;

// ---------------------------------------------------------------------------
// 高级安全设置常量（签名 / 加密 / 解密）
// ---------------------------------------------------------------------------

export const SIGN_ALGOS = [
  { v: 'none', l: '无' },
  { v: 'hmac_sha256', l: 'HMAC-SHA256' },
  { v: 'hmac_sha512', l: 'HMAC-SHA512' },
  { v: 'hmac_md5', l: 'HMAC-MD5' },
  { v: 'sha256_with_rsa', l: 'SHA256WithRSA' },
  { v: 'sha1_with_rsa', l: 'SHA1WithRSA' },
  { v: 'md5_with_rsa', l: 'MD5WithRSA' },
];
export const AES_ALGOS = [
  { v: 'none', l: '无' },
  { v: 'aes_128_cbc', l: 'AES-128-CBC' },
  { v: 'aes_256_cbc', l: 'AES-256-CBC' },
  { v: 'aes_256_gcm', l: 'AES-256-GCM' },
  { v: 'aes_ecb', l: 'AES-ECB' },
];
