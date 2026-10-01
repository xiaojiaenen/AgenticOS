/**
 * 公告设计台：共享 zod schema、常量与小型工具函数。
 * 从 AnnouncementManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { FileCode, FileText } from 'lucide-react';
import { z } from 'zod';
import type { Announcement, AnnouncementContentFormat } from '@/services/announcementService';

/** Basic HTML sanitizer — strips script/event handler attributes */
export function sanitizeHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/\bon\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/\bon\w+\s*=\s*\S+/gi, '');
}

export const FORMAT_META: Record<AnnouncementContentFormat, { label: string; icon: typeof FileText; desc: string }> = {
  markdown: { label: 'Markdown', icon: FileText, desc: '使用 Markdown 语法编写，支持标题、列表、代码块等' },
  html: { label: 'HTML', icon: FileCode, desc: '直接编写 HTML 片段，支持内联样式和布局' },
};

export function toLocalInputValue(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

export function fromLocalInputValue(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

// ---------------------------------------------------------------------------
// zod schema
// ---------------------------------------------------------------------------

export const announcementSchema = z.object({
  eyebrow: z.string(),
  title: z.string().min(1, '请填写公告标题'),
  subtitle: z.string(),
  body: z.string(),
  image_url: z.string(),
  content_format: z.enum(['markdown', 'html']),
  theme: z.enum(['aurora', 'sunset', 'midnight']),
  cta_label: z.string(),
  cta_link: z.string(),
  is_published: z.boolean(),
  dismissible: z.boolean(),
  show_once: z.boolean(),
  starts_at: z.string(),
  ends_at: z.string(),
});

export type AnnouncementFormValues = z.infer<typeof announcementSchema>;

export const aiGenerateSchema = z.object({
  brief: z.string().min(6, '公告要点至少 6 个字符，描述得更具体一些'),
  cta_goal: z.string(),
  content_format: z.enum(['markdown', 'html']),
  theme: z.enum(['aurora', 'sunset', 'midnight']),
});
export type AiGenerateValues = z.infer<typeof aiGenerateSchema>;

export function formFromAnnouncement(item: Announcement): AnnouncementFormValues {
  return {
    eyebrow: item.eyebrow,
    title: item.title,
    subtitle: item.subtitle,
    body: item.body,
    image_url: item.image_url ?? '',
    content_format: item.content_format,
    theme: item.theme,
    cta_label: item.cta_label ?? '',
    cta_link: item.cta_link ?? '',
    is_published: item.is_published,
    dismissible: item.dismissible,
    show_once: item.show_once,
    starts_at: toLocalInputValue(item.starts_at),
    ends_at: toLocalInputValue(item.ends_at),
  };
}

export const EMPTY_FORM: AnnouncementFormValues = {
  eyebrow: '系统公告',
  title: '',
  subtitle: '',
  body: '',
  image_url: '',
  content_format: 'markdown',
  theme: 'aurora',
  cta_label: '',
  cta_link: '',
  is_published: true,
  dismissible: true,
  show_once: true,
  starts_at: '',
  ends_at: '',
};
