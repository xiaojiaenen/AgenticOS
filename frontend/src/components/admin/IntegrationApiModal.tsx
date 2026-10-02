/**
 * 集成管理：接口编辑弹窗。
 * 从 IntegrationManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import * as React from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, Save, Trash2 } from 'lucide-react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import {
  IntegrationApi,
  createApi,
  updateApi,
} from '@/services/integrationService';
import { METHODS, apiFormSchema, type ApiFormValues } from './integrationHelpers';

export function ApiModal({
  open,
  systemId,
  editingApi,
  onClose,
}: {
  open: boolean;
  systemId: number;
  editingApi: IntegrationApi | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const form = useForm<ApiFormValues>({
    resolver: zodResolver(apiFormSchema),
    defaultValues: {
      name: '',
      display_name: '',
      description: '',
      method: 'GET',
      path: '/',
      requires_approval: false,
      timeout_seconds: 30,
      body_wrapper_key: '',
      params: [],
    },
  });
  const paramArray = useFieldArray({ control: form.control, name: 'params' });

  React.useEffect(() => {
    if (open) {
      form.reset({
        name: editingApi?.name ?? '',
        display_name: editingApi?.display_name ?? '',
        description: editingApi?.description ?? '',
        method: (editingApi?.method as ApiFormValues['method']) ?? 'GET',
        path: editingApi?.path ?? '/',
        requires_approval: editingApi?.requires_approval ?? false,
        timeout_seconds: editingApi?.timeout_seconds ?? 30,
        body_wrapper_key: editingApi?.body_wrapper_key ?? '',
        params: editingApi
          ? editingApi.params.map((p) => ({
              name: p.name,
              param_type: p.param_type,
              data_type: p.data_type,
              required: p.required,
              description: p.description,
              default_value: p.default_value,
              param_source: p.param_source ?? 'static',
              label: p.label ?? null,
            }))
          : [],
      });
    }
  }, [open, editingApi, form]);

  const params = form.watch('params');

  const saveMutation = useMutation({
    mutationFn: async (values: ApiFormValues) => {
      const payload = {
        name: values.name.trim(),
        display_name: values.display_name.trim(),
        description: values.description,
        method: values.method,
        path: values.path,
        requires_approval: values.requires_approval,
        timeout_seconds: values.timeout_seconds,
        body_wrapper_key: values.body_wrapper_key || null,
        params: values.params.map((p) => ({
          ...p,
          default_value: p.default_value || null,
          label: p.label || null,
        })),
      };
      return editingApi
        ? updateApi(systemId, editingApi.id, payload)
        : createApi(systemId, payload);
    },
    onSuccess: () => {
      toast.success(editingApi ? '接口已更新' : '接口已创建');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || '保存失败'),
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[min(90vh,940px)] w-[min(680px,calc(100vw-32px))] max-w-none flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>{editingApi ? '编辑接口' : '新增接口'}</DialogTitle>
          <DialogDescription>配置接口请求方式、参数与审批策略。</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => void saveMutation.mutateAsync(values))}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-1 py-2">
            <div className="grid grid-cols-2 gap-3.5">
              <div className="space-y-1.5">
                <Label>接口名称 *</Label>
                <Input className="font-mono text-sm" placeholder="search_issues" {...form.register('name')} />
                {form.formState.errors.name ? (
                  <p className="text-xs font-medium text-rose-600">{form.formState.errors.name.message}</p>
                ) : null}
              </div>
              <div className="space-y-1.5">
                <Label>展示名 *</Label>
                <Input placeholder="搜索工单" {...form.register('display_name')} />
                {form.formState.errors.display_name ? (
                  <p className="text-xs font-medium text-rose-600">{form.formState.errors.display_name.message}</p>
                ) : null}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>描述</Label>
              <textarea
                rows={2}
                placeholder="接口功能描述"
                {...form.register('description')}
                className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm text-[var(--foreground)] outline-none transition focus:border-zinc-900 focus:ring-[3px] focus:ring-indigo-100"
              />
            </div>

            <div className="grid grid-cols-2 gap-3.5">
              <div className="space-y-1.5">
                <Label>方法</Label>
                <Select value={form.watch('method')} onValueChange={(v) => form.setValue('method', v as ApiFormValues['method'])}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {METHODS.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label>路径 *</Label>
                <Input className="font-mono text-sm" placeholder="/rest/api/2/issue/{id}" {...form.register('path')} />
                {form.formState.errors.path ? (
                  <p className="text-xs font-medium text-rose-600">{form.formState.errors.path.message}</p>
                ) : null}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3.5">
              <div className="space-y-1.5">
                <Label>超时 (秒)</Label>
                <Input type="number" {...form.register('timeout_seconds', { valueAsNumber: true })} />
                {form.formState.errors.timeout_seconds ? (
                  <p className="text-xs font-medium text-rose-600">{form.formState.errors.timeout_seconds.message}</p>
                ) : null}
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2.5 text-sm font-medium text-zinc-700">
                  <Checkbox
                    checked={form.watch('requires_approval')}
                    onCheckedChange={(checked) => form.setValue('requires_approval', checked === true)}
                  />
                  需要审批
                </label>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Body 包装键</Label>
              <Input placeholder="留空则不包装" {...form.register('body_wrapper_key')} />
            </div>

            {/* 参数定义 */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-zinc-700">请求参数</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="xs"
                  className="gap-1 text-zinc-700"
                  onClick={() =>
                    paramArray.append({
                      name: '',
                      param_type: 'query',
                      data_type: 'string',
                      required: false,
                      description: '',
                      default_value: null,
                      param_source: 'static',
                      label: null,
                    })
                  }
                >
                  <Plus size={13} />
                  添加
                </Button>
              </div>
              {params.length === 0 && (
                <p className="rounded-lg border border-dashed border-[var(--border-subtle)] p-4 text-center text-xs font-medium text-[var(--muted-foreground)]">
                  暂无参数
                </p>
              )}
              {params.map((p, i) => (
                <div key={p.name || i} className="mb-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3">
                  <div className="grid grid-cols-4 gap-2">
                    <Input placeholder="参数名" {...form.register(`params.${i}.name` as const)} />
                    <Select
                      value={p.param_type}
                      onValueChange={(v) => form.setValue(`params.${i}.param_type`, v)}
                    >
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="path">path</SelectItem>
                        <SelectItem value="query">query</SelectItem>
                        <SelectItem value="body">body</SelectItem>
                      </SelectContent>
                    </Select>
                    <Select
                      value={p.data_type}
                      onValueChange={(v) => form.setValue(`params.${i}.data_type`, v)}
                    >
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="string">string</SelectItem>
                        <SelectItem value="integer">integer</SelectItem>
                        <SelectItem value="boolean">boolean</SelectItem>
                        <SelectItem value="object">object</SelectItem>
                      </SelectContent>
                    </Select>
                    <div className="flex items-center gap-2">
                      <label className="flex items-center gap-1 text-xs font-medium text-zinc-600">
                        <Checkbox
                          checked={p.required}
                          onCheckedChange={(checked) => form.setValue(`params.${i}.required`, checked === true)}
                        />
                        必填
                      </label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-xs"
                        className="text-[var(--muted-foreground)] hover:bg-rose-50 hover:text-rose-500"
                        onClick={() => paramArray.remove(i)}
                      >
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <Select
                      value={p.param_source || 'static'}
                      onValueChange={(v) => form.setValue(`params.${i}.param_source`, v)}
                    >
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="static">固定值</SelectItem>
                        <SelectItem value="user_input">用户输入</SelectItem>
                        <SelectItem value="user_credential">用户凭据（密码框）</SelectItem>
                        <SelectItem value="llm_extract">AI 提取</SelectItem>
                      </SelectContent>
                    </Select>
                    {p.param_source === 'static' ? (
                      <Input
                        className="text-xs"
                        placeholder="固定值（如：GREE）"
                        {...form.register(`params.${i}.default_value` as const)}
                      />
                    ) : (
                      <Input
                        className="text-xs"
                        placeholder="显示标签（如：项目编码）"
                        {...form.register(`params.${i}.label` as const)}
                      />
                    )}
                  </div>
                  <Input className="mt-2 text-xs" placeholder="参数说明" {...form.register(`params.${i}.description` as const)} />
                </div>
              ))}
            </div>
          </div>

          <DialogFooter className="border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={saveMutation.isPending} className="gap-2">
              {saveMutation.isPending ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              更新
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
