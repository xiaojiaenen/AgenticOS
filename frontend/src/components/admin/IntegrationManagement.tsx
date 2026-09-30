/**
 * 集成管理：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Select/Dialog/AlertDialog/Checkbox。
 * 功能：第三方系统 CRUD、接口 CRUD、API 测试、OpenAPI 导入。
 * 后端 API 不变（services/integrationService.ts）。
 */
import * as React from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  AlertCircle,
  ChevronLeft,
  ExternalLink,
  Globe,
  Key,
  Loader2,
  Pencil,
  Plug,
  Plus,
  Save,
  Shield,
  TestTube,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, StatusPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Checkbox } from '@/components/shadcn/checkbox';
import { Skeleton } from '@/components/shadcn/skeleton';
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
  IntegrationApi,
  IntegrationApiParam,
  IntegrationSystem,
  IntegrationTestResult,
  createApi,
  createSystem,
  deleteApi,
  deleteSystem,
  listApis,
  listCategories,
  listSystems,
  previewOpenApiImport,
  confirmOpenApiImport,
  testApi,
  updateApi,
  updateSystem,
  type OpenApiPreview,
} from '@/services/integrationService';

const AUTH_TYPES = [
  { value: 'api_key', label: 'API Key' },
  { value: 'bearer', label: 'Bearer Token' },
  { value: 'basic', label: 'Basic Auth' },
  { value: 'oauth2', label: 'OAuth 2.0' },
  { value: 'custom', label: '自定义' },
  { value: 'jwt_login', label: 'JWT 登录' },
];
const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH'] as const;

/** 高级安全配置结构：按 section（sign / request_encrypt / response_decrypt / common）分组的字符串键值 */
type AdvancedAuth = Record<string, Record<string, string>>;

function authTypeLabel(t: string): string {
  return AUTH_TYPES.find((a) => a.value === t)?.label || t;
}

function authTypeIcon(t: string): React.ComponentType<{ size?: number; className?: string }> {
  switch (t) {
    case 'api_key':
      return Key;
    case 'bearer':
    case 'oauth2':
      return Shield;
    default:
      return Globe;
  }
}

function methodBadgeColor(m: string): string {
  switch (m) {
    case 'GET':
      return 'bg-emerald-100 text-emerald-700';
    case 'POST':
      return 'bg-indigo-100 text-indigo-700';
    case 'PUT':
      return 'bg-amber-100 text-amber-700';
    case 'DELETE':
      return 'bg-rose-100 text-rose-700';
    case 'PATCH':
      return 'bg-violet-100 text-violet-700';
    default:
      return 'bg-zinc-100 text-zinc-700';
  }
}

// ---------------------------------------------------------------------------
// zod schema
// ---------------------------------------------------------------------------

const credentialFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.string(),
  required: z.boolean(),
  placeholder: z.string(),
});

const systemFormSchema = z.object({
  name: z.string().min(1, '请填写名称'),
  base_url: z.string().min(1, '请填写 Base URL'),
  description: z.string(),
  auth_type: z.string().min(1),
  published: z.boolean(),
  oauth_client_id: z.string(),
  oauth_client_secret: z.string(),
  oauth_auth_url: z.string(),
  oauth_token_url: z.string(),
  oauth_refresh_token_url: z.string(),
  oauth_scope: z.string(),
  jwt_login_url: z.string(),
  jwt_refresh_url: z.string(),
  jwt_refresh_body_template: z.string(),
  jwt_refresh_token_path: z.string(),
  jwt_request_body_template: z.string(),
  jwt_response_token_path: z.string(),
  jwt_response_expires_path: z.string(),
  jwt_response_token_header: z.string(),
  login_token_source: z.string(),
  login_inject_mode: z.string(),
  login_inject_header_name: z.string(),
  credential_fields: z.array(credentialFieldSchema),
});

type SystemFormValues = z.infer<typeof systemFormSchema>;

const apiFormSchema = z.object({
  name: z.string().min(1, '请填写接口名称'),
  display_name: z.string().min(1, '请填写展示名'),
  description: z.string(),
  method: z.enum(METHODS),
  path: z.string().min(1, '请填写路径'),
  requires_approval: z.boolean(),
  timeout_seconds: z
    .number({ error: '请输入数字' })
    .int('必须为整数')
    .min(1, '至少 1 秒'),
  body_wrapper_key: z.string(),
  params: z.array(
    z.object({
      name: z.string(),
      param_type: z.string(),
      data_type: z.string(),
      required: z.boolean(),
      description: z.string(),
      default_value: z.string().nullable(),
      param_source: z.string(),
      label: z.string().nullable(),
    }),
  ),
});

