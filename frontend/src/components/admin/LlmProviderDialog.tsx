/**
 * AI 提供商：新建 / 编辑弹窗。
 *
 * 两个不能妥协的点：
 * 1. **API Key 永不回显**。编辑时输入框始终为空，占位符说明「留空表示不修改」；
 *    要清空必须显式点「清空 Key」。把「空」当成「不变」会导致泄露的 Key 永远删不掉。
 * 2. **类型决定必填项**。企业网关（Cookie）没有 API Key、模型名可留空，
 *    表单必须跟着切换，否则用户会被要求填一个业务上不存在的字段。
 */
import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
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
import { Switch } from '@/components/shadcn/switch';
import {
  createLlmProvider,
  updateLlmProvider,
  type LlmProvider,
  type ProviderPreset,
  type ProviderType,
  type ProviderTypeOption,
} from '@/services/llmProviderService';
import { toastError } from '../../lib/errors';

interface FormState {
  /** 厂商预设 slug；空串表示不使用预设 */
  preset: string;
  name: string;
  slug: string;
  provider_type: ProviderType;
  base_url: string;
  model: string;
  api_key: string;
  timeout_seconds: string;
  description: string;
  enabled: boolean;
}

const EMPTY: FormState = {
  preset: '',
  name: '',
  slug: '',
  provider_type: 'openai_compatible',
  base_url: '',
  model: '',
  api_key: '',
  timeout_seconds: '300',
  description: '',
  enabled: true,
};

function toForm(provider: LlmProvider | null): FormState {
  if (!provider) return EMPTY;
  return {
    preset: provider.preset ?? '',
    name: provider.name,
    slug: provider.slug,
    provider_type: provider.provider_type,
    base_url: provider.base_url,
    model: provider.model,
    // 刻意留空：后端从不返回 Key，这里也不假装知道
    api_key: '',
    timeout_seconds: String(provider.timeout_seconds ?? 300),
    description: provider.description ?? '',
    enabled: provider.enabled,
  };
}

