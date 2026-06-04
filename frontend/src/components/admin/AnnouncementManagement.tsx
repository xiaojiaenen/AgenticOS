import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import { BellRing, CalendarClock, Eye, FileCode, FileText, Loader2, Megaphone, Plus, RefreshCw, Sparkles, Trash2, Wand2, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { toast } from '../ui/Toast';
import {
  Announcement,
  AnnouncementContentFormat,
  AnnouncementGenerateRequest,
  AnnouncementPayload,
  AnnouncementTheme,
  createAnnouncement,
  deleteAnnouncement,
  generateAnnouncement,
  getAnnouncements,
  updateAnnouncement,
} from '../../services/announcementService';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '../../lib/utils';
import { useAdminModalBackdrop } from './useAdminModalBackdrop';
import { THEME_DEFS } from '../announcement/announcementTheme';

type AnnouncementForm = {
  eyebrow: string;
  title: string;
  subtitle: string;
  body: string;
  image_url: string;
  content_format: AnnouncementContentFormat;
  theme: AnnouncementTheme;
  cta_label: string;
  cta_link: string;
  is_published: boolean;
  dismissible: boolean;
  show_once: boolean;
  starts_at: string;
  ends_at: string;
};


const FORMAT_META: Record<AnnouncementContentFormat, { label: string; icon: typeof FileText; desc: string }> = {
  markdown: { label: 'Markdown', icon: FileText, desc: '使用 Markdown 语法编写，支持标题、列表、代码块等' },
  html: { label: 'HTML', icon: FileCode, desc: '直接编写 HTML 片段，支持内联样式和布局' },
};

const EMPTY_FORM: AnnouncementForm = {
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

function formatAnnouncementForm(item: Announcement): AnnouncementForm {
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

function buildPayload(form: AnnouncementForm): AnnouncementPayload {
  return {
    eyebrow: form.eyebrow.trim() || '系统公告',
    title: form.title.trim(),
    subtitle: form.subtitle.trim(),
    body: form.body.trim(),
    image_url: form.image_url.trim() || null,
    content_format: form.content_format,
    theme: form.theme,
    cta_label: form.cta_label.trim() || null,
    cta_link: form.cta_link.trim() || null,
    is_published: form.is_published,
    dismissible: form.dismissible,
    show_once: form.show_once,
    starts_at: fromLocalInputValue(form.starts_at),
    ends_at: fromLocalInputValue(form.ends_at),
  };
}




export const AnnouncementManagement = () => {
  const [items, setItems] = useState<Announcement[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [form, setForm] = useState<AnnouncementForm>(EMPTY_FORM);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showAIPanel, setShowAIPanel] = useState(false);
  const [aiBrief, setAiBrief] = useState('');
  const [aiCtaGoal, setAiCtaGoal] = useState('');
  const [aiFormat, setAiFormat] = useState<AnnouncementContentFormat>('markdown');
  const [aiTheme, setAiTheme] = useState<AnnouncementTheme>('aurora');
  const [isGenerating, setIsGenerating] = useState(false);

  useAdminModalBackdrop(showAIPanel);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedId) ?? null,
    [items, selectedId],
  );

  const stats = useMemo(
    () => ({
      total: items.length,
      published: items.filter((item) => item.is_published).length,
      activeNow: items.filter((item) => item.active_now).length,
    }),
    [items],
  );

  const loadAnnouncements = useCallback(async (preferredId?: number | null) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAnnouncements();
      setItems(response.items);
      if (response.items.length > 0) {
        const next = preferredId
          ? response.items.find((item) => item.id === preferredId) ?? response.items[0]
          : response.items[0];
        setSelectedId(next.id);
        setForm(formatAnnouncementForm(next));
      } else {
        setSelectedId(null);
        setForm(EMPTY_FORM);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '公告加载失败');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAnnouncements();
  }, [loadAnnouncements]);

  const handleSelect = (item: Announcement) => {
    setSelectedId(item.id);
    setForm(formatAnnouncementForm(item));
    setError(null);
    setShowAIPanel(false);
  };

  const handleCreateNew = () => {
    setSelectedId(null);
    setForm(EMPTY_FORM);
    setError(null);
    setShowAIPanel(false);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      const payload = buildPayload(form);
      if (!payload.title) {
        throw new Error('请先填写公告标题');
      }
      const saved = selectedId === null
        ? await createAnnouncement(payload)
        : await updateAnnouncement(selectedId, payload);
      await loadAnnouncements(saved.id);
      setSelectedId(saved.id);
      setForm(formatAnnouncementForm(saved));
      toast(selectedId === null ? '公告已创建' : '公告已更新', { variant: 'success' });
    } catch (err) {
      const message = err instanceof Error ? err.message : '公告保存失败';
      setError(message);
      toast(message, { variant: 'error' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (selectedId === null || !selectedItem) return;
    const confirmed = window.confirm(`确认删除公告「${selectedItem.title}」吗？`);
    if (!confirmed) return;

    setIsDeleting(true);
    setError(null);
    try {
      await deleteAnnouncement(selectedId);
      toast('公告已删除', { variant: 'success' });
      await loadAnnouncements();
    } catch (err) {
      const message = err instanceof Error ? err.message : '公告删除失败';
      setError(message);
      toast(message, { variant: 'error' });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleAIGenerate = async () => {
    const trimmed = aiBrief.trim();
    if (!trimmed) {
      toast('请先描述公告要点', { variant: 'error' });
      return;
    }
    if (trimmed.length < 6) {
      toast('公告要点至少 6 个字符，描述得更具体一些吧', { variant: 'error' });
      return;
    }
    setIsGenerating(true);
    try {
      const request: AnnouncementGenerateRequest = {
        brief: trimmed,
        content_format: aiFormat,
        theme: aiTheme,
        cta_goal: aiCtaGoal.trim() || null,
      };
      const draft = await generateAnnouncement(request);
      setForm((prev) => ({
        ...prev,
        eyebrow: draft.eyebrow,
        title: draft.title,
        subtitle: draft.subtitle,
        body: draft.body,
        cta_label: draft.cta_label ?? '',
        cta_link: draft.cta_link ?? '',
      }));
      toast('AI 草稿已生成，请根据需要调整', { variant: 'success' });
      setShowAIPanel(false);
      setAiBrief('');
      setAiCtaGoal('');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'AI 生成失败';
      toast(message, { variant: 'error' });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleApplyAIDraft = (draft: { eyebrow?: string; title?: string; subtitle?: string; body?: string; cta_label?: string; cta_link?: string }) => {
    setForm((prev) => ({
      ...prev,
      eyebrow: draft.eyebrow ?? prev.eyebrow,
      title: draft.title ?? prev.title,
      subtitle: draft.subtitle ?? prev.subtitle,
      body: draft.body ?? prev.body,
      cta_label: draft.cta_label ?? prev.cta_label,
      cta_link: draft.cta_link ?? prev.cta_link,
    }));
    setShowAIPanel(false);
  };

  const previewTheme = THEME_DEFS[form.theme];
  const FormatIcon = FORMAT_META[form.content_format].icon;

  return (
    <div className="admin-page-stage space-y-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_420px]">
        <div className="rounded-[28px] border border-white/65 bg-[linear-gradient(135deg,rgba(255,255,255,0.82),rgba(255,255,255,0.50),rgba(186,230,253,0.36))] p-6 shadow-md">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p className="admin-section-kicker">Announcement Studio</p>
              <h1 className="mt-1.5 text-3xl font-black tracking-tight text-slate-950">用户公告设计台</h1>
              <p className="mt-3 max-w-3xl text-sm font-medium leading-7 text-slate-500">
                撰写支持 Markdown 和 HTML 的公告，或让 AI 帮你一键生成。用户进入聊天或 Agent Store 时就会看到它。
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <Button variant="ghost" onClick={() => {
                setAiFormat(form.content_format);
                setAiTheme(form.theme);
                setShowAIPanel((prev) => !prev);
              }} className="gap-2" size="sm">
                <Wand2 size={14} />
                AI 生成
              </Button>
              <Button variant="secondary" onClick={() => loadAnnouncements()} disabled={isLoading} className="gap-2" size="sm">
                {isLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                刷新
              </Button>
              <Button onClick={handleCreateNew} className="gap-2" size="sm">
                <Plus size={14} />
                新建公告
              </Button>
            </div>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
          <div className="admin-stat-card rounded-3xl border border-white/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.82),rgba(255,255,255,0.62),rgba(56,189,248,0.18))] px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.16em] text-slate-400">总公告数</p>
            <p className="mt-2 text-3xl font-black tracking-tight text-slate-950">{stats.total}</p>
          </div>
          <div className="admin-stat-card rounded-3xl border border-white/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.82),rgba(255,255,255,0.62),rgba(251,191,36,0.16))] px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.16em] text-slate-400">已发布</p>
            <p className="mt-2 text-3xl font-black tracking-tight text-slate-950">{stats.published}</p>
          </div>
          <div className="admin-stat-card rounded-3xl border border-white/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.82),rgba(255,255,255,0.62),rgba(16,185,129,0.18))] px-5 py-4">
            <p className="text-[11px] font-black uppercase tracking-[0.16em] text-slate-400">当前生效</p>
            <p className="mt-2 text-3xl font-black tracking-tight text-slate-950">{stats.activeNow}</p>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          {error}
        </div>
      )}

      {/* AI Generation Modal */}
      {typeof document !== 'undefined' && createPortal(
        <AnimatePresence>
          {showAIPanel && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="admin-modal-shell"
              onMouseDown={() => setShowAIPanel(false)}
            >
              <motion.div
                initial={{ opacity: 0, y: 24, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 24, scale: 0.96 }}
                transition={{ duration: 0.22 }}
                onMouseDown={(event) => event.stopPropagation()}
                className="admin-solid-panel admin-modal-panel w-full max-w-xl p-0"
              >
                <div className="flex items-start justify-between border-b border-slate-100 px-6 py-4">
                  <div>
                    <p className="admin-section-kicker">AI 公告生成器</p>
                    <h3 className="mt-1.5 text-xl font-black tracking-tight text-slate-900">用一句话描述公告要点</h3>
                    <p className="mt-1 text-sm font-medium text-slate-500">
                      填写公告需求，选择格式和主题，一键生成完整草稿
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowAIPanel(false)}
                    className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600"
                  >
                    <X size={19} />
                  </button>
                </div>

                <div className="p-6 space-y-5">
                  <div>
                    <label className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                      公告要点 <span className="text-rose-500">*</span>
                    </label>
                    <textarea
                      value={aiBrief}
                      onChange={(e) => setAiBrief(e.target.value)}
                      rows={4}
                      placeholder="例如：通知用户 PPT 模式新增了 10 套全新设计主题，包括苹果、谷歌、特斯拉等品牌风格，现在可以在导出 PPT 时自由切换。"
                      className="w-full rounded-[22px] border border-white/75 bg-white/72 px-5 py-4 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-brand-200 focus:bg-white focus:ring-4 focus:ring-brand-100/80"
                    />
                  </div>

                  <div>
                    <label className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                      CTA 引导目标（可选）
                    </label>
                    <input
                      value={aiCtaGoal}
                      onChange={(e) => setAiCtaGoal(e.target.value)}
                      placeholder="例如：引导用户去 Agent Store 体验"
                      className="w-full rounded-[22px] border border-white/75 bg-white/72 px-5 py-4 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-brand-200 focus:bg-white focus:ring-4 focus:ring-brand-100/80"
                    />
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                        内容格式
                      </label>
                      <div className="flex rounded-2xl border border-white/70 bg-white/70 p-0.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
                        {(Object.keys(FORMAT_META) as AnnouncementContentFormat[]).map((fmt) => {
                          const meta = FORMAT_META[fmt];
                          const active = aiFormat === fmt;
                          return (
                            <button
                              key={fmt}
                              type="button"
                              onClick={() => setAiFormat(fmt)}
                              className={cn(
                                'flex flex-1 items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold transition-all',
                                active
                                  ? 'bg-white text-slate-800 shadow-sm'
                                  : 'text-slate-500 hover:text-slate-700',
                              )}
                            >
                              <meta.icon size={14} />
                              {meta.label}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div>
                      <label className="mb-2 ml-1 block text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                        主题风格
                      </label>
                      <div className="grid grid-cols-3 gap-2">
                        {(Object.keys(THEME_DEFS) as AnnouncementTheme[]).map((theme) => {
                          const meta = THEME_DEFS[theme];
                          const active = aiTheme === theme;
                          return (
                            <button
                              key={theme}
                              type="button"
                              onClick={() => setAiTheme(theme)}
                              className={cn(
                                'rounded-2xl border p-2 text-center transition-all',
                                active
                                  ? 'border-sky-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(224,242,254,0.9))] shadow-sm'
                                  : 'border-white/70 bg-white/65 hover:shadow-sm',
                              )}
                            >
                              <div className="h-8 rounded-xl" style={{ background: meta.chipGradient }} />
                              <p className="mt-1.5 text-[11px] font-bold text-slate-800">{meta.label}</p>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end gap-3 border-t border-white/60 px-6 py-4">
                  <Button variant="secondary" size="sm" onClick={() => setShowAIPanel(false)}>
                    取消
                  </Button>
                  <Button size="sm" onClick={handleAIGenerate} disabled={isGenerating} isLoading={isGenerating} className="gap-2">
                    {isGenerating ? null : <Wand2 size={14} />}
                    {isGenerating ? 'AI 生成中...' : '一键生成草稿'}
                  </Button>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body,
      )}

      <section className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <div className="admin-solid-panel p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="admin-section-kicker">已保存公告</p>
              <h2 className="mt-1 text-xl font-black tracking-tight text-slate-950">公告列表</h2>
            </div>
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/70 bg-white/75 text-slate-800 shadow-sm">
              <Megaphone size={18} />
            </div>
          </div>

          {isLoading ? (
            <div className="flex h-52 items-center justify-center gap-3 rounded-3xl border border-dashed border-slate-200 bg-slate-50/70 text-sm font-bold text-slate-500">
              <Loader2 size={16} className="animate-spin" />
              正在加载公告
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-52 flex-col items-center justify-center gap-3 rounded-3xl border border-dashed border-slate-200 bg-slate-50/70 text-center">
              <BellRing size={30} className="text-slate-300" />
              <div>
                <p className="text-sm font-black text-slate-700">还没有公告</p>
                <p className="mt-1 text-xs font-medium text-slate-400">先创建一条给用户的入场提示吧。</p>
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
                    'w-full rounded-3xl border px-4 py-4 text-left transition-all',
                    selectedId === item.id
                      ? 'border-sky-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(224,242,254,0.92))] shadow-md'
                      : 'border-white/75 bg-white/72 hover:-translate-y-0.5 hover:border-slate-200 hover:shadow-sm',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="h-11 w-11 rounded-2xl" style={{ background: THEME_DEFS[item.theme].chipGradient }} />
                    <div className="flex flex-wrap justify-end gap-2">
                      <span className={cn(
                        'rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-[0.16em]',
                        item.active_now ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-500',
                      )}>
                        {item.active_now ? 'live' : item.is_published ? 'scheduled' : 'draft'}
                      </span>
                    </div>
                  </div>
                  <p className="mt-4 text-lg font-black tracking-tight text-slate-950">{item.title}</p>
                  <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-slate-500">
                    {item.subtitle || item.body || '暂无补充文案'}
                  </p>
                  <div className="mt-4 flex items-center justify-between gap-2 text-xs font-semibold text-slate-400">
                    <div className="flex items-center gap-2">
                      <span>{item.eyebrow}</span>
                      <span className={cn(
                        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px]',
                        item.content_format === 'html'
                          ? 'bg-amber-50 text-amber-600'
                          : 'bg-sky-50 text-sky-600',
                      )}>
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
          <form onSubmit={handleSave} className="admin-solid-panel p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="admin-section-kicker">编辑器</p>
                <h2 className="mt-1 text-2xl font-black tracking-tight text-slate-950">
                  {selectedId === null ? '创建新公告' : '编辑公告'}
                </h2>
                <p className="mt-2 text-sm font-medium leading-7 text-slate-500">
                  支持 Markdown 和 HTML 两种格式，所见即所得。
                </p>
              </div>

              <div className="flex items-center gap-2">
                {selectedId !== null && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={handleDelete}
                    disabled={isDeleting || isSaving}
                    className="gap-2"
                  >
                    {isDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    删除
                  </Button>
                )}
                <Button type="submit" size="sm" isLoading={isSaving} className="gap-2">
                  <Sparkles size={14} />
                  保存公告
                </Button>
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <Input
                label="眉标"
                value={form.eyebrow}
                onChange={(event) => setForm((prev) => ({ ...prev, eyebrow: event.target.value }))}
                placeholder="系统公告 / 新版本 / 活动预告"
              />
              <Input
                label="主标题"
                value={form.title}
                onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
                placeholder="例如：PPT 模式新增原生导出"
              />
              <div className="md:col-span-2">
                <Input
                  label="副标题"
                  value={form.subtitle}
                  onChange={(event) => setForm((prev) => ({ ...prev, subtitle: event.target.value }))}
                  placeholder="一句话点明这条公告想让用户先看到什么"
                />
              </div>

              {/* Content Format Toggle */}
              <div className="md:col-span-2">
                <div className="mb-3 flex items-center justify-between">
                  <label className="ml-1 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">
                    正文
                  </label>
                  <div className="flex rounded-2xl border border-white/70 bg-white/70 p-0.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
                    {(Object.keys(FORMAT_META) as AnnouncementContentFormat[]).map((fmt) => {
                      const meta = FORMAT_META[fmt];
                      const active = form.content_format === fmt;
                      return (
                        <button
                          key={fmt}
                          type="button"
                          onClick={() => setForm((prev) => ({ ...prev, content_format: fmt }))}
                          className={cn(
                            'flex items-center gap-1.5 rounded-xl px-3.5 py-1.5 text-xs font-bold transition-all',
                            active
                              ? 'bg-white text-slate-800 shadow-sm'
                              : 'text-slate-500 hover:text-slate-700',
                          )}
                        >
                          <meta.icon size={14} />
                          {meta.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <textarea
                  value={form.body}
                  onChange={(event) => setForm((prev) => ({ ...prev, body: event.target.value }))}
                  rows={8}
                  placeholder={
                    form.content_format === 'markdown'
                      ? '# 更新内容\n\n- 新增功能 A\n- 优化体验 B\n\n> 更多详情请查看文档'
                      : '<h3>更新内容</h3>\n<ul>\n  <li>新增功能 A</li>\n  <li>优化体验 B</li>\n</ul>'
                  }
                  className="w-full rounded-[22px] border border-white/75 bg-white/72 px-5 py-4 text-sm font-semibold text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition-all placeholder:text-slate-400 focus:border-brand-200 focus:bg-white focus:ring-4 focus:ring-brand-100/80 font-mono"
                  spellCheck={false}
                />
                <div className="mt-2 ml-2 flex items-center gap-2 text-xs font-medium text-slate-400">
                  <FormatIcon size={12} />
                  <span>
                    {form.content_format === 'markdown'
                      ? '支持 Markdown 语法：**加粗** *斜体* `代码` - 列表 # 标题'
                      : '支持 HTML 片段，将直接渲染到公告中'}
                  </span>
                </div>
              </div>

              <div className="md:col-span-2">
                <Input
                  label="插图链接（可选）"
                  value={form.image_url}
                  onChange={(event) => setForm((prev) => ({ ...prev, image_url: event.target.value }))}
                  placeholder="https://example.com/announcement-illustration.png"
                />
              </div>
            </div>

            <div className="mt-6">
              <p className="mb-3 ml-1 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">主题风格</p>
              <div className="grid gap-3 md:grid-cols-3">
                {(Object.keys(THEME_DEFS) as AnnouncementTheme[]).map((theme) => {
                  const meta = THEME_DEFS[theme];
                  const active = form.theme === theme;
                  return (
                    <button
                      key={theme}
                      type="button"
                      onClick={() => setForm((prev) => ({ ...prev, theme }))}
                      className={cn(
                        'rounded-3xl border p-3 text-left transition-all',
                        active
                          ? 'border-sky-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(224,242,254,0.9))] shadow-md'
                          : 'border-white/70 bg-white/65 hover:-translate-y-0.5 hover:shadow-sm',
                      )}
                    >
                      <div className="h-16 rounded-2xl" style={{ background: meta.chipGradient }} />
                      <p className="mt-3 text-sm font-black text-slate-900">{meta.label}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <Input
                label="按钮文案"
                value={form.cta_label}
                onChange={(event) => setForm((prev) => ({ ...prev, cta_label: event.target.value }))}
                placeholder="例如：立即体验"
              />
              <Input
                label="按钮链接"
                value={form.cta_link}
                onChange={(event) => setForm((prev) => ({ ...prev, cta_link: event.target.value }))}
                placeholder="例如：/agents 或 https://..."
              />
              <Input
                label="开始时间"
                type="datetime-local"
                value={form.starts_at}
                onChange={(event) => setForm((prev) => ({ ...prev, starts_at: event.target.value }))}
              />
              <Input
                label="结束时间"
                type="datetime-local"
                value={form.ends_at}
                onChange={(event) => setForm((prev) => ({ ...prev, ends_at: event.target.value }))}
              />
            </div>

            <div className="mt-6 grid gap-3 md:grid-cols-3">
              <label className="flex items-start gap-3 rounded-3xl border border-white/75 bg-white/70 px-4 py-4 text-sm font-semibold text-slate-600">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-sky-500"
                  checked={form.is_published}
                  onChange={(event) => setForm((prev) => ({ ...prev, is_published: event.target.checked }))}
                />
                <span>
                  <span className="block font-black text-slate-900">立即发布</span>
                  保存后直接进入发布状态，配合时间窗决定是否生效。
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-3xl border border-white/75 bg-white/70 px-4 py-4 text-sm font-semibold text-slate-600">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-sky-500"
                  checked={form.dismissible}
                  onChange={(event) => setForm((prev) => ({ ...prev, dismissible: event.target.checked }))}
                />
                <span>
                  <span className="block font-black text-slate-900">允许轻松关闭</span>
                  用户可以点右上角关闭，或点遮罩直接退出。
                </span>
              </label>
              <label className="flex items-start gap-3 rounded-3xl border border-white/75 bg-white/70 px-4 py-4 text-sm font-semibold text-slate-600">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-sky-500"
                  checked={form.show_once}
                  onChange={(event) => setForm((prev) => ({ ...prev, show_once: event.target.checked }))}
                />
                <span>
                  <span className="block font-black text-slate-900">只提醒一次</span>
                  用户关闭后会记住，等你下次修改公告内容再重新展示。
                </span>
              </label>
            </div>
          </form>

          <div className="admin-solid-panel overflow-hidden p-0">
            <div className="flex items-center justify-between border-b border-white/70 px-5 py-4">
              <div>
                <p className="admin-section-kicker">Live Preview</p>
                <h2 className="mt-1 text-xl font-black tracking-tight text-slate-950">用户看到的效果</h2>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/75 bg-white/80 text-slate-900 shadow-sm">
                <Eye size={17} />
              </div>
            </div>

            <div className="p-5">
              <div
                className="relative overflow-hidden rounded-[34px] border text-slate-800"
                style={{
                  background: previewTheme.bgGradient,
                  boxShadow: previewTheme.shadow,
                  borderColor: previewTheme.borderColor,
                }}
              >
                {/* ambient orbs */}
                <div className="absolute -left-16 top-6 h-60 w-60 rounded-full blur-3xl" style={{ background: previewTheme.orbA }} />
                <div className="absolute -right-20 -bottom-12 h-72 w-72 rounded-full blur-3xl" style={{ background: previewTheme.orbB }} />
                {/* top-edge highlight */}
                <div className="absolute inset-x-0 top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.7),rgba(255,255,255,0.9),rgba(255,255,255,0.7),transparent)]" />
                {/* right-side gradient wash */}
                <div className="absolute inset-0 bg-[linear-gradient(200deg,rgba(255,255,255,0.42)_0%,transparent_55%,rgba(255,255,255,0.18)_100%)]" />

                <div className="relative z-10 grid gap-0 lg:grid-cols-[1fr_1fr]">
                  <div className="p-6">
                    <div className="flex items-center gap-3 flex-wrap">
                      <span
                        className={cn(
                          'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-black uppercase tracking-[0.18em]',
                          previewTheme.accentLightClass, previewTheme.accentTextClass,
                        )}
                        style={{ borderColor: 'currentColor', background: 'rgba(255,255,255,0.6)' }}
                      >
                        <BellRing size={13} />
                        {form.eyebrow || '系统公告'}
                      </span>
                      <div className="flex gap-2">
                        <span className="inline-flex items-center gap-1 rounded-full border border-slate-200/60 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                          <FormatIcon size={11} />
                          {FORMAT_META[form.content_format].label}
                        </span>
                        <span className="rounded-full border border-slate-200/60 bg-white/70 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                          {previewTheme.label}
                        </span>
                      </div>
                    </div>

                    <h3 className="mt-6 font-display text-3xl font-black leading-tight tracking-[-0.03em] text-slate-900">
                      {form.title || '这里会显示你的公告主标题'}
                    </h3>
                    <p className="mt-4 text-sm font-semibold leading-7 text-slate-600">
                      {form.subtitle || '副标题适合承接标题，让用户一眼知道这条公告为什么值得点开。'}
                    </p>

                    {form.body ? (
                      form.content_format === 'html' ? (
                        <div
                          className="mt-6 text-sm font-medium leading-7 text-slate-500"
                          dangerouslySetInnerHTML={{ __html: form.body }}
                        />
                      ) : (
                        <div className="mt-6 text-sm font-medium leading-7 text-slate-500 [&_strong]:text-slate-800 [&_h1]:text-slate-900 [&_h2]:text-slate-900 [&_h3]:text-slate-900 [&_pre]:bg-slate-100 [&_pre]:border [&_pre]:border-slate-200 [&_pre]:rounded-xl [&_pre]:p-4 [&_pre]:my-3 [&_pre]:overflow-x-auto [&_pre]:text-[13px] [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded-md [&_code]:text-[0.9em] [&_code]:text-brand-700 [&_blockquote]:border-l-[3px] [&_blockquote]:border-brand-300 [&_blockquote]:pl-3.5 [&_blockquote]:my-2.5 [&_blockquote]:text-slate-500 [&_blockquote]:italic [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:my-2.5 [&_ul]:space-y-1 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:my-2.5 [&_ol]:space-y-1 [&_a]:text-brand-600 [&_a]:underline [&_hr]:border-t [&_hr]:border-slate-200 [&_hr]:my-4">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {form.body}
                          </ReactMarkdown>
                        </div>
                      )
                    ) : (
                      <p className="mt-6 text-sm font-medium leading-7 text-slate-400">
                        正文区域支持 Markdown 或 HTML 语法，写点更丰富的内容吧。
                      </p>
                    )}

                    <div className="mt-8 flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        className={cn(
                          'rounded-2xl px-5 py-3 text-sm font-black text-white shadow-lg shadow-black/10',
                          previewTheme.ctaBg,
                        )}
                      >
                        {form.cta_label || '进入平台'}
                      </button>
                      <span className="inline-flex items-center gap-2 rounded-full border border-slate-200/60 bg-white/70 px-3 py-2 text-[11px] font-bold tracking-[0.08em] text-slate-500">
                        <CalendarClock size={13} />
                        {form.is_published ? '已发布' : '草稿'}
                        {form.show_once ? ' · 仅提醒一次' : ' · 每次进入可见'}
                      </span>
                    </div>
                  </div>

                  {/* Right decoration panel */}
                  <div className="relative hidden min-h-[320px] overflow-hidden lg:block">
                    {/* soft ambient orbs */}
                    <div className="absolute -right-4 -top-6 h-40 w-40 rounded-full blur-2xl" style={{ background: previewTheme.orbA }} />
                    <div className="absolute -left-2 bottom-8 h-36 w-36 rounded-full blur-2xl" style={{ background: previewTheme.orbB }} />
                    <div className="absolute right-12 top-1/2 h-24 w-24 rounded-full blur-2xl" style={{ background: previewTheme.orbC }} />

                    {/* floating dots */}
                    <div className="absolute right-10 top-10 h-2 w-2 rounded-full" style={{ background: previewTheme.dotColor, boxShadow: `0 0 8px ${previewTheme.dotColor}` }} />
                    <div className="absolute right-24 top-24 h-1.5 w-1.5 rounded-full" style={{ background: previewTheme.dotColor }} />
                    <div className="absolute left-6 top-14 h-1.5 w-1.5 rounded-full" style={{ background: previewTheme.dotColor }} />
                    <div className="absolute right-16 bottom-24 h-1 w-1 rounded-full" style={{ background: previewTheme.dotColor }} />

                    {/* dot grid */}
                    <div
                      className="absolute inset-0 opacity-[0.06]"
                      style={{
                        backgroundImage: 'radial-gradient(rgba(15,23,42,0.35) 0.5px, transparent 0.5px)',
                        backgroundSize: '18px 18px',
                      }}
                    />

                    {/* glass sheen */}
                    <div className="absolute inset-0 bg-[linear-gradient(200deg,rgba(255,255,255,0.36)_0%,transparent_50%,rgba(255,255,255,0.14)_100%)]" />

                    {form.image_url ? (
                      <motion.div
                        key={form.image_url}
                        initial={{ opacity: 0, x: 24, scale: 0.94 }}
                        animate={{ opacity: 1, x: 0, scale: 1 }}
                        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                        className="absolute bottom-5 right-5 z-10 w-[64%] cursor-pointer overflow-hidden rounded-2xl border border-white/60 shadow-lg shadow-black/6 transition-transform hover:scale-[1.03]"
                      >
                        <div className="absolute -inset-2 rounded-2xl bg-white/25 blur-md" />
                        <img
                          src={form.image_url}
                          alt="announcement illustration"
                          className="relative w-full rounded-2xl object-cover"
                          style={{ aspectRatio: '4/3' }}
                          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                        />
                        <div className="absolute inset-0 rounded-2xl bg-[linear-gradient(35deg,rgba(0,0,0,0.06)_0%,transparent_45%,rgba(255,255,255,0.08)_100%)]" />
                      </motion.div>
                    ) : (
                      /* glass placeholder card when no image */
                      <div className="absolute bottom-5 right-5 left-5 rounded-[24px] border border-white/70 bg-white/72 p-5 shadow-lg backdrop-blur-xl">
                        <div className="mb-2 h-1.5 w-10 rounded-full bg-slate-300/80" />
                        <div className="space-y-2">
                          <div className="h-2.5 w-full rounded-full bg-slate-200/90" />
                          <div className="h-2.5 w-4/5 rounded-full bg-slate-200/80" />
                          <div className="h-2.5 w-3/5 rounded-full bg-slate-200/70" />
                        </div>
                        <div className="mt-4 flex items-center gap-2.5">
                          <div className={cn('flex h-8 w-8 items-center justify-center rounded-xl text-white shadow-md', previewTheme.accentClass)}>
                            <Sparkles size={13} />
                          </div>
                          <div>
                            <p className="text-xs font-black text-slate-800">AgenticOS</p>
                            <p className="text-[10px] font-semibold text-slate-400">Platform Notice</p>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-4 rounded-3xl border border-slate-100 bg-slate-50/80 px-4 py-4 text-xs font-medium leading-6 text-slate-500">
                预览说明：正文将按照所选格式渲染。Markdown 会自动转换为富文本，HTML 将直接渲染。
                真正对用户生效时，会在进入聊天或 Agent Store 后弹出。
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
