/**
 * 公告设计台：Live Preview 面板（用户看到的效果）。
 * 从 AnnouncementManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { BellRing, CalendarClock, Eye, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AnnouncementFormValues } from './announcementHelpers';
import { FORMAT_META, sanitizeHtml } from './announcementHelpers';
import { THEME_DEFS } from '@/components/announcement/announcementTheme';

export function AnnouncementPreview({ values }: { values: AnnouncementFormValues }) {
  const previewTheme = THEME_DEFS[values.theme];
  const FormatIcon = FORMAT_META[values.content_format].icon;

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-sm">
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">Live Preview</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-[var(--foreground)]">用户看到的效果</h2>
        </div>
        <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] text-[var(--foreground)] shadow-sm">
          <Eye size={17} />
        </div>
      </div>

      <div className="p-5">
        <div
          className="relative overflow-hidden rounded-[34px] border text-[var(--foreground)]"
          style={{
            background: previewTheme.bgGradient,
            boxShadow: previewTheme.shadow,
            borderColor: previewTheme.borderColor,
          }}
        >
          <div className="absolute -left-16 top-6 h-60 w-60 rounded-full blur-3xl" style={{ background: previewTheme.orbA }} />
          <div className="absolute -right-20 -bottom-12 h-72 w-72 rounded-full blur-3xl" style={{ background: previewTheme.orbB }} />
          <div className="absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.7),rgba(255,255,255,0.9),rgba(255,255,255,0.7),transparent)]" />
          <div className="absolute inset-0 bg-[linear-gradient(200deg,rgba(255,255,255,0.42)_0%,transparent_55%,rgba(255,255,255,0.18)_100%)]" />

          <div className="relative z-10 grid gap-0 lg:grid-cols-[1fr_1fr]">
            <div className="p-6">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={cn(
                    'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wide',
                    previewTheme.accentLightClass,
                    previewTheme.accentTextClass,
                  )}
                  style={{ borderColor: 'currentColor', background: 'rgba(255,255,255,0.6)' }}
                >
                  <BellRing size={13} />
                  {values.eyebrow || '系统公告'}
                </span>
                <div className="flex gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full border border-zinc-200/60 bg-[var(--surface-1)] px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                    <FormatIcon size={11} />
                    {FORMAT_META[values.content_format].label}
                  </span>
                  <span className="rounded-full border border-zinc-200/60 bg-[var(--surface-1)] px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                    {previewTheme.label}
                  </span>
                </div>
              </div>

              <h3 className="mt-6 font-display text-3xl font-semibold leading-tight tracking-tight text-[var(--foreground)]">
                {values.title || '这里会显示你的公告主标题'}
              </h3>
              <p className="mt-4 text-sm font-semibold leading-7 text-zinc-600">
                {values.subtitle || '副标题适合承接标题，让用户一眼知道这条公告为什么值得点开。'}
              </p>

              {values.body ? (
                values.content_format === 'html' ? (
                  <div
                    className="mt-6 text-sm font-medium leading-7 text-[var(--muted-foreground)]"
                    dangerouslySetInnerHTML={{ __html: sanitizeHtml(values.body) }}
                  />
                ) : (
                  <div className="mt-6 text-sm font-medium leading-7 text-[var(--muted-foreground)] [&_strong]:text-[var(--foreground)] [&_h1]:text-[var(--foreground)] [&_h2]:text-[var(--foreground)] [&_h3]:text-[var(--foreground)] [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-[var(--border-subtle)] [&_pre]:bg-[var(--surface-2)] [&_pre]:p-4 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:text-[13px] [&_code]:rounded-md [&_code]:bg-[var(--surface-2)] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.9em] [&_blockquote]:border-l-[3px] [&_blockquote]:border-indigo-300 [&_blockquote]:pl-3.5 [&_blockquote]:my-2.5 [&_blockquote]:italic [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2.5 [&_ul]:space-y-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2.5 [&_ol]:space-y-1 [&_a]:text-indigo-600 [&_a]:underline [&_hr]:my-4">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {values.body}
                    </ReactMarkdown>
                  </div>
                )
              ) : (
                <p className="mt-6 text-sm font-medium leading-7 text-[var(--muted-foreground)]">
                  正文区域支持 Markdown 或 HTML 语法，写点更丰富的内容吧。
                </p>
              )}

              <div className="mt-8 flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className={cn('rounded-lg px-5 py-3 text-sm font-semibold text-white shadow-md shadow-black/10', previewTheme.ctaBg)}
                >
                  {values.cta_label || '进入平台'}
                </button>
                <span className="inline-flex items-center gap-2 rounded-full border border-zinc-200/60 bg-[var(--surface-1)] px-3 py-2 text-[11px] font-medium tracking-wide text-[var(--muted-foreground)]">
                  <CalendarClock size={13} />
                  {values.is_published ? '已发布' : '草稿'}
                  {values.show_once ? ' · 仅提醒一次' : ' · 每次进入可见'}
                </span>
              </div>
            </div>

            {/* Right decoration panel */}
            <div className="relative hidden min-h-[320px] overflow-hidden lg:block">
              <div className="absolute -right-4 -top-6 h-40 w-40 rounded-full blur-2xl" style={{ background: previewTheme.orbA }} />
              <div className="absolute -left-2 bottom-8 h-36 w-36 rounded-full blur-2xl" style={{ background: previewTheme.orbB }} />
              <div className="absolute right-12 top-1/2 h-24 w-24 rounded-full blur-2xl" style={{ background: previewTheme.orbC }} />

              <div className="absolute right-10 top-10 h-2 w-2 rounded-full" style={{ background: previewTheme.dotColor, boxShadow: `0 0 8px ${previewTheme.dotColor}` }} />
              <div className="absolute right-24 top-24 h-1.5 w-1.5 rounded-full" style={{ background: previewTheme.dotColor }} />
              <div className="absolute left-6 top-14 h-1.5 w-1.5 rounded-full" style={{ background: previewTheme.dotColor }} />
              <div className="absolute right-16 bottom-24 h-1 w-1 rounded-full" style={{ background: previewTheme.dotColor }} />

              <div
                className="absolute inset-0 opacity-[0.06]"
                style={{
                  backgroundImage: 'radial-gradient(rgba(15,23,42,0.35) 0.5px, transparent 0.5px)',
                  backgroundSize: '18px 18px',
                }}
              />

              <div className="absolute inset-0 bg-[linear-gradient(200deg,rgba(255,255,255,0.36)_0%,transparent_50%,rgba(255,255,255,0.14)_100%)]" />

              {values.image_url ? (
                <div
                  key={values.image_url}
                  className="absolute bottom-5 right-5 z-10 w-[64%] cursor-pointer overflow-hidden rounded-lg border border-[var(--border-subtle)] shadow-md transition-transform hover:scale-[1.03]"
                >
                  <div className="absolute -inset-2 rounded-lg bg-white/40 blur-md" />
                  <img
                    src={values.image_url}
                    alt="announcement illustration"
                    className="relative w-full rounded-lg object-cover"
                    style={{ aspectRatio: '4/3' }}
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                  <div className="absolute inset-0 rounded-lg bg-[linear-gradient(35deg,rgba(0,0,0,0.06)_0%,transparent_45%,rgba(255,255,255,0.08)_100%)]" />
                </div>
              ) : (
                <div className="absolute bottom-5 right-5 left-5 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-5 shadow-md">
                  <div className="mb-2 h-1.5 w-10 rounded-full bg-zinc-300/80" />
                  <div className="space-y-2">
                    <div className="h-2.5 w-full rounded-full bg-zinc-200/90" />
                    <div className="h-2.5 w-4/5 rounded-full bg-zinc-200/80" />
                    <div className="h-2.5 w-3/5 rounded-full bg-zinc-200/70" />
                  </div>
                  <div className="mt-4 flex items-center gap-2.5">
                    <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg text-white shadow-md', previewTheme.accentClass)}>
                      <Sparkles size={13} />
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-[var(--foreground)]">AgenticOS</p>
                      <p className="text-[10px] font-semibold text-[var(--muted-foreground)]">Platform Notice</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-zinc-100 bg-zinc-50/80 px-4 py-4 text-xs font-medium leading-6 text-[var(--muted-foreground)]">
          预览说明：正文将按照所选格式渲染。Markdown 会自动转换为富文本，HTML 将直接渲染。
          真正对用户生效时，会在进入聊天或 Agent Store 后弹出。
        </div>
      </div>
    </div>
  );
}
