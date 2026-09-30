/**
 * 公告设计台：TanStack Query 数据层 + react-hook-form/zod 表单
 * + shadcn Dialog/AlertDialog/Checkbox。功能与后端 API 不变
 * （services/announcementService.ts），含 AI 公告生成。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { BellRing, CalendarClock, Eye, FileCode, FileText, Loader2, Megaphone, Plus, RefreshCw, Sparkles, Trash2, Wand2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AdminPageHeader, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Checkbox } from '@/components/shadcn/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/shadcn/alert-dialog';
import { cn } from '@/lib/utils';
import {
  Announcement,
  AnnouncementContentFormat,
  AnnouncementGenerateRequest,
  AnnouncementTheme,
  createAnnouncement,
  deleteAnnouncement,
  generateAnnouncement,
  getAnnouncements,
  updateAnnouncement,
} from '@/services/announcementService';
import { THEME_DEFS } from '@/components/announcement/announcementTheme';

/** Basic HTML sanitizer — strips script/event handler attributes */
function sanitizeHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/\bon\w+\s*=\s*["'][^"']*["']/gi, '')
    .replace(/\bon\w+\s*=\s*\S+/gi, '');
}

const FORMAT_META: Record<AnnouncementContentFormat, { label: string; icon: typeof FileText; desc: string }> = {
  markdown: { label: 'Markdown', icon: FileText, desc: '使用 Markdown 语法编写，支持标题、列表、代码块等' },
  html: { label: 'HTML', icon: FileCode, desc: '直接编写 HTML 片段，支持内联样式和布局' },
};

function toLocalInputValue(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}

