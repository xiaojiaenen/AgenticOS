import { authHeaders } from './authService';

export type LdapSetting = {
  ldap_enabled: boolean;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const SETTINGS_ENDPOINT = `${API_BASE_URL}/api/v1/settings`;

async function parseResponse<T>(response: Response): Promise<T> {
  const raw = await response.text();
  if (response.ok) return JSON.parse(raw) as T;
  let message = 'Request failed';
  try {
    const payload = JSON.parse(raw);
    if (typeof payload.detail === 'string') message = payload.detail;
  } catch {
    if (raw) message = raw;
  }
  throw new Error(message);
}

export async function getLdapSetting(): Promise<LdapSetting> {
  const response = await fetch(`${SETTINGS_ENDPOINT}/ldap`, {
    headers: authHeaders(),
  });
  return parseResponse<LdapSetting>(response);
}

export async function updateLdapSetting(ldap_enabled: boolean): Promise<LdapSetting> {
  const response = await fetch(`${SETTINGS_ENDPOINT}/ldap`, {
    method: 'PUT',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ldap_enabled }),
  });
  return parseResponse<LdapSetting>(response);
}
