/**
 * 公告设计台：公告编辑器表单。
 * 从 AnnouncementManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import type { UseFormReturn } from 'react-hook-form';
import { Sparkles, Trash2 } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Checkbox } from '@/components/shadcn/checkbox';
import { cn } from '@/lib/utils';
import {
  AnnouncementContentFormat,
  AnnouncementTheme,
} from '@/services/announcementService';
import { THEME_DEFS } from '@/components/announcement/announcementTheme';
import { FORMAT_META, type AnnouncementFormValues } from './announcementHelpers';

export function AnnouncementEditor({
  form,
  selectedId,
  isSaving,
  onSubmit,
  onDeleteClick,
}: {
  form: UseFormReturn<AnnouncementFormValues>;
  selectedId: number | null;
  isSaving: boolean;
  onSubmit: (values: AnnouncementFormValues) => void;
  onDeleteClick: () => void;
}) {
  const formValues = form.watch();
  const FormatIcon = FORMAT_META[formValues.content_format].icon;

  return (
    <form
      onSubmit={form.handleSubmit((values) => onSubmit(values))}
      className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-6 shadow-sm"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">编辑器</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-[var(--foreground)]">
            {selectedId === null ? '创建新公告' : '编辑公告'}
          </h2>
          <p className="mt-2 text-sm font-medium leading-7 text-[var(--muted-foreground)]">
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
              onClick={onDeleteClick}
            >
              <Trash2 size={14} />
              删除
            </Button>
          )}
          <Button type="submit" size="sm" disabled={isSaving} className="gap-2">
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
            <div className="flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-0.5">
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
            className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-3 font-mono text-sm text-[var(--foreground)] outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
          />
          <div className="mt-2 flex items-center gap-2 text-xs font-medium text-[var(--muted-foreground)]">
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
        <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">主题风格</p>
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
                  active ? 'border-indigo-300 bg-indigo-50/80 shadow-md' : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:shadow-sm',
                )}
              >
                <div className="h-16 rounded-lg" style={{ background: meta.chipGradient }} />
                <p className="mt-3 text-sm font-semibold text-[var(--foreground)]">{meta.label}</p>
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
        <label className="flex items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-4 text-sm font-medium text-zinc-600">
          <Checkbox
            className="mt-1"
            checked={formValues.is_published}
            onCheckedChange={(checked) => form.setValue('is_published', checked === true)}
          />
          <span>
            <span className="block font-semibold text-[var(--foreground)]">立即发布</span>
            保存后直接进入发布状态，配合时间窗决定是否生效。
          </span>
        </label>
        <label className="flex items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-4 text-sm font-medium text-zinc-600">
          <Checkbox
            className="mt-1"
            checked={formValues.dismissible}
            onCheckedChange={(checked) => form.setValue('dismissible', checked === true)}
          />
          <span>
            <span className="block font-semibold text-[var(--foreground)]">允许轻松关闭</span>
            用户可以点右上角关闭，或点遮罩直接退出。
          </span>
        </label>
        <label className="flex items-start gap-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-4 text-sm font-medium text-zinc-600">
          <Checkbox
            className="mt-1"
            checked={formValues.show_once}
            onCheckedChange={(checked) => form.setValue('show_once', checked === true)}
          />
          <span>
            <span className="block font-semibold text-[var(--foreground)]">只提醒一次</span>
            用户关闭后会记住，等你下次修改公告内容再重新展示。
          </span>
        </label>
      </div>
    </form>
  );
}
