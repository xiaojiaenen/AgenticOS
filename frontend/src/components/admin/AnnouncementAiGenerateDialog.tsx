/**
 * 公告设计台：AI 公告生成弹窗。
 * 从 AnnouncementManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Wand2 } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/shadcn/dialog';
import { cn } from '@/lib/utils';
import {
  AnnouncementContentFormat,
  AnnouncementGenerateRequest,
  AnnouncementTheme,
  generateAnnouncement,
} from '@/services/announcementService';
import { THEME_DEFS } from '@/components/announcement/announcementTheme';
import { FORMAT_META, aiGenerateSchema, type AiGenerateValues } from './announcementHelpers';

export function AiGenerateDialog({
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
              className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5 text-sm text-[var(--foreground)] outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
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
              <div className="flex rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-0.5">
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
                        active ? 'border-indigo-300 bg-indigo-50/80 shadow-sm' : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:shadow-sm',
                      )}
                    >
                      <div className="h-8 rounded-lg" style={{ background: meta.chipGradient }} />
                      <p className="mt-1.5 text-[11px] font-medium text-[var(--foreground)]">{meta.label}</p>
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