type ApiFormValues = z.infer<typeof apiFormSchema>;

// ---------------------------------------------------------------------------
// 集成系统编辑弹窗（三步向导）
// ---------------------------------------------------------------------------

function SystemModal({
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
              {i > 0 && <div className={cn('mx-1 h-px flex-1', i <= step ? 'bg-indigo-300' : 'bg-zinc-200')} />}
              <button
                type="button"
                onClick={() => {
                  if (i < step || (i === step + 1 && canProceed)) setStep(i);
                }}
                className={cn(
                  'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-all',
                  i === step
                    ? 'bg-indigo-100 text-indigo-700'
                    : i < step
                      ? 'text-indigo-500 hover:bg-indigo-50'
                      : 'text-zinc-400',
                )}
              >
                <span
                  className={cn(
                    'flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold',
                    i === step
                      ? 'bg-indigo-600 text-white'
                      : i < step
                        ? 'bg-indigo-200 text-indigo-700'
                        : 'bg-zinc-200 text-zinc-400',
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
                    className="w-full resize-y rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
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
                              ? 'border-indigo-400 bg-indigo-50 text-indigo-700 shadow-sm'
                              : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300',
                          )}
                        >
                          <Icon size={18} className={authType === t.value ? 'text-indigo-500' : 'text-zinc-400'} />
                          <span className="text-xs font-semibold">{t.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {authType === 'oauth2' && (
                  <div className="space-y-3 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-indigo-500">OAuth 2.0 配置</p>
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
                            className="gap-1 text-indigo-600"
                            onClick={() => writeJwtPairs([...jwtPairs, { key: '', value: '' }])}
                          >
                            <Plus size={13} />
                            添加字段
                          </Button>
                        </div>
                        {jwtPairs.length === 0 && (
                          <p className="text-xs font-medium text-zinc-400">暂无字段，点击「添加字段」定义登录请求体</p>
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
                              className="text-zinc-400 hover:bg-rose-50 hover:text-rose-500"
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
                      <p className="text-xs font-medium text-zinc-400">
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
                      <p className="mt-0.5 text-xs font-medium text-zinc-400">
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
                    <p className="rounded-lg border border-dashed border-zinc-200 p-4 text-center text-xs font-medium text-zinc-400">
                      暂无凭据字段
                    </p>
                  )}
                  {credFields.map((f, i) => (
                    <div key={f.key || i} className="mb-2 rounded-lg border border-zinc-200 bg-white p-3">
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
                            className="text-zinc-400 hover:bg-rose-50 hover:text-rose-500"
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
                <div className="space-y-3 rounded-lg border border-indigo-100 bg-indigo-50/30 p-4">
                  <p className="text-sm font-semibold text-zinc-700">默认凭据（可选）</p>
                  <p className="text-xs font-medium text-zinc-500">
                    管理员设置默认凭据后，普通用户无需配置即可直接使用该集成。用户只能看到「已就绪」状态，无法查看具体凭据值。
                  </p>
                  {credFields.length === 0 ? (
                    <p className="text-xs font-medium text-zinc-400">请先在上方定义凭据字段</p>
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

// ---------------------------------------------------------------------------
// 高级安全设置面板（签名 / 加密 / 解密）
// ---------------------------------------------------------------------------

const SIGN_ALGOS = [
  { v: 'none', l: '无' },
  { v: 'hmac_sha256', l: 'HMAC-SHA256' },
  { v: 'hmac_sha512', l: 'HMAC-SHA512' },
  { v: 'hmac_md5', l: 'HMAC-MD5' },
  { v: 'sha256_with_rsa', l: 'SHA256WithRSA' },
  { v: 'sha1_with_rsa', l: 'SHA1WithRSA' },
  { v: 'md5_with_rsa', l: 'MD5WithRSA' },
];
const AES_ALGOS = [
  { v: 'none', l: '无' },
  { v: 'aes_128_cbc', l: 'AES-128-CBC' },
  { v: 'aes_256_cbc', l: 'AES-256-CBC' },
  { v: 'aes_256_gcm', l: 'AES-256-GCM' },
  { v: 'aes_ecb', l: 'AES-ECB' },
];

function AdvancedAuthPanel({
  aa,
  onChange,
}: {
  aa: AdvancedAuth;
  onChange: (v: AdvancedAuth) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const sign = aa.sign ?? {};
  const enc = aa.request_encrypt ?? {};
  const dec = aa.response_decrypt ?? {};
  const common = aa.common ?? {};
  const set = (section: string, key: string, val: string) =>
    onChange({ ...aa, [section]: { ...(aa[section] ?? {}), [key]: val } });
  const hasSign = sign.algorithm !== undefined && sign.algorithm !== 'none' && sign.algorithm !== '';
  const hasEnc = enc.algorithm !== undefined && enc.algorithm !== 'none' && enc.algorithm !== '';
  const hasDec = dec.algorithm !== undefined && dec.algorithm !== 'none' && dec.algorithm !== '';

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition hover:bg-zinc-50"
      >
        <span className="text-sm font-semibold text-zinc-700">签名 / 加密 / 解密</span>
        <span className="text-xs font-medium text-zinc-400">
          {open ? '收起' : '展开'}
          {hasSign || hasEnc || hasDec ? ' · 已配置' : ''}
        </span>
      </button>
      {open && (
        <div className="space-y-5 border-t border-zinc-100 px-4 py-4">
          <div className="space-y-3 rounded-lg border border-amber-100 bg-amber-50/40 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-amber-600">请求签名</p>
            <div className="space-y-1.5">
              <Label>签名算法</Label>
              <Select value={sign.algorithm || 'none'} onValueChange={(v) => set('sign', 'algorithm', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SIGN_ALGOS.map((a) => (
                    <SelectItem key={a.v} value={a.v}>{a.l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasSign && (
              <>
                <div className="space-y-1.5">
                  <Label>{sign.algorithm?.startsWith('rsa') ? 'RSA 私钥 (PEM)' : '签名密钥'}</Label>
                  <textarea
                    rows={2}
                    className="w-full resize-y rounded-md border border-zinc-200 bg-white px-3 py-2 font-mono text-xs text-zinc-900 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
                    value={sign.secret || ''}
                    onChange={(e) => set('sign', 'secret', e.target.value)}
                    placeholder={sign.algorithm?.startsWith('rsa') ? '-----BEGIN PRIVATE KEY-----\n...' : '输入密钥'}
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>签名位置</Label>
                    <Select value={sign.placement || 'header'} onValueChange={(v) => set('sign', 'placement', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="header">Header</SelectItem>
                        <SelectItem value="query">Query Param</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>字段名</Label>
                    <Input value={sign.field_name || ''} onChange={(e) => set('sign', 'field_name', e.target.value)} placeholder="X-Signature" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label>签名内容模板</Label>
                  <Input
                    className="font-mono text-xs"
                    value={sign.content_template || ''}
                    onChange={(e) => set('sign', 'content_template', e.target.value)}
                    placeholder="{timestamp}{nonce}{body}"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>编码</Label>
                  <Select value={sign.encoding || 'base64'} onValueChange={(v) => set('sign', 'encoding', v)}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="base64">Base64</SelectItem>
                      <SelectItem value="hex">Hex</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}
          </div>

          <div className="space-y-3 rounded-lg border border-indigo-100 bg-indigo-50/40 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-indigo-600">请求加密</p>
            <div className="space-y-1.5">
              <Label>加密算法</Label>
              <Select value={enc.algorithm || 'none'} onValueChange={(v) => set('request_encrypt', 'algorithm', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AES_ALGOS.map((a) => (
                    <SelectItem key={a.v} value={a.v}>{a.l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasEnc && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>密钥</Label>
                    <Input type="password" className="font-mono text-xs" value={enc.key || ''} onChange={(e) => set('request_encrypt', 'key', e.target.value)} placeholder="16/24/32 字节" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>IV</Label>
                    <Input type="password" className="font-mono text-xs" value={enc.iv || ''} onChange={(e) => set('request_encrypt', 'iv', e.target.value)} placeholder="16 字节 (ECB 留空)" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>加密范围</Label>
                    <Select value={enc.scope || 'body'} onValueChange={(v) => set('request_encrypt', 'scope', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="body">整个 Body</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>编码</Label>
                    <Select value={enc.encoding || 'base64'} onValueChange={(v) => set('request_encrypt', 'encoding', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="base64">Base64</SelectItem>
                        <SelectItem value="hex">Hex</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </>
            )}
          </div>

          <div className="space-y-3 rounded-lg border border-emerald-100 bg-emerald-50/40 p-3.5">
            <p className="text-xs font-semibold uppercase tracking-wider text-emerald-600">响应解密</p>
            <div className="space-y-1.5">
              <Label>解密算法</Label>
              <Select value={dec.algorithm || 'none'} onValueChange={(v) => set('response_decrypt', 'algorithm', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AES_ALGOS.map((a) => (
                    <SelectItem key={a.v} value={a.v}>{a.l}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {hasDec && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>密钥</Label>
                    <Input type="password" className="font-mono text-xs" value={dec.key || enc.key || ''} onChange={(e) => set('response_decrypt', 'key', e.target.value)} placeholder="复用请求加密密钥" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>IV</Label>
                    <Input type="password" className="font-mono text-xs" value={dec.iv || enc.iv || ''} onChange={(e) => set('response_decrypt', 'iv', e.target.value)} placeholder="复用请求加密 IV" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label>密文路径</Label>
                    <Input className="font-mono text-xs" value={dec.path || ''} onChange={(e) => set('response_decrypt', 'path', e.target.value)} placeholder="data.encrypted" />
                  </div>
                  <div className="space-y-1.5">
                    <Label>编码</Label>
                    <Select value={dec.encoding || 'base64'} onValueChange={(v) => set('response_decrypt', 'encoding', v)}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="base64">Base64</SelectItem>
                        <SelectItem value="hex">Hex</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </>
            )}
          </div>

          {(hasSign || hasEnc) && (
            <div className="space-y-3 rounded-lg border border-zinc-200 bg-zinc-50/40 p-3.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">公共参数</p>
              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <Label>时间戳字段名</Label>
                  <Input value={common.timestamp_field || ''} onChange={(e) => set('common', 'timestamp_field', e.target.value)} placeholder="timestamp" />
                </div>
                <div className="space-y-1.5">
                  <Label>时间戳格式</Label>
                  <Select value={common.timestamp_format || 'unix'} onValueChange={(v) => set('common', 'timestamp_format', v)}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="unix">Unix 时间戳</SelectItem>
                      <SelectItem value="iso8601">ISO 8601</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>随机数字段名</Label>
                  <Input value={common.nonce_field || ''} onChange={(e) => set('common', 'nonce_field', e.target.value)} placeholder="nonce" />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 接口编辑弹窗
// ---------------------------------------------------------------------------

function ApiModal({
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
                className="w-full resize-y rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
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
                  className="gap-1 text-indigo-600"
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
                <p className="rounded-lg border border-dashed border-zinc-200 p-4 text-center text-xs font-medium text-zinc-400">
                  暂无参数
                </p>
              )}
              {params.map((p, i) => (
                <div key={p.name || i} className="mb-2 rounded-lg border border-zinc-200 bg-white p-3">
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
                        className="text-zinc-400 hover:bg-rose-50 hover:text-rose-500"
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

// ---------------------------------------------------------------------------
// 测试抽屉
// ---------------------------------------------------------------------------

type TestState = {
  apiId: number;
  params: Record<string, string>;
  result: IntegrationTestResult | null;
  loading: boolean;
};

function TestDrawer({
  state,
  api,
  onClose,
  onParamChange,
  onRun,
}: {
  state: TestState;
  api: IntegrationApi | undefined;
  onClose: () => void;
  onParamChange: (name: string, value: string) => void;
  onRun: () => void;
}) {
  if (!api) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onMouseDown={onClose}>
      <div
        className="h-full w-full max-w-md overflow-y-auto border-l border-zinc-200/80 bg-white p-6 shadow-lg"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold text-zinc-900">测试: {api.display_name}</h3>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X size={18} />
          </Button>
        </div>
        <div className="mt-5 space-y-3">
          {api.params.map((p) => (
            <div key={p.name} className="space-y-1.5">
              <Label>
                {p.name} {p.required && <span className="text-rose-500">*</span>}
              </Label>
              <Input
                className="text-sm"
                value={state.params[p.name] ?? ''}
                onChange={(e) => onParamChange(p.name, e.target.value)}
                placeholder={p.description || p.name}
              />
            </div>
          ))}
          <Button onClick={onRun} disabled={state.loading} className="w-full gap-2">
            {state.loading ? <Loader2 size={16} className="animate-spin" /> : <TestTube size={16} />}
            发送请求
          </Button>
        </div>
        {state.result && (
          <div className="mt-5">
            <div
              className={cn(
                'rounded-lg border p-4',
                state.result.success ? 'border-emerald-200 bg-emerald-50' : 'border-rose-200 bg-rose-50',
              )}
            >
              <div className="flex items-center justify-between">
                <span
                  className={cn(
                    'text-sm font-semibold',
                    state.result.success ? 'text-emerald-700' : 'text-rose-700',
                  )}
                >
                  {state.result.success ? '成功' : '失败'}
                  {state.result.status_code > 0 ? ` (${state.result.status_code})` : ''}
                </span>
                <span className="text-xs font-medium text-zinc-500">{state.result.elapsed_ms}ms</span>
              </div>
              <pre className="mt-3 max-h-[300px] overflow-auto rounded-lg bg-zinc-900 p-3 text-xs text-zinc-100">
                {state.result.body}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

export const IntegrationManagement = () => {
  const queryClient = useQueryClient();

  const [selectedSystem, setSelectedSystem] = React.useState<IntegrationSystem | null>(null);
  const [systemModalOpen, setSystemModalOpen] = React.useState(false);
  const [editingSystem, setEditingSystem] = React.useState<IntegrationSystem | null>(null);
  const [apiModalOpen, setApiModalOpen] = React.useState(false);
  const [editingApi, setEditingApi] = React.useState<IntegrationApi | null>(null);
  const [deletingSystem, setDeletingSystem] = React.useState<IntegrationSystem | null>(null);
  const [deletingApi, setDeletingApi] = React.useState<IntegrationApi | null>(null);
  const [testState, setTestState] = React.useState<TestState | null>(null);
  const [openApiModal, setOpenApiModal] = React.useState(false);
  const [openApiInput, setOpenApiInput] = React.useState('');
  const [openApiPreview, setOpenApiPreview] = React.useState<OpenApiPreview | null>(null);
  const [activeCategory, setActiveCategory] = React.useState<string>('all');

  const systemsQuery = useQuery({
    queryKey: ['admin', 'integrations'],
    queryFn: listSystems,
  });
  const systems = systemsQuery.data?.items ?? [];

  const categoriesQuery = useQuery({
    queryKey: ['admin', 'integration-categories'],
    queryFn: listCategories,
    retry: 0,
  });
  const categories = categoriesQuery.data?.items ?? [];

  const apisQuery = useQuery({
    queryKey: ['admin', 'integrations', selectedSystem?.id, 'apis'],
    queryFn: () => listApis(selectedSystem!.id),
    enabled: selectedSystem !== null,
  });
  const apis = apisQuery.data?.items ?? [];

  const saveSystemMutation = useMutation({
    mutationFn: (payload: { system: IntegrationSystem }) => deleteSystem(payload.system.id),
    onSuccess: () => {
      toast.success('集成已删除');
      setDeletingSystem(null);
      if (selectedSystem) {
        setSelectedSystem(null);
      }
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const deleteApiMutation = useMutation({
    mutationFn: (api: IntegrationApi) => {
      if (!selectedSystem) throw new Error('未指定集成');
      return deleteApi(selectedSystem.id, api.id);
    },
    onSuccess: () => {
      toast.success('接口已删除');
      setDeletingApi(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const testMutation = useMutation({
    mutationFn: (api: IntegrationApi) => {
      if (!selectedSystem) throw new Error('未指定集成');
      const params: Record<string, string> = {};
      api.params.forEach((p: IntegrationApiParam) => {
        params[p.name] = p.default_value || '';
      });
      setTestState({ apiId: api.id, params, result: null, loading: true });
      return testApi(selectedSystem.id, api.id, params);
    },
    onSuccess: (result) => {
      setTestState((prev) => (prev ? { ...prev, result, loading: false } : null));
    },
    onError: (err: Error) => {
      setTestState((prev) =>
        prev
          ? {
              ...prev,
              result: { success: false, status_code: 0, body: err.message, elapsed_ms: 0 },
              loading: false,
            }
          : null,
      );
    },
  });

  const previewMutation = useMutation({
    mutationFn: (input: string) => {
      const isUrl = input.trim().startsWith('http');
      return previewOpenApiImport(isUrl ? undefined : input.trim(), isUrl ? input.trim() : undefined);
    },
    onSuccess: (preview) => setOpenApiPreview(preview),
    onError: (err: Error) => toast.error(err.message || '解析失败'),
  });

  const confirmImportMutation = useMutation({
    mutationFn: (preview: OpenApiPreview) => confirmOpenApiImport(preview),
    onSuccess: () => {
      toast.success('导入成功');
      setOpenApiModal(false);
      setOpenApiPreview(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'integrations'] });
    },
    onError: (err: Error) => toast.error(err.message || '导入失败'),
  });

  const enabledCount = systems.filter((s) => s.enabled).length;
  const filteredSystems =
    activeCategory === 'all'
      ? systems
      : systems.filter((s) => s.category === activeCategory);

  // ── 系统列表表格 ──
  const systemColumns = React.useMemo<ColumnDef<IntegrationSystem, unknown>[]>(
    () => [
      {
        id: 'name',
        header: '名称',
        cell: ({ row }) => {
          const sys = row.original;
          const Icon = authTypeIcon(sys.auth_type);
          return (
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-zinc-200/80 bg-white text-zinc-600 shadow-sm">
                <Icon size={18} />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-zinc-900">{sys.name}</p>
                <p className="truncate text-xs font-medium text-zinc-400">{sys.base_url}</p>
              </div>
            </div>
          );
        },
      },
      {
        id: 'description',
        header: '描述',
        enableSorting: false,
        cell: ({ row }) => (
          <span className="block max-w-[220px] truncate text-sm font-medium text-zinc-600">
            {row.original.description || '-'}
          </span>
        ),
      },
      {
        id: 'category',
        header: '分类',
        enableSorting: false,
        cell: ({ row }) => {
          const cat = categories.find((c) => c.key === row.original.category);
          return (
            <span className="rounded-lg bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600">
              {cat ? `${cat.icon} ${cat.label}` : row.original.category}
            </span>
          );
        },
      },
      {
        id: 'auth',
        header: '鉴权',
        enableSorting: false,
        cell: ({ row }) => (
          <span className="rounded-lg bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600">
            {authTypeLabel(row.original.auth_type)}
          </span>
        ),
      },
      {
        accessorKey: 'api_count',
        header: () => <span className="block text-center">接口</span>,
        cell: ({ getValue }) => (
          <span className="block text-center text-sm font-medium text-zinc-700">{Number(getValue())}</span>
        ),
      },
      {
        id: 'status',
        header: () => <span className="block text-center">状态</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const sys = row.original;
          const label = sys.enabled && sys.published ? '已发布' : sys.enabled ? '未发布' : '已禁用';
          return (
            <span className="block text-center">
              <StatusPill tone={sys.enabled && sys.published ? 'active' : sys.enabled ? 'warning' : 'inactive'}>
                {label}
              </StatusPill>
            </span>
          );
        },
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const sys = row.original;
          return (
            <div className="flex justify-end gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setSelectedSystem(sys);
                }}
                aria-label={`查看 ${sys.name}`}
                title="查看接口"
              >
                <ExternalLink size={15} />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setEditingSystem(sys);
                  setSystemModalOpen(true);
                }}
                aria-label={`编辑 ${sys.name}`}
              >
                <Pencil size={15} />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-rose-500 hover:bg-rose-50"
                onClick={(e) => {
                  e.stopPropagation();
                  setDeletingSystem(sys);
                }}
                aria-label={`删除 ${sys.name}`}
              >
                <Trash2 size={15} />
              </Button>
            </div>
          );
        },
      },
    ],
    [categories],
  );

  // ── 接口列表表格 ──
  const apiColumns = React.useMemo<ColumnDef<IntegrationApi, unknown>[]>(
    () => [
      {
        id: 'api',
        header: '接口',
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-zinc-900">{row.original.display_name}</p>
            <p className="truncate text-xs font-medium text-zinc-400">{row.original.name}</p>
          </div>
        ),
      },
      {
        accessorKey: 'method',
        header: '方法',
        cell: ({ getValue }) => (
          <span className={cn('rounded-lg px-2 py-1 text-xs font-semibold', methodBadgeColor(String(getValue())))}>
            {String(getValue())}
          </span>
        ),
      },
      {
        accessorKey: 'path',
        header: '路径',
        cell: ({ getValue }) => (
          <span className="block max-w-[240px] truncate font-mono text-xs text-zinc-600">
            {String(getValue())}
          </span>
        ),
      },
      {
        id: 'params',
        header: () => <span className="block text-center">参数</span>,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="block text-center text-sm font-medium text-zinc-700">
            {row.original.params.length}
          </span>
        ),
      },
      {
        id: 'approval',
        header: () => <span className="block text-center">审批</span>,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.requires_approval ? (
            <span className="block text-center">
              <StatusPill tone="warning">需审批</StatusPill>
            </span>
          ) : (
            <span className="block text-center text-xs text-zinc-400">—</span>
          ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const api = row.original;
          return (
            <div className="flex justify-end gap-1">
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => testMutation.mutate(api)}
                title="测试"
              >
                <TestTube size={15} />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => {
                  setEditingApi(api);
                  setApiModalOpen(true);
                }}
              >
                <Pencil size={15} />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                className="text-rose-500 hover:bg-rose-50"
                onClick={() => setDeletingApi(api)}
              >
                <Trash2 size={15} />
              </Button>
            </div>
          );
        },
      },
    ],
    [testMutation],
  );

  if (!selectedSystem) {
    return (
      <div className="space-y-5">
        <AdminPageHeader
          kicker="集成管理"
          title="第三方集成"
          description={`${enabledCount} 个已启用 / ${systems.length} 个总计`}
          actions={
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setOpenApiModal(true);
                  setOpenApiInput('');
                  setOpenApiPreview(null);
                }}
              >
                <Upload size={14} />
                导入 OpenAPI
              </Button>
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setEditingSystem(null);
                  setSystemModalOpen(true);
                }}
              >
                <Plus size={14} />
                新增集成
              </Button>
            </>
          }
        />

        {systemsQuery.isError ? (
          <ErrorBanner message={(systemsQuery.error as Error).message || '加载失败'} />
        ) : null}

        {/* 分类 Tab */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant={activeCategory === 'all' ? 'default' : 'secondary'}
            size="xs"
            onClick={() => setActiveCategory('all')}
          >
            全部 ({systems.length})
          </Button>
          {categories
            .filter((c) => systems.some((s) => s.category === c.key))
            .map((c) => (
              <Button
                key={c.key}
                variant={activeCategory === c.key ? 'default' : 'secondary'}
                size="xs"
                onClick={() => setActiveCategory(c.key)}
              >
                {c.icon} {c.label} ({systems.filter((s) => s.category === c.key).length})
              </Button>
            ))}
        </div>

        <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
          {systemsQuery.isLoading ? (
            <div className="space-y-3 p-5">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <DataTable
              columns={systemColumns}
              data={filteredSystems}
              emptyState={
                <div className="flex flex-col items-center justify-center py-8">
                  <Plug size={32} className="mb-3 text-zinc-300" />
                  <p className="text-sm font-semibold text-zinc-600">暂无集成</p>
                  <p className="mt-1 text-xs font-medium text-zinc-400">
                    点击「新增集成」创建第一个第三方系统连接
                  </p>
                </div>
              }
            />
          )}
        </section>

        {/* OpenAPI 导入弹窗 */}
        <Dialog open={openApiModal} onOpenChange={setOpenApiModal}>
          <DialogContent className="sm:max-w-2xl">
            <DialogHeader>
              <DialogTitle>从 OpenAPI 导入</DialogTitle>
              <DialogDescription>粘贴 OpenAPI JSON 内容或输入 URL</DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <textarea
                className="min-h-[120px] w-full resize-y rounded-md border border-zinc-200 bg-white px-3 py-2 font-mono text-xs text-zinc-900 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
                value={openApiInput}
                onChange={(e) => setOpenApiInput(e.target.value)}
                placeholder="粘贴 OpenAPI JSON 内容或输入 URL..."
              />
              <Button
                className="w-full gap-2"
                onClick={() => previewMutation.mutate(openApiInput)}
                disabled={previewMutation.isPending || !openApiInput.trim()}
              >
                {previewMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Upload size={16} />
                )}
                解析预览
              </Button>

              {openApiPreview && (
                <div className="space-y-2 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4">
                  <p className="font-semibold text-zinc-900">{openApiPreview.system_name}</p>
                  <p className="text-sm font-medium text-zinc-500">{openApiPreview.system_description}</p>
                  <div className="flex flex-wrap items-center gap-4 text-xs font-medium text-zinc-600">
                    <span>
                      Base URL: <span className="font-mono">{openApiPreview.base_url}</span>
                    </span>
                    <span>鉴权: {openApiPreview.auth_type}</span>
                  </div>
                  <p className="text-sm font-semibold text-zinc-700">
                    {openApiPreview.apis.length} 个接口将被导入:
                  </p>
                  <div className="max-h-[200px] space-y-1 overflow-y-auto">
                    {openApiPreview.apis.map((a, i) => (
                      <div key={i} className="flex items-center gap-2 text-xs">
                        <span className={cn('rounded-lg px-1.5 py-0.5 font-semibold', methodBadgeColor(a.method))}>
                          {a.method}
                        </span>
                        <span className="font-mono text-zinc-600">{a.path}</span>
                        <span className="text-zinc-400">{a.display_name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setOpenApiModal(false)}>
                取消
              </Button>
              <Button
                onClick={() => openApiPreview && confirmImportMutation.mutate(openApiPreview)}
                disabled={confirmImportMutation.isPending || !openApiPreview}
                className="gap-2"
              >
                {confirmImportMutation.isPending ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Save size={16} />
                )}
                确认导入
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <SystemModal
          open={systemModalOpen}
          editingSystem={editingSystem}
          onClose={() => {
            setSystemModalOpen(false);
            setEditingSystem(null);
          }}
        />

        <AlertDialog
          open={deletingSystem !== null}
          onOpenChange={(next) => !next && setDeletingSystem(null)}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>删除集成</AlertDialogTitle>
              <AlertDialogDescription>
                确定删除集成「{deletingSystem?.name}」？该操作不可撤销。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={saveSystemMutation.isPending}>取消</AlertDialogCancel>
              <AlertDialogAction
                className="bg-rose-600 text-white hover:bg-rose-600/90"
                disabled={saveSystemMutation.isPending}
                onClick={(event) => {
                  event.preventDefault();
                  if (deletingSystem) saveSystemMutation.mutate({ system: deletingSystem });
                }}
              >
                {saveSystemMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
                确认删除
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <AdminPageHeader
        kicker="集成详情"
        title={selectedSystem.name}
        description={selectedSystem.description || selectedSystem.base_url}
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setSelectedSystem(null)}
            >
              <ChevronLeft size={14} />
              返回列表
            </Button>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setEditingApi(null);
                setApiModalOpen(true);
              }}
            >
              <Plus size={14} />
              新增接口
            </Button>
          </>
        }
      />

      {apisQuery.isError ? (
        <ErrorBanner message={(apisQuery.error as Error).message || '加载接口失败'} />
      ) : null}

      <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
        {apisQuery.isLoading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : (
          <DataTable
            columns={apiColumns}
            data={apis}
            emptyState={
              <div className="flex flex-col items-center justify-center py-8">
                <ExternalLink size={32} className="mb-3 text-zinc-300" />
                <p className="text-sm font-semibold text-zinc-600">暂无接口</p>
                <p className="mt-1 text-xs font-medium text-zinc-400">
                  为 {selectedSystem.name} 定义可用的 API 接口
                </p>
              </div>
            }
          />
        )}
      </section>

      {testState && (
        <TestDrawer
          state={testState}
          api={apis.find((a) => a.id === testState.apiId)}
          onClose={() => setTestState(null)}
          onParamChange={(name, value) =>
            setTestState((prev) => (prev ? { ...prev, params: { ...prev.params, [name]: value } } : null))
          }
          onRun={() => {
            const api = apis.find((a) => a.id === testState.apiId);
            if (api) testMutation.mutate(api);
          }}
        />
      )}

      <ApiModal
        open={apiModalOpen}
        systemId={selectedSystem.id}
        editingApi={editingApi}
        onClose={() => {
          setApiModalOpen(false);
          setEditingApi(null);
        }}
      />

      <AlertDialog open={deletingApi !== null} onOpenChange={(next) => !next && setDeletingApi(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除接口</AlertDialogTitle>
            <AlertDialogDescription>
              确定删除接口「{deletingApi?.display_name}」？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteApiMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteApiMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingApi) deleteApiMutation.mutate(deletingApi);
              }}
            >
              {deleteApiMutation.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