export function LlmProviderDialog({
  open,
  provider,
  providerTypes,
  presets,
  onClose,
}: {
  open: boolean;
  provider: LlmProvider | null;
  providerTypes: ProviderTypeOption[];
  presets: ProviderPreset[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [clearKey, setClearKey] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(toForm(provider));
      setClearKey(false);
    }
  }, [open, provider]);

  const isEdit = provider !== null;
  const isEnterprise = form.provider_type === 'enterprise_cookie';

  const patch = (next: Partial<FormState>) => setForm((prev) => ({ ...prev, ...next }));

  const selectedPreset = presets.find((item) => item.slug === form.preset) ?? null;

  /**
   * 选中预设就把它知道的都填上（地址、认证方式、模型）。
   *
   * 只在字段为空时填 —— 管理员手动改了一半又切预设时，不该把手输的值冲掉。
   */
  const applyPreset = (slug: string) => {
    const preset = presets.find((item) => item.slug === slug);
    if (!preset) {
      patch({ preset: '' });
      return;
    }
    patch({
      preset: slug,
      name: form.name.trim() ? form.name : preset.label,
      slug: form.slug.trim() ? form.slug : preset.slug.replace(/_/g, '-'),
      provider_type: preset.provider_type,
      base_url: preset.base_url,
      model: preset.model,
    });
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const timeout = Number(form.timeout_seconds);
      if (!Number.isFinite(timeout) || timeout < 1) {
        throw new Error('超时时间必须是大于 0 的整数');
      }
      if (isEdit) {
        const payload: Record<string, unknown> = {
          name: form.name.trim(),
          provider_type: form.provider_type,
          base_url: form.base_url.trim(),
          model: form.model.trim(),
          timeout_seconds: timeout,
          description: form.description.trim(),
          enabled: form.enabled,
        };
        // 三态：清空 > 覆盖 > 不传
        if (clearKey) payload.api_key = '';
        else if (form.api_key.trim()) payload.api_key = form.api_key.trim();
        return updateLlmProvider(provider.id, payload);
      }
      return createLlmProvider({
        // preset 只影响后端如何补全空缺字段；显式值仍然优先
        preset: form.preset || null,
        name: form.name.trim(),
        slug: form.slug.trim(),
        provider_type: form.provider_type,
        base_url: form.base_url.trim(),
        model: form.model.trim(),
        api_key: form.api_key.trim() || undefined,
        timeout_seconds: timeout,
        description: form.description.trim(),
        enabled: form.enabled,
      });
    },
    onSuccess: () => {
      toast.success(isEdit ? '提供商已更新' : '提供商已创建');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'llm-providers'] });
      onClose();
    },
    onError: (err: Error) => toast.error(toastError(err, '保存失败')),
  });

  const disabled =
    saveMutation.isPending ||
    !form.name.trim() ||
    !form.base_url.trim() ||
    (!isEdit && !form.slug.trim()) ||
    (!isEnterprise && !form.model.trim());

  return (
    <Dialog open={open} onOpenChange={(next) => (!next ? onClose() : undefined)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑提供商' : '新建 AI 提供商'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? '修改后立即生效，正在进行的对话会沿用旧连接直到结束。'
              : '提供商是全站共用的：切换默认提供商后，所有智能体都改用它。'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {!isEdit ? (
            <div className="grid gap-1.5">
              <Label>厂商预设</Label>
              <Select
                value={form.preset || '__none__'}
                onValueChange={(value) => applyPreset(value === '__none__' ? '' : value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="手动配置" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">手动配置</SelectItem>
                  {presets.map((item) => (
                    <SelectItem key={item.slug} value={item.slug}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs font-medium text-[var(--muted-foreground)]">
                {selectedPreset
                  ? selectedPreset.notes ||
                    '预设会补全接口地址、认证方式与登录动作，账号密码在创建后再填。'
                  : '选一个预设会自动填好接口地址、认证方式与登录动作；也可以完全手填。'}
              </p>
            </div>
          ) : null}

          <div className="grid gap-1.5">
            <Label htmlFor="provider-name">名称</Label>
            <Input
              id="provider-name"
              value={form.name}
              placeholder="例如：DeepSeek / 企业 AI 网关"
              onChange={(e) => patch({ name: e.target.value })}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="provider-slug">标识（slug）</Label>
            <Input
              id="provider-slug"
              value={form.slug}
              disabled={isEdit}
              placeholder="例如：deepseek"
              onChange={(e) => patch({ slug: e.target.value })}
            />
            <p className="text-xs font-medium text-[var(--muted-foreground)]">
              {isEdit ? '标识创建后不可修改。' : '仅用于内部识别，小写字母、数字与短横线。'}
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label>认证方式</Label>
            <Select
              value={form.provider_type}
              onValueChange={(value) => patch({ provider_type: value as ProviderType })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {providerTypes.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs font-medium text-[var(--muted-foreground)]">
              {isEnterprise
                ? '企业网关靠浏览器登录态认证，需要在保存后单独配置账号密码或粘贴 Cookie。'
                : 'OpenAI 兼容端点，用 API Key 认证。OpenAI / DeepSeek / 通义 / Ollama 都属这一类。'}
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="provider-base-url">接口地址</Label>
            <Input
              id="provider-base-url"
              value={form.base_url}
              placeholder={isEnterprise ? 'https://agents.example.com' : 'https://api.deepseek.com'}
              onChange={(e) => patch({ base_url: e.target.value })}
            />
            <p className="text-xs font-medium text-[var(--muted-foreground)]">
              {isEnterprise ? '填网关根地址，不含 /v1/chat/completions。' : '不含 /v1 也可，系统会按 SDK 约定拼接。'}
            </p>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="provider-model">
              模型{isEnterprise ? '（可留空，由网关决定）' : ''}
            </Label>
            <Input
              id="provider-model"
              value={form.model}
              placeholder={isEnterprise ? '留空则使用网关默认模型' : 'deepseek-chat'}
              onChange={(e) => patch({ model: e.target.value })}
            />
          </div>

          {!isEnterprise ? (
            <div className="grid gap-1.5">
              <Label htmlFor="provider-api-key">API Key</Label>
              <Input
                id="provider-api-key"
                type="password"
                autoComplete="new-password"
                value={form.api_key}
                disabled={clearKey}
                placeholder={
                  isEdit
                    ? provider?.has_api_key
                      ? '已配置，留空表示不修改'
                      : '尚未配置'
                    : 'sk-...'
                }
                onChange={(e) => patch({ api_key: e.target.value })}
              />
              {isEdit && provider?.has_api_key ? (
                <label className="flex items-center gap-2 text-xs font-medium text-[var(--muted-foreground)]">
                  <input
                    type="checkbox"
                    checked={clearKey}
                    onChange={(e) => {
                      setClearKey(e.target.checked);
                      if (e.target.checked) patch({ api_key: '' });
                    }}
                  />
                  清空已保存的 Key（清空后该提供商不可用）
                </label>
              ) : null}
            </div>
          ) : null}

          <div className="grid gap-1.5">
            <Label htmlFor="provider-timeout">请求超时（秒）</Label>
            <Input
              id="provider-timeout"
              type="number"
              min={1}
              max={3600}
              value={form.timeout_seconds}
              onChange={(e) => patch({ timeout_seconds: e.target.value })}
            />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="provider-desc">备注</Label>
            <Input
              id="provider-desc"
              value={form.description}
              placeholder="用途说明，便于其他管理员理解"
              onChange={(e) => patch({ description: e.target.value })}
            />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3.5 py-2.5">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[var(--foreground)]">启用</p>
              <p className="text-xs font-medium text-[var(--muted-foreground)]">
                停用后不会被选为生效提供商，也不会参与 Cookie 续期。
              </p>
            </div>
            <Switch checked={form.enabled} onCheckedChange={(next) => patch({ enabled: next })} />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saveMutation.isPending}>
            取消
          </Button>
          <Button onClick={() => saveMutation.mutate()} disabled={disabled}>
            {saveMutation.isPending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
            {isEdit ? '保存' : '创建'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
