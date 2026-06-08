import { authHeaders } from './authService';

export type AnnouncementTheme = 'aurora' | 'sunset' | 'midnight';

export type AnnouncementContentFormat = 'markdown' | 'html';

export type Announcement = {
  id: number;
  eyebrow: string;
  title: string;
  subtitle: string;
  body: string;
  image_url: string | null;
  content_format: AnnouncementContentFormat;
  theme: AnnouncementTheme;
  cta_label: string | null;
  cta_link: string | null;
  is_published: boolean;
  dismissible: boolean;
  show_once: boolean;
  starts_at: string | null;
  ends_at: string | null;
  active_now: boolean;
  created_by: number | null;
  created_at: string;
  updated_at: string;
};

export type AnnouncementListResponse = {
  items: Announcement[];
};

export type ActiveAnnouncementResponse = {
  item: Announcement | null;
};

export type AnnouncementPayload = {
  eyebrow: string;
  title: string;
  subtitle: string;
  body: string;
  image_url: string | null;
  content_format: AnnouncementContentFormat;
  theme: AnnouncementTheme;
  cta_label: string | null;
  cta_link: string | null;
  is_published: boolean;
  dismissible: boolean;
  show_once: boolean;
  starts_at: string | null;
  ends_at: string | null;
};

export type AnnouncementGenerateRequest = {
  brief: string;
  content_format: AnnouncementContentFormat;
  theme: AnnouncementTheme;
  cta_goal?: string | null;
};

export type AnnouncementGeneratedDraft = {
  eyebrow: string;
  title: string;
  subtitle: string;
  body: string;
  content_format: AnnouncementContentFormat;
  theme: AnnouncementTheme;
  cta_label: string | null;
  cta_link: string | null;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const ANNOUNCEMENTS_ENDPOINT = `${API_BASE_URL}/api/v1/announcements`;

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

export async function getAnnouncements(): Promise<AnnouncementListResponse> {
  const response = await fetch(ANNOUNCEMENTS_ENDPOINT, {
    headers: authHeaders(),
  });
  return parseResponse<AnnouncementListResponse>(response);
}

export async function getActiveAnnouncement(): Promise<ActiveAnnouncementResponse> {
  const response = await fetch(`${ANNOUNCEMENTS_ENDPOINT}/active`, {
    headers: authHeaders(),
  });
  return parseResponse<ActiveAnnouncementResponse>(response);
}

export async function createAnnouncement(payload: AnnouncementPayload): Promise<Announcement> {
  const response = await fetch(ANNOUNCEMENTS_ENDPOINT, {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<Announcement>(response);
}

export async function updateAnnouncement(announcementId: number, payload: Partial<AnnouncementPayload>): Promise<Announcement> {
  const response = await fetch(`${ANNOUNCEMENTS_ENDPOINT}/${announcementId}`, {
    method: 'PATCH',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });
  return parseResponse<Announcement>(response);
}

export async function deleteAnnouncement(announcementId: number): Promise<void> {
  const response = await fetch(`${ANNOUNCEMENTS_ENDPOINT}/${announcementId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    await parseResponse(response);
  }
}

export async function generateAnnouncement(request: AnnouncementGenerateRequest): Promise<AnnouncementGeneratedDraft> {
  const response = await fetch(`${ANNOUNCEMENTS_ENDPOINT}/generate`, {
    method: 'POST',
    headers: {
      ...authHeaders(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  });
  return parseResponse<AnnouncementGeneratedDraft>(response);
}
