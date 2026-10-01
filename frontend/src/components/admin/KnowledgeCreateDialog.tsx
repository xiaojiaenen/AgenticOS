/**
 * 知识库管理：新建知识库弹窗。
 * 从 KnowledgeManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus } from 'lucide-react';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { createKnowledgeBase } from '@/services/knowledgeService';
import { kbFormSchema, type KBFormValues } from './knowledgeHelpers';

export function CreateKBDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const form = useForm<KBFormValues>({
    resolver: zodResolver(kbFormSchema),
    defaultValues: { name: '', description: '', purpose: '', scope: 'org', visibility: 'public' },
  });

  const createMutation = useMutation({
    mutationFn: (values: KBFormValues) =>
      createKnowledgeBase({
        name: values.name.trim(),
        description: values.description.trim() || undefined,
        purpose: values.purpose.trim() || undefined,
        scope: values.scope,
        visibility: values.visibility,
      }),
    onSuccess: () => {
      toast.success('知识库创建成功');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'kbs'] });
      form.reset();
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || '创建失败'),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>新建知识库</DialogTitle>
          <DialogDescription>创建组织级 / 团队级 / 个人级知识库</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => void createMutation.mutateAsync(values))}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label htmlFor="kb-name">名称 *</Label>
            <Input id="kb-name" placeholder="例如：公司技术文档" {...form.register('name')} />
            {form.formState.errors.name ? (
              <p className="text-xs font-medium text-rose-600">{form.formState.errors.name.message}</p>
            ) : null}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="kb-description">描述</Label>
            <Input id="kb-description" placeholder="简要说明知识库用途" {...form.register('description')} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="kb-purpose">
              目标声明
              <span className="ml-1 text-xs font-normal text-[var(--muted-foreground)]">
                （告诉 LLM 这个知识库关注什么）
              </span>
            </Label>
            <textarea
              id="kb-purpose"
              rows={3}
              placeholder="例如：本知识库包含公司后端服务的部署运维规范，关注 Docker 部署、监控告警、故障排查"
              {...form.register('purpose')}
              className="w-full resize-none rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm text-[var(--foreground)] outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
            />
          </div>

          <div className="flex gap-4">
            <div className="flex-1 space-y-1.5">
              <Label>归属</Label>
              <Select
                value={form.watch('scope')}
                onValueChange={(v) => form.setValue('scope', v as KBFormValues['scope'])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="org">组织级</SelectItem>
                  <SelectItem value="team">团队级</SelectItem>
                  <SelectItem value="personal">个人级</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 space-y-1.5">
              <Label>可见性</Label>
              <Select
                value={form.watch('visibility')}
                onValueChange={(v) => form.setValue('visibility', v as KBFormValues['visibility'])}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="public">公开</SelectItem>
                  <SelectItem value="restricted">受限</SelectItem>
                  <SelectItem value="private">私有</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={createMutation.isPending}>
              取消
            </Button>
            <Button type="submit" disabled={createMutation.isPending} className="gap-2">
              {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              {createMutation.isPending ? '创建中…' : '创建'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