function fromLocalInputValue(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

// ---------------------------------------------------------------------------
// zod schema
// ---------------------------------------------------------------------------

const announcementSchema = z.object({
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

type AnnouncementFormValues = z.infer<typeof announcementSchema>;

const aiGenerateSchema = z.object({
  brief: z.string().min(6, '公告要点至少 6 个字符，描述得更具体一些'),
  cta_goal: z.string(),
  content_format: z.enum(['markdown', 'html']),
  theme: z.enum(['aurora', 'sunset', 'midnight']),
});
type AiGenerateValues = z.infer<typeof aiGenerateSchema>;

function formFromAnnouncement(item: Announcement): AnnouncementFormValues {
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

const EMPTY_FORM: AnnouncementFormValues = {
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

// ---------------------------------------------------------------------------
// AI 生成弹窗
// ---------------------------------------------------------------------------

function AiGenerateDialog({
  open,
  initialFormat,
  initialTheme,
  onApply,
  onClose,
}: {
  open: boolean;
  initialFormat: AnnouncementContentFormat;
  initialTheme: AnnouncementTheme;
  onApply: (draft: { eyebrow?: string; title?: string; subtitle?: string; body?: string; cta_label?: string; cta_link?: string }) => void;
  onClose: () => void;
}) {
  const form = useForm<AiGenerateValues>({
    resolver: zodResolver(aiGenerateSchema),
    defaultValues: { brief: '', cta_goal: '', content_format: initialFormat, theme: initialTheme },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({
        brief: '',
        cta_goal: '',
        content_format: initialFormat,
        theme: initialTheme,
      });
    }
  }, [open, initialFormat, initialTheme, form]);

  const generateMutation = useMutation({
    mutationFn: (values: AiGenerateValues) => {
      const request: AnnouncementGenerateRequest = {
        brief: values.brief.trim(),
        content_format: values.content_format,
        theme: values.theme,
        cta_goal: values.cta_goal.trim() || null,
      };
      return generateAnnouncement(request);
    },
    onSuccess: (draft) => {
      onApply({
        eyebrow: draft.eyebrow,
        title: draft.title,
        subtitle: draft.subtitle,
        body: draft.body,
        cta_label: draft.cta_label ?? '',
        cta_link: draft.cta_link ?? '',
      });
      toast.success('AI 草稿已生成，请根据需要调整');
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || 'AI 生成失败'),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>AI 公告生成器</DialogTitle>
          <DialogDescription>填写公告需求，选择格式和主题，一键生成完整草稿</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => void generateMutation.mutateAsync(values))}
          className="space-y-5"
        >
          <div className="space-y-1.5">
            <Label htmlFor="ai-brief">
              公告要点 <span className="text-rose-500">*</span>
            </Label>
            <textarea
              id="ai-brief"
              rows={4}
              placeholder="例如：通知用户 PPT 模式新增了 10 套全新设计主题，包括苹果、谷歌、特斯拉等品牌风格，现在可以在导出 PPT 时自由切换。"
              {...form.register('brief')}
              className="w-full resize-y rounded-md border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-800 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
            />
            {form.formState.errors.brief ? (
              <p className="text-xs font-medium text-rose-600">{form.formState.errors.brief.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="ai-cta-goal">CTA 引导目标（可选）</Label>
            <Input id="ai-cta-goal" placeholder="例如：引导用户去 Agent Store 体验" {...form.register('cta_goal')} />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>内容格式</Label>
              <div className="flex rounded-lg border border-zinc-200/80 bg-white p-0.5">
                {(Object.keys(FORMAT_META) as AnnouncementContentFormat[]).map((fmt) => {
                  const meta = FORMAT_META[fmt];
                  const active = form.watch('content_format') === fmt;
                  return (
                    <Button
                      key={fmt}
                      type="button"
                      variant={active ? 'secondary' : 'ghost'}
                      size="xs"
                      className="flex-1 gap-1.5"
                      onClick={() => form.setValue('content_format', fmt)}
                    >
                      <meta.icon size={14} />
                      {meta.label}
                    </Button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>主题风格</Label>
              <div className="grid grid-cols-3 gap-2">
                {(Object.keys(THEME_DEFS) as AnnouncementTheme[]).map((theme) => {
                  const meta = THEME_DEFS[theme];
                  const active = form.watch('theme') === theme;
                  return (
                    <button
                      key={theme}
                      type="button"
                      onClick={() => form.setValue('theme', theme)}
                      className={cn(
                        'rounded-lg border p-2 text-center transition-all',
                        active ? 'border-indigo-300 bg-indigo-50/80 shadow-sm' : 'border-zinc-200/80 bg-white hover:shadow-sm',
                      )}
                    >
                      <div className="h-8 rounded-lg" style={{ background: meta.chipGradient }} />
                      <p className="mt-1.5 text-[11px] font-medium text-zinc-800">{meta.label}</p>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={generateMutation.isPending} className="gap-2">
              {generateMutation.isPending ? null : <Wand2 size={14} />}
              {generateMutation.isPending ? 'AI 生成中...' : '一键生成草稿'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export const AnnouncementManagement = () => {
  const queryClient = useQueryClient();

  const [selectedId, setSelectedId] = React.useState<number | null>(null);
  const [aiDialogOpen, setAiDialogOpen] = React.useState(false);

  const announcementsQuery = useQuery({
    queryKey: ['admin', 'announcements'],
    queryFn: getAnnouncements,
  });
  const items = announcementsQuery.data?.items ?? [];

  const form = useForm<AnnouncementFormValues>({
    resolver: zodResolver(announcementSchema),
    defaultValues: EMPTY_FORM,
  });

  React.useEffect(() => {
    if (announcementsQuery.isSuccess) {
      if (items.length > 0) {
        setSelectedId(items[0].id);
        form.reset(formFromAnnouncement(items[0]));
      } else {
        setSelectedId(null);
        form.reset(EMPTY_FORM);
      }
    }
    // 仅在数据首次加载时同步表单
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [announcementsQuery.isSuccess]);

  const handleSelect = (item: Announcement) => {
    setSelectedId(item.id);
    form.reset(formFromAnnouncement(item));
    setAiDialogOpen(false);
  };

  const handleCreateNew = () => {
    setSelectedId(null);
    form.reset(EMPTY_FORM);
    setAiDialogOpen(false);
  };

  const saveMutation = useMutation({
    mutationFn: async (values: AnnouncementFormValues) => {
      const payload = {
        eyebrow: values.eyebrow.trim() || '系统公告',
        title: values.title.trim(),
        subtitle: values.subtitle.trim(),
        body: values.body.trim(),
        image_url: values.image_url.trim() || null,
        content_format: values.content_format,
        theme: values.theme,
        cta_label: values.cta_label.trim() || null,
        cta_link: values.cta_link.trim() || null,
        is_published: values.is_published,
        dismissible: values.dismissible,
        show_once: values.show_once,
        starts_at: fromLocalInputValue(values.starts_at),
        ends_at: fromLocalInputValue(values.ends_at),
      };
      return selectedId === null
        ? createAnnouncement(payload)
        : updateAnnouncement(selectedId, payload);
    },
    onSuccess: async (saved) => {
      toast.success(selectedId === null ? '公告已创建' : '公告已更新');
      await queryClient.invalidateQueries({ queryKey: ['admin', 'announcements'] });
      setSelectedId(saved.id);
      form.reset(formFromAnnouncement(saved));
    },
    onError: (err: Error) => toast.error(err.message || '公告保存失败'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAnnouncement(id),
    onSuccess: () => {
      toast.success('公告已删除');
      setSelectedId(null);
      form.reset(EMPTY_FORM);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'announcements'] });
    },
    onError: (err: Error) => toast.error(err.message || '公告删除失败'),
  });

  const [deleteConfirmOpen, setDeleteConfirmOpen] = React.useState(false);
  const selectedItem = items.find((item) => item.id === selectedId) ?? null;

  const stats = {
    total: items.length,
    published: items.filter((item) => item.is_published).length,
    activeNow: items.filter((item) => item.active_now).length,
  };

  const formValues = form.watch();
  const previewTheme = THEME_DEFS[formValues.theme];
  const FormatIcon = FORMAT_META[formValues.content_format].icon;

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="Announcement Studio"
        title="用户公告设计台"
        description="撰写支持 Markdown 和 HTML 的公告，或让 AI 帮你一键生成。用户进入聊天或 Agent Store 时就会看到它。"
        actions={
          <>
            <KpiPill label="总公告数" value={stats.total} />
            <KpiPill label="已发布" value={stats.published} />
            <KpiPill label="当前生效" value={stats.activeNow} />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => {
                form.setValue('content_format', formValues.content_format);
                form.setValue('theme', formValues.theme);
                setAiDialogOpen(true);
              }}
            >
              <Wand2 size={14} />
              AI 生成
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void announcementsQuery.refetch()}
              disabled={announcementsQuery.isFetching}
            >
              {announcementsQuery.isFetching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
            <Button size="sm" className="gap-1.5" onClick={handleCreateNew}>
              <Plus size={14} />
              新建公告
            </Button>
          </>
        }
      />

      {announcementsQuery.isError ? (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
          {(announcementsQuery.error as Error).message || '公告加载失败'}
        </div>
      ) : null}

      <AiGenerateDialog
        open={aiDialogOpen}
        initialFormat={formValues.content_format}
        initialTheme={formValues.theme}
        onApply={(draft) => {
          if (draft.eyebrow !== undefined) form.setValue('eyebrow', draft.eyebrow);
          if (draft.title !== undefined) form.setValue('title', draft.title);
          if (draft.subtitle !== undefined) form.setValue('subtitle', draft.subtitle);
          if (draft.body !== undefined) form.setValue('body', draft.body);
          if (draft.cta_label !== undefined) form.setValue('cta_label', draft.cta_label);
          if (draft.cta_link !== undefined) form.setValue('cta_link', draft.cta_link);
        }}
        onClose={() => setAiDialogOpen(false)}
      />

      <section className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        {/* 公告列表 */}
        <div className="rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">已保存公告</p>
              <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">公告列表</h2>
            </div>
            <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-zinc-200/80 bg-white text-zinc-800 shadow-sm">
              <Megaphone size={18} />
            </div>
          </div>

          {announcementsQuery.isLoading ? (
            <div className="flex h-52 items-center justify-center gap-3 rounded-lg border border-dashed border-zinc-200 bg-zinc-50/70 text-sm font-medium text-zinc-500">
              <Loader2 size={16} className="animate-spin" />
              正在加载公告
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-52 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-zinc-200 bg-zinc-50/70 text-center">
              <BellRing size={30} className="text-zinc-300" />
              <div>
                <p className="text-sm font-semibold text-zinc-700">还没有公告</p>
                <p className="mt-1 text-xs font-medium text-zinc-400">先创建一条给用户的入场提示吧。</p>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => handleSelect(item)}
                  className={cn(
                    'w-full rounded-lg border px-4 py-4 text-left transition-all',
                    selectedId === item.id
                      ? 'border-indigo-300 bg-indigo-50/80 shadow-md'
                      : 'border-zinc-200 bg-white hover:border-zinc-300 hover:shadow-sm',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="h-11 w-11 rounded-lg" style={{ background: THEME_DEFS[item.theme].chipGradient }} />
                    <div className="flex flex-wrap justify-end gap-2">
                      <span
                        className={cn(
                          'rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide',
                          item.active_now ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-500',
                        )}
                      >
                        {item.active_now ? 'live' : item.is_published ? 'scheduled' : 'draft'}
                      </span>
                    </div>
                  </div>
                  <p className="mt-4 text-lg font-semibold tracking-tight text-zinc-950">{item.title}</p>
                  <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-zinc-500">
                    {item.subtitle || item.body || '暂无补充文案'}
                  </p>
                  <div className="mt-4 flex items-center justify-between gap-2 text-xs font-semibold text-zinc-400">
                    <div className="flex items-center gap-2">
                      <span>{item.eyebrow}</span>
                      <span
                        className={cn(
                          'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]',
                          item.content_format === 'html' ? 'bg-amber-50 text-amber-600' : 'bg-indigo-50 text-indigo-600',
                        )}
                      >
                        {item.content_format === 'html' ? 'HTML' : 'MD'}
                      </span>
                    </div>
                    <span>{new Date(item.updated_at).toLocaleDateString('zh-CN')}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.1fr)_420px]">
          {/* 编辑器 */}
          <form onSubmit={form.handleSubmit((values) => void saveMutation.mutateAsync(values))} className="rounded-lg border border-zinc-200/80 bg-white p-6 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">编辑器</p>
                <h2 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950">
                  {selectedId === null ? '创建新公告' : '编辑公告'}
                </h2>
                <p className="mt-2 text-sm font-medium leading-7 text-zinc-500">
                  支持 Markdown 和 HTML 两种格式，所见即所得。
                </p>
              </div>

              <div className="flex items-center gap-2">
                {selectedId !== null && (
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    className="gap-1.5"
                    onClick={() => setDeleteConfirmOpen(true)}
                  >
                    <Trash2 size={14} />
                    删除
                  </Button>
                )}
                <Button type="submit" size="sm" disabled={saveMutation.isPending} className="gap-2">
                  <Sparkles size={14} />
                  保存公告
                </Button>
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ann-eyebrow">眉标</Label>
                <Input id="ann-eyebrow" placeholder="系统公告 / 新版本 / 活动预告" {...form.register('eyebrow')} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ann-title">主标题</Label>
                <Input id="ann-title" placeholder="例如：PPT 模式新增原生导出" {...form.register('title')} />
                {form.formState.errors.title ? (
                  <p className="text-xs font-medium text-rose-600">{form.formState.errors.title.message}</p>
                ) : null}
              </div>
              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="ann-subtitle">副标题</Label>
                <Input id="ann-subtitle" placeholder="一句话点明这条公告想让用户先看到什么" {...form.register('subtitle')} />
              </div>

              {/* 正文 + 格式切换 */}
              <div className="md:col-span-2">
                <div className="mb-3 flex items-center justify-between">
                  <Label>正文</Label>
                  <div className="flex rounded-lg border border-zinc-200/80 bg-white p-0.5">
                    {(Object.keys(FORMAT_META) as AnnouncementContentFormat[]).map((fmt) => {
                      const meta = FORMAT_META[fmt];
                      const active = formValues.content_format === fmt;
                      return (
                        <Button
                          key={fmt}
                          type="button"
                          variant={active ? 'secondary' : 'ghost'}
                          size="xs"
                          className="gap-1.5"
                          onClick={() => form.setValue('content_format', fmt)}
                        >
                          <meta.icon size={14} />
                          {meta.label}
                        </Button>
                      );
                    })}
                  </div>
                </div>
                <textarea
                  rows={8}
                  spellCheck={false}
                  placeholder={
                    formValues.content_format === 'markdown'
                      ? '# 更新内容\n\n- 新增功能 A\n- 优化体验 B\n\n> 更多详情请查看文档'
                      : '<h3>更新内容</h3>\n<ul>\n <li>新增功能 A</li>\n <li>优化体验 B</li>\n</ul>'
                  }
                  {...form.register('body')}
                  className="w-full resize-y rounded-md border border-zinc-200 bg-white px-3.5 py-3 font-mono text-sm text-zinc-800 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
                />
                <div className="mt-2 flex items-center gap-2 text-xs font-medium text-zinc-400">
                  <FormatIcon size={12} />
                  <span>
                    {formValues.content_format === 'markdown'
                      ? '支持 Markdown 语法：**加粗** *斜体* `代码` - 列表 # 标题'
                      : '支持 HTML 片段，将直接渲染到公告中'}
                  </span>
                </div>
              </div>

              <div className="space-y-1.5 md:col-span-2">
                <Label htmlFor="ann-image">插图链接（可选）</Label>
                <Input id="ann-image" placeholder="https://example.com/announcement-illustration.png" {...form.register('image_url')} />
              </div>
            </div>

            <div className="mt-6">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">主题风格</p>
              <div className="grid gap-3 md:grid-cols-3">
                {(Object.keys(THEME_DEFS) as AnnouncementTheme[]).map((theme) => {
                  const meta = THEME_DEFS[theme];
                  const active = formValues.theme === theme;
                  return (
                    <button
                      key={theme}
                      type="button"
                      onClick={() => form.setValue('theme', theme)}
                      className={cn(
                        'rounded-lg border p-3 text-left transition-all',
                        active ? 'border-indigo-300 bg-indigo-50/80 shadow-md' : 'border-zinc-200/80 bg-white hover:shadow-sm',
                      )}
                    >
                      <div className="h-16 rounded-lg" style={{ background: meta.chipGradient }} />
                      <p className="mt-3 text-sm font-semibold text-zinc-900">{meta.label}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="ann-cta-label">按钮文案</Label>
                <Input id="ann-cta-label" placeholder="例如：立即体验" {...form.register('cta_label')} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ann-cta-link">按钮链接</Label>
                <Input id="ann-cta-link" placeholder="例如：/agents 或 https://..." {...form.register('cta_link')} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ann-starts-at">开始时间</Label>
                <Input id="ann-starts-at" type="datetime-local" {...form.register('starts_at')} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ann-ends-at">结束时间</Label>
                <Input id="ann-ends-at" type="datetime-local" {...form.register('ends_at')} />
              </div>
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-3">
              <label className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-4 text-sm font-medium text-zinc-600">
                <Checkbox
                  className="mt-1"
                  checked={formValues.is_published}
                  onCheckedChange={(checked) => form.setValue('is_published', checked === true)}
                />
                <span>
                  <span className="block font-semibold text-zinc-900">立即发布</span>
                  保存后直接进入发布状态，配合时间窗决定是否生效。
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-4 text-sm font-medium text-zinc-600">
                <Checkbox
                  className="mt-1"
                  checked={formValues.dismissible}
                  onCheckedChange={(checked) => form.setValue('dismissible', checked === true)}
                />
                <span>
                  <span className="block font-semibold text-zinc-900">允许轻松关闭</span>
                  用户可以点右上角关闭，或点遮罩直接退出。
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white px-4 py-4 text-sm font-medium text-zinc-600">
                <Checkbox
                  className="mt-1"
                  checked={formValues.show_once}
                  onCheckedChange={(checked) => form.setValue('show_once', checked === true)}
                />
                <span>
                  <span className="block font-semibold text-zinc-900">只提醒一次</span>
                  用户关闭后会记住，等你下次修改公告内容再重新展示。
                </span>
              </label>
            </div>
          </form>

          {/* Live Preview */}
          <div className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-zinc-200/80 px-5 py-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">Live Preview</p>
                <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">用户看到的效果</h2>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-zinc-200 bg-white text-zinc-900 shadow-sm">
                <Eye size={17} />
              </div>
            </div>

            <div className="p-5">
              <div
                className="relative overflow-hidden rounded-[34px] border text-zinc-800"
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
                        {formValues.eyebrow || '系统公告'}
                      </span>
                      <div className="flex gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full border border-zinc-200/60 bg-white px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
                          <FormatIcon size={11} />
                          {FORMAT_META[formValues.content_format].label}
                        </span>
                        <span className="rounded-full border border-zinc-200/60 bg-white px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">
                          {previewTheme.label}
                        </span>
                      </div>
                    </div>

                    <h3 className="mt-6 font-display text-3xl font-semibold leading-tight tracking-tight text-zinc-900">
                      {formValues.title || '这里会显示你的公告主标题'}
                    </h3>
                    <p className="mt-4 text-sm font-semibold leading-7 text-zinc-600">
                      {formValues.subtitle || '副标题适合承接标题，让用户一眼知道这条公告为什么值得点开。'}
                    </p>

                    {formValues.body ? (
                      formValues.content_format === 'html' ? (
                        <div
                          className="mt-6 text-sm font-medium leading-7 text-zinc-500"
                          dangerouslySetInnerHTML={{ __html: sanitizeHtml(formValues.body) }}
                        />
                      ) : (
                        <div className="mt-6 text-sm font-medium leading-7 text-zinc-500 [&_strong]:text-zinc-800 [&_h1]:text-zinc-900 [&_h2]:text-zinc-900 [&_h3]:text-zinc-900 [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-zinc-200 [&_pre]:bg-zinc-100 [&_pre]:p-4 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:text-[13px] [&_code]:rounded-md [&_code]:bg-zinc-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.9em] [&_blockquote]:border-l-[3px] [&_blockquote]:border-indigo-300 [&_blockquote]:pl-3.5 [&_blockquote]:my-2.5 [&_blockquote]:italic [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2.5 [&_ul]:space-y-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2.5 [&_ol]:space-y-1 [&_a]:text-indigo-600 [&_a]:underline [&_hr]:my-4">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {formValues.body}
                          </ReactMarkdown>
                        </div>
                      )
                    ) : (
                      <p className="mt-6 text-sm font-medium leading-7 text-zinc-400">
                        正文区域支持 Markdown 或 HTML 语法，写点更丰富的内容吧。
                      </p>
                    )}

                    <div className="mt-8 flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        className={cn('rounded-lg px-5 py-3 text-sm font-semibold text-white shadow-md shadow-black/10', previewTheme.ctaBg)}
                      >
                        {formValues.cta_label || '进入平台'}
                      </button>
                      <span className="inline-flex items-center gap-2 rounded-full border border-zinc-200/60 bg-white px-3 py-2 text-[11px] font-medium tracking-wide text-zinc-500">
                        <CalendarClock size={13} />
                        {formValues.is_published ? '已发布' : '草稿'}
                        {formValues.show_once ? ' · 仅提醒一次' : ' · 每次进入可见'}
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

                    {formValues.image_url ? (
                      <div
                        key={formValues.image_url}
                        className="absolute bottom-5 right-5 z-10 w-[64%] cursor-pointer overflow-hidden rounded-lg border border-zinc-200/80 shadow-md transition-transform hover:scale-[1.03]"
                      >
                        <div className="absolute -inset-2 rounded-lg bg-white/40 blur-md" />
                        <img
                          src={formValues.image_url}
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
                      <div className="absolute bottom-5 right-5 left-5 rounded-lg border border-zinc-200/80 bg-white p-5 shadow-md">
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
                            <p className="text-xs font-semibold text-zinc-800">AgenticOS</p>
                            <p className="text-[10px] font-semibold text-zinc-400">Platform Notice</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-4 rounded-lg border border-zinc-100 bg-zinc-50/80 px-4 py-4 text-xs font-medium leading-6 text-zinc-500">
                预览说明：正文将按照所选格式渲染。Markdown 会自动转换为富文本，HTML 将直接渲染。
                真正对用户生效时，会在进入聊天或 Agent Store 后弹出。
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 删除确认 */}
      <AlertDialog open={deleteConfirmOpen} onOpenChange={setDeleteConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除公告</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除公告「{selectedItem?.title}」吗？用户将不再看到这条公告。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (selectedId !== null) deleteMutation.mutate(selectedId);
              }}
            >
              {deleteMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
