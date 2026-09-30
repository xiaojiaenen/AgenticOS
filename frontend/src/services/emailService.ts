import { apiFetch } from "./apiClient";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const ENDPOINT = `${API_BASE_URL}/api/v1/email`;

export type EmailStatus = {
  configured: boolean;
  email_address: string | null;
  imap_host: string | null;
  smtp_host: string | null;
};

export type EmailCredentialsPayload = {
  email_address: string;
  password: string;
  imap_host?: string;
  imap_port?: number;
  imap_ssl?: boolean;
  smtp_host?: string;
  smtp_port?: number;
  smtp_ssl?: boolean;
};

export async function getEmailStatus(): Promise<EmailStatus> {
  return apiFetch<EmailStatus>(`${ENDPOINT}/credentials/status`, {}, '邮箱配置状态加载失败');
}

export async function saveEmailCredentials(payload: EmailCredentialsPayload): Promise<{ success: boolean; message?: string; error?: string }> {
  return apiFetch<{ success: boolean; message?: string; error?: string }>(
    `${ENDPOINT}/credentials`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    '保存邮箱配置失败',
  );
}

export async function deleteEmailCredentials(): Promise<{ success: boolean; message?: string }> {
  return apiFetch<{ success: boolean; message?: string }>(
    `${ENDPOINT}/credentials`,
    { method: "DELETE" },
    '删除邮箱配置失败',
  );
}
