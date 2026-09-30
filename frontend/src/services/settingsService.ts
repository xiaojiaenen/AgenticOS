import { apiFetch } from './apiClient';

export type LdapSetting = {
  ldap_enabled: boolean;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SETTINGS_ENDPOINT = `${API_BASE_URL}/api/v1/settings`;

export async function getLdapSetting(): Promise<LdapSetting> {
  return apiFetch<LdapSetting>(`${SETTINGS_ENDPOINT}/ldap`, {}, 'LDAP 配置加载失败');
}

export async function updateLdapSetting(ldap_enabled: boolean): Promise<LdapSetting> {
  return apiFetch<LdapSetting>(
    `${SETTINGS_ENDPOINT}/ldap`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ldap_enabled }),
    },
    'LDAP 配置更新失败',
  );
}
