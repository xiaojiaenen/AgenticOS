import { apiFetch } from './apiClient';

export type LdapConfig = {
  enabled: boolean;
  server_url: string;
  start_tls: boolean;
  bind_dn: string;
  bind_password_set: boolean;
  base_dn: string;
  user_filter: string;
  attr_username: string;
  attr_email: string;
  attr_name: string;
  attr_department: string;
  auto_create_users: boolean;
  default_role: 'user' | 'admin';
  department_sync: boolean;
  email_domain: string;
  email_auto_configure: boolean;
  imap_host: string;
  imap_port: number;
  smtp_host: string;
  smtp_port: number;
};

/** 保存用的载荷：bind_password 传空字符串表示不修改 */
export type LdapConfigInput = Omit<LdapConfig, 'bind_password_set'> & {
  bind_password: string;
};

export type LdapTestResult = {
  ok: boolean;
  message: string;
  hint?: string;
  tls?: boolean;
  server_info?: { vendor?: string; version?: string };
  sample_entries?: number;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SETTINGS_ENDPOINT = `${API_BASE_URL}/api/v1/settings`;

export async function getLdapConfig(): Promise<LdapConfig> {
  return apiFetch<LdapConfig>(`${SETTINGS_ENDPOINT}/ldap`, {}, 'LDAP 配置加载失败');
}

export async function updateLdapConfig(config: LdapConfigInput): Promise<LdapConfig> {
  return apiFetch<LdapConfig>(
    `${SETTINGS_ENDPOINT}/ldap`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    },
    'LDAP 配置保存失败',
  );
}

/** 连接测试：可提交未保存的配置；密码留空时沿用已保存的密码 */
export async function testLdapConnection(config: LdapConfigInput): Promise<LdapTestResult> {
  return apiFetch<LdapTestResult>(
    `${SETTINGS_ENDPOINT}/ldap/test`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    },
    'LDAP 连接测试请求失败',
  );
}
