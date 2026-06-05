import { authHeaders } from "./authService";

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

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json();
  let message = "请求失败";
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") message = payload.detail;
    if (typeof payload.error === "string") message = payload.error;
  } catch {
    const text = await response.text();
    if (text) message = text;
  }
  throw new Error(message);
}

export async function getEmailStatus(): Promise<EmailStatus> {
  const response = await fetch(`${ENDPOINT}/credentials/status`, { headers: authHeaders() });
  return parseResponse(response);
}

export async function saveEmailCredentials(payload: EmailCredentialsPayload): Promise<{ success: boolean; message?: string; error?: string }> {
  const response = await fetch(`${ENDPOINT}/credentials`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response);
}

export async function deleteEmailCredentials(): Promise<{ success: boolean; message?: string }> {
  const response = await fetch(`${ENDPOINT}/credentials`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return parseResponse(response);
}
