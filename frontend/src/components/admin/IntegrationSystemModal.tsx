/**
 * 集成管理：集成系统编辑弹窗（三步向导）。
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
import { cn } from '@/lib/utils';
import {
  CredentialField,
  IntegrationSystem,
  createSystem,
  updateSystem,
} from '@/services/integrationService';
import { AdvancedAuthPanel } from './IntegrationAdvancedAuthPanel';
import {
  AUTH_TYPES,
  authTypeIcon,
  systemFormSchema,
  type AdvancedAuth,
  type SystemFormValues,
} from './integrationHelpers';

export function SystemModal({
  open,
  editingSystem,
  onClose,
}: {
  open: boolean;
  editingSystem: IntegrationSystem | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [step, setStep] = React.useState(0);
  const [advancedAuth, setAdvancedAuth] = React.useState<AdvancedAuth>({});
  const [defaultCreds, setDefaultCreds] = React.useState<Record<string, string> | null>(null);

  const form = useForm<SystemFormValues>({
    resolver: zodResolver(systemFormSchema),
    defaultValues: {
      name: '',
      base_url: '',
      description: '',
      auth_type: 'api_key',
      published: true,
      oauth_client_id: '',
      oauth_client_secret: '',
      oauth_auth_url: '',
      oauth_token_url: '',
      oauth_refresh_token_url: '',
      oauth_scope: '',
      jwt_login_url: '',
      jwt_refresh_url: '',
      jwt_refresh_body_template: '',
      jwt_refresh_token_path: '',
      jwt_request_body_template: '{}',
      jwt_response_token_path: '',
      jwt_response_expires_path: '',
      jwt_response_token_header: '',
      login_token_source: 'body',
      login_inject_mode: 'bearer',
      login_inject_header_name: '',
      credential_fields: [],
    },
  });
  const credFieldArray = useFieldArray({ control: form.control, name: 'credential_fields' });

  React.useEffect(() => {
    if (open) {
      setStep(0);
      setAdvancedAuth((editingSystem?.advanced_auth as AdvancedAuth) ?? {});
      setDefaultCreds(null);
      form.reset({
        name: editingSystem?.name ?? '',
        base_url: editingSystem?.base_url ?? '',
        description: editingSystem?.description ?? '',
        auth_type: editingSystem?.auth_type ?? 'api_key',
        published: editingSystem?.published ?? true,
        oauth_client_id: '',
        oauth_client_secret: '',
        oauth_auth_url: editingSystem?.oauth_auth_url ?? '',
        oauth_token_url: editingSystem?.oauth_token_url ?? '',
        oauth_refresh_token_url: editingSystem?.oauth_refresh_token_url ?? '',
        oauth_scope: editingSystem?.oauth_scope ?? '',
        jwt_login_url: editingSystem?.jwt_login_url ?? '',
        jwt_refresh_url: editingSystem?.jwt_refresh_url ?? '',
        jwt_refresh_body_template: editingSystem?.jwt_refresh_body_template ?? '',
        jwt_refresh_token_path: editingSystem?.jwt_refresh_token_path ?? '',
        jwt_request_body_template: editingSystem?.jwt_request_body_template ?? '{}',
        jwt_response_token_path: editingSystem?.jwt_response_token_path ?? '',
        jwt_response_expires_path: editingSystem?.jwt_response_expires_path ?? '',
        jwt_response_token_header: editingSystem?.jwt_response_token_header ?? '',
        login_token_source: editingSystem?.login_token_source ?? 'body',
        login_inject_mode: editingSystem?.login_inject_mode ?? 'bearer',
        login_inject_header_name: editingSystem?.login_inject_header_name ?? '',
        credential_fields: editingSystem
          ? Object.values(
              (editingSystem.credential_template as { fields?: CredentialField[] }).fields ?? {},
            ).map((f: CredentialField) => ({
              key: f.key ?? '',
              label: f.label ?? '',
              type: f.type ?? 'text',
              required: f.required ?? false,
              placeholder: f.placeholder ?? '',
            }))
          : [],
      });
    }
  }, [open, editingSystem, form]);

  const authType = form.watch('auth_type');
  const jwtTemplate = form.watch('jwt_request_body_template');
  const loginTokenSource = form.watch('login_token_source');
  const loginInjectMode = form.watch('login_inject_mode');
  const credFields = form.watch('credential_fields');

  const jwtPairs = React.useMemo(() => {
    try {
      const parsed: unknown = JSON.parse(jwtTemplate || '{}');
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return Object.entries(parsed as Record<string, unknown>).map(([k, v]) => ({
          key: k,
          value: String(v),
        }));
      }
      return [];
    } catch {
      return [];
    }
  }, [jwtTemplate]);

  const writeJwtPairs = (pairs: { key: string; value: string }[]) => {
    const obj: Record<string, string> = {};
    for (const p of pairs) obj[p.key] = p.value;
    form.setValue('jwt_request_body_template', JSON.stringify(obj), { shouldDirty: true });
  };

  const saveMutation = useMutation({
    mutationFn: async (values: SystemFormValues) => {
      const credential_template = { fields: values.credential_fields } as unknown as Record<string, CredentialField>;
      const payload = {
        name: values.name.trim(),
        description: values.description,
        base_url: values.base_url.trim(),
        auth_type: values.auth_type,
        credential_template,
        oauth_auth_url: values.oauth_auth_url || undefined,
        oauth_token_url: values.oauth_token_url || undefined,
        oauth_scope: values.oauth_scope || undefined,
        oauth_refresh_token_url: values.oauth_refresh_token_url || undefined,
        jwt_login_url: values.jwt_login_url || undefined,
        jwt_refresh_url: values.jwt_refresh_url || undefined,
        jwt_refresh_body_template: values.jwt_refresh_body_template || undefined,
        jwt_refresh_token_path: values.jwt_refresh_token_path || undefined,
        jwt_request_body_template: values.jwt_request_body_template || undefined,
        jwt_response_token_path: values.jwt_response_token_path || undefined,
        jwt_response_expires_path: values.jwt_response_expires_path || undefined,
        jwt_response_token_header: values.login_inject_header_name || values.jwt_response_token_header || undefined,
        login_token_source: values.login_token_source || undefined,
        login_inject_mode: values.login_inject_mode || undefined,
        login_inject_header_name: values.login_inject_header_name || undefined,
        published: values.published,
        headers: editingSystem?.headers ?? {},
        advanced_auth: advancedAuth,
        default_credential_data: defaultCreds,
      };
      return editingSystem
        ? updateSystem(editingSystem.id, payload)
        : createSystem(payload);
    },
    onSuccess: () => {
      toast.success(editingSystem ? '集成已更新' : '集成已创建');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || '保存失败'),
  });

  const canProceed =
    step === 0
      ? form.watch('name').trim().length > 0 && form.watch('base_url').trim().length > 0
      : step === 1
        ? (authType !== 'oauth2' ||
            !!(form.watch('oauth_auth_url') && form.watch('oauth_token_url'))) &&
          (authType !== 'jwt_login' || !!form.watch('jwt_login_url'))
        : true;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[min(90vh,940px)] w-[min(680px,calc(100vw-32px))] max-w-none flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>{editingSystem ? '编辑集成' : '新增集成'}</DialogTitle>
          <DialogDescription>配置第三方系统连接、鉴权与凭据字段。</DialogDescription>
        </DialogHeader>

        {/* 步骤条 */}
        <div className="flex items-center gap-1 px-1">
          {['基本信息', '鉴权配置', '高级设置'].map((label, i) => (
            <React.Fragment key={label}>
              {i > 0 && <div className={cn('mx-1 h-px flex-1', i <= step ? 'bg-zinc-900' : 'bg-zinc-200')} />}
              <button
                type="button"
                onClick={() => {
                  if (i < step || (i === step + 1 && canProceed)) setStep(i);
                }}
                className={cn(
                  'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all',
                  i === step
                    ? 'bg-zinc-200 text-zinc-800'
                    : i < step
                      ? 'text-zinc-600 hover:bg-zinc-100'
                      : 'text-[var(--muted-foreground)]',
                )}
              >
                <span
                  className={cn(
                    'flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold',
                    i === step
                      ? 'bg-zinc-900 text-white'
                      : i < step
                        ? 'bg-zinc-900 text-white'
                        : 'bg-zinc-200 text-[var(--muted-foreground)]',
                  )}
                >
                  {i < step ? '✓' : i + 1}
                </span>
                {label}
              </button>
            </React.Fragment>
          ))}
        </div>

        <form
          onSubmit={form.handleSubmit((values) => void saveMutation.mutateAsync(values))}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-1 py-2">
            {step === 0 && (
              <>
                <div className="grid grid-cols-1 gap-3.5 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>名称 *</Label>
                    <Input placeholder="如 Jira、GitHub" {...form.register('name')} />
                    {form.formState.errors.name ? (
                      <p className="text-xs font-medium text-rose-600">{form.formState.errors.name.message}</p>
                    ) : null}
                  </div>
                  <div className="space-y-1.5">
                    <Label>Base URL *</Label>
                    <Input
                      placeholder="https://api.example.com"
                      className="font-mono text-sm"
                      {...form.register('base_url')}
                    />
                    {form.formState.errors.base_url ? (
                      <p className="text-xs font-medium text-rose-600">{form.formState.errors.base_url.message}</p>
                    ) : null}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>描述</Label>
                  <textarea
                    rows={2}
                    placeholder="简要描述该系统的用途"
                    {...form.register('description')}
                    className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-2 text-sm text-[var(--foreground)] outline-none transition focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/25"
                  />
                </div>
                <label className="flex items-center gap-2.5 text-sm font-medium text-zinc-700">
                  <Checkbox
                    checked={form.watch('published')}
                    onCheckedChange={(checked) => form.setValue('published', checked === true)}
                  />
                  发布（用户可见）
                </label>
              </>
            )}

            {step === 1 && (
              <>
                <div>
                  <Label className="mb-2 block">鉴权方式</Label>
                  <div className="grid grid-cols-3 gap-2">
                    {AUTH_TYPES.map((t) => {
                      const Icon = authTypeIcon(t.value);
                      return (
                        <button
                          key={t.value}
                          type="button"
                          onClick={() => form.setValue('auth_type', t.value, { shouldDirty: true })}
                          className={cn(
                            'flex flex-col items-center gap-1.5 rounded-lg border-2 px-3 py-3 text-center transition-all',
                            authType === t.value
                              ? 'border-zinc-900 bg-zinc-100 text-zinc-800 shadow-sm'
                              : 'border-[var(--border-subtle)] bg-[var(--surface-1)] text-zinc-600 hover:border-zinc-300',
                          )}
                        >
                          <Icon size={18} className={authType === t.value ? 'text-zinc-600' : 'text-[var(--muted-foreground)]'} />
                          <span className="text-xs font-semibold">{t.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {authType === 'oauth2' && (
                  <div className="space-y-3 rounded-lg border border-zinc-200 bg-zinc-100/50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-zinc-600">OAuth 2.0 配置</p>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label>Client ID</Label>
                        <Input className="font-mono text-sm" {...form.register('oauth_client_id')} />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Client Secret</Label>
                        <Input type="password" className="font-mono text-sm" {...form.register('oauth_client_secret')} />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <Label>授权 URL</Label>
                      <Input className="font-mono text-sm" {...form.register('oauth_auth_url')} />
                    </div>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <Label>Token URL</Label>
                        <Input className="font-mono text-sm" {...form.register('oauth_token_url')} />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Refresh Token URL</Label>
                        <Input className="font-mono text-sm" {...form.register('oauth_refresh_token_url')} />
                      </div>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Scope</Label>
                      <Input placeholder="read write (可选)" {...form.register('oauth_scope')} />
                    </div>
                  </div>
                )}

                {authType === 'jwt_login' && (
                  <>
                    <div className="space-y-3 rounded-lg border border-violet-100 bg-violet-50/50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wider text-violet-500">登录端点</p>
                      <div className="space-y-1.5">
                        <Label>登录地址</Label>
                        <Input className="font-mono text-sm" {...form.register('jwt_login_url')} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="space-y-1.5">
                          <Label>刷新地址</Label>
                          <Input className="font-mono text-xs" {...form.register('jwt_refresh_url')} />
                        </div>
                        <div className="space-y-1.5">
                          <Label>Refresh Token 路径</Label>
                          <Input className="font-mono text-xs" {...form.register('jwt_refresh_token_path')} />
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <Label>刷新请求体模板</Label>
                        <Input
                          className="font-mono text-xs"
                          {...form.register('jwt_refresh_body_template')}
                          placeholder='{"grant_type":"refresh_token","refresh_token":"{refresh_token}"}'
                        />
                      </div>
                    </div>
                    <div className="space-y-3 rounded-lg border border-violet-100 bg-violet-50/50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wider text-violet-500">
                        Token 解析与注入
                      </p>
                      <div>
                        <div className="mb-2 flex items-center justify-between">
                          <Label>请求体字段</Label>
                          <Button
                            type="button"
                            variant="ghost"
                            size="xs"
                            className="gap-1 text-zinc-700"
                            onClick={() => writeJwtPairs([...jwtPairs, { key: '', value: '' }])}
                          >
                            <Plus size={13} />
                            添加字段
                          </Button>
                        </div>
                        {jwtPairs.length === 0 && (
                          <p className="text-xs font-medium text-[var(--muted-foreground)]">暂无字段，点击「添加字段」定义登录请求体</p>
                        )}
                        {jwtPairs.map((p, i) => (
                          <div key={i} className="mb-2 flex items-center gap-2">
                            <Input
                              className="flex-1 font-mono text-sm"
                              placeholder="字段名 (如 username)"
                              value={p.key}
                              onChange={(e) => {
                                const next = [...jwtPairs];
                                next[i] = { ...next[i], key: e.target.value };
                                writeJwtPairs(next);
                              }}
                            />
                            <Input
                              className="flex-1 font-mono text-sm"
                              placeholder="值模板 (如 {username})"
                              value={p.value}
                              onChange={(e) => {
                                const next = [...jwtPairs];
                                next[i] = { ...next[i], value: e.target.value };
                                writeJwtPairs(next);
                              }}
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              className="text-[var(--muted-foreground)] hover:bg-rose-50 hover:text-rose-500"
                              onClick={() => writeJwtPairs(jwtPairs.filter((_, x) => x !== i))}
                            >
                              <Trash2 size={15} />
                            </Button>
                          </div>
                        ))}
                      </div>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label>Token 来源</Label>
                          <Select
                            value={loginTokenSource}
                            onValueChange={(v) => form.setValue('login_token_source', v)}
                          >
                            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="body">响应 Body</SelectItem>
                              <SelectItem value="header">响应 Header</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-1.5">
                          <Label>注入方式</Label>
                          <Select
                            value={loginInjectMode}
                            onValueChange={(v) => form.setValue('login_inject_mode', v)}
                          >
                            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="bearer">Authorization: Bearer</SelectItem>
                              <SelectItem value="header">自定义 Header</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                        <div className="space-y-1.5">
                          <Label>Token Body 路径</Label>
                          <Input className="font-mono text-xs" {...form.register('jwt_response_token_path')} />
                        </div>
                        <div className="space-y-1.5">
                          <Label>过期时间路径</Label>
                          <Input className="font-mono text-xs" {...form.register('jwt_response_expires_path')} />
                        </div>
                        <div className="space-y-1.5">
                          <Label>Header 名称</Label>
                          <Input className="font-mono text-xs" {...form.register('login_inject_header_name')} />
                        </div>
                      </div>
                      <p className="text-xs font-medium text-[var(--muted-foreground)]">
                        Token 来源：从响应 Body（JSON）或 Header 中读取 token。注入方式：以 Bearer Token 或自定义 Header 注入请求。
                      </p>
                    </div>
                  </>
                )}

                {/* 用户凭据 */}
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <Label>用户凭据字段</Label>
                      <p className="mt-0.5 text-xs font-medium text-[var(--muted-foreground)]">
                        定义用户连接此系统时需要填写的凭据信息
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="xs"
                      className="gap-1"
                      onClick={() =>
                        credFieldArray.append({
                          key: '',
                          label: '',
                          type: 'text',
                          required: true,
                          placeholder: '',
                        })
                      }
                    >
                      <Plus size={13} />
                      添加字段
                    </Button>
                  </div>
                  {credFields.length === 0 && (
                    <p className="rounded-lg border border-dashed border-[var(--border-subtle)] p-4 text-center text-xs font-medium text-[var(--muted-foreground)]">
                      暂无凭据字段
                    </p>
                  )}
                  {credFields.map((f, i) => (
                    <div key={f.key || i} className="mb-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3">
                      <div className="grid grid-cols-6 gap-2">
                        <Input
                          className="col-span-2 text-sm"
                          placeholder="字段标识 (key)"
                          {...form.register(`credential_fields.${i}.key` as const)}
                        />
                        <Input
                          className="col-span-2 text-sm"
                          placeholder="显示名称"
                          {...form.register(`credential_fields.${i}.label` as const)}
                        />
                        <Select
                          value={f.type}
                          onValueChange={(v) =>
                            form.setValue(`credential_fields.${i}.type`, v, { shouldDirty: true })
                          }
                        >
                          <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="text">文本</SelectItem>
                            <SelectItem value="password">密码</SelectItem>
                            <SelectItem value="url">URL</SelectItem>
                            <SelectItem value="email">邮箱</SelectItem>
                          </SelectContent>
                        </Select>
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-1 text-xs font-medium text-zinc-600">
                            <Checkbox
                              checked={f.required}
                              onCheckedChange={(checked) =>
                                form.setValue(`credential_fields.${i}.required`, checked === true)
                              }
                            />
                            必填
                          </label>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            className="text-[var(--muted-foreground)] hover:bg-rose-50 hover:text-rose-500"
                            onClick={() => credFieldArray.remove(i)}
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                      </div>
                      <Input
                        className="mt-2 text-xs"
                        placeholder="占位提示文字（可选）"
                        {...form.register(`credential_fields.${i}.placeholder` as const)}
                      />
                    </div>
                  ))}
                </div>

                {/* 默认凭据 */}
                <div className="space-y-3 rounded-lg border border-zinc-200 bg-zinc-100/30 p-4">
                  <p className="text-sm font-semibold text-zinc-700">默认凭据（可选）</p>
                  <p className="text-xs font-medium text-[var(--muted-foreground)]">
                    管理员设置默认凭据后，普通用户无需配置即可直接使用该集成。用户只能看到「已就绪」状态，无法查看具体凭据值。
                  </p>
                  {credFields.length === 0 ? (
                    <p className="text-xs font-medium text-[var(--muted-foreground)]">请先在上方定义凭据字段</p>
                  ) : (
                    credFields.map((f) => (
                      <div key={f.key || f.label} className="space-y-1.5">
                        <Label>{f.label || f.key || '字段'}</Label>
                        <Input
                          type={f.type === 'password' ? 'password' : 'text'}
                          className="font-mono text-sm"
                          placeholder={f.placeholder || `默认 ${f.label || f.key || ''}`}
                          value={(defaultCreds && f.key) ? defaultCreds[f.key] ?? '' : ''}
                          onChange={(e) => {
                            if (!f.key) return;
                            const creds = { ...(defaultCreds ?? {}), [f.key]: e.target.value };
                            const allEmpty = Object.values(creds).every((v) => !v);
                            setDefaultCreds(allEmpty ? null : creds);
                          }}
                        />
                      </div>
                    ))
                  )}
                </div>
              </>
            )}

            {step === 2 && (
              <AdvancedAuthPanel aa={advancedAuth} onChange={setAdvancedAuth} />
            )}
          </div>

          <DialogFooter className="justify-between border-t border-zinc-100 pt-4">
            <div>
              {step > 0 && (
                <Button type="button" variant="outline" onClick={() => setStep(step - 1)}>
                  上一步
                </Button>
              )}
            </div>
            <div className="flex gap-3">
              <Button type="button" variant="ghost" onClick={onClose}>
                取消
              </Button>
              {step < 2 ? (
                <Button
                  type="button"
                  onClick={() => {
                    if (canProceed) setStep(step + 1);
                  }}
                  disabled={!canProceed}
                >
                  下一步
                </Button>
              ) : (
                <Button type="submit" disabled={saveMutation.isPending} className="gap-2">
                  {saveMutation.isPending ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Save size={16} />
                  )}
                  {editingSystem ? '更新' : '创建'}
                </Button>
              )}
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
