import { apiFetch } from './apiClient';

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

export async function getAnnouncements(): Promise<AnnouncementListResponse> {
  return apiFetch<AnnouncementListResponse>(ANNOUNCEMENTS_ENDPOINT, {}, '公告列表加载失败');
}

export async function getActiveAnnouncement(): Promise<ActiveAnnouncementResponse> {
  return apiFetch<ActiveAnnouncementResponse>(`${ANNOUNCEMENTS_ENDPOINT}/active`, {}, '当前公告加载失败');
}

export async function createAnnouncement(payload: AnnouncementPayload): Promise<Announcement> {
  return apiFetch<Announcement>(
    ANNOUNCEMENTS_ENDPOINT,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '创建公告失败',
  );
}

export async function updateAnnouncement(announcementId: number, payload: Partial<AnnouncementPayload>): Promise<Announcement> {
  return apiFetch<Announcement>(
    `${ANNOUNCEMENTS_ENDPOINT}/${announcementId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '更新公告失败',
  );
}

export async function deleteAnnouncement(announcementId: number): Promise<void> {
  await apiFetch<void>(`${ANNOUNCEMENTS_ENDPOINT}/${announcementId}`, { method: 'DELETE' }, '删除公告失败');
}

export async function generateAnnouncement(request: AnnouncementGenerateRequest): Promise<AnnouncementGeneratedDraft> {
  return apiFetch<AnnouncementGeneratedDraft>(
    `${ANNOUNCEMENTS_ENDPOINT}/generate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    },
    '生成公告失败',
  );
}
