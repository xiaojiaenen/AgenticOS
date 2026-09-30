/**
 * 智能体配置：TanStack Query 数据层 + TanStack Table
 * + react-hook-form/zod 表单 + shadcn Select/Dialog/AlertDialog/Tabs。
 * 后端 API 不变（services/agentProfileService.ts、userService.ts、integrationService.ts）。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { toast } from 'sonner';
import {
  Bot,
  Check,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Wrench,
  X,
} from 'lucide-react';
import { DataTable } from './data-table';
import { AdminPageHeader, ErrorBanner, KpiPill } from './shared';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Checkbox } from '@/components/shadcn/checkbox';
import { Switch } from '@/components/shadcn/switch';
import { Skeleton } from '@/components/shadcn/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/shadcn/tabs';
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
import { formatApiDate } from '@/lib/datetime';
import { cn } from '@/lib/utils';
import {
  AgentProfile,
  AgentProfilePayload,
  AgentProfileTool,
  createAgentProfile,
  deleteAgentProfile,
  getAgentProfiles,
  updateAgentProfile,
} from '@/services/agentProfileService';
import { AdminUser, listUsers } from '@/services/userService';
import { AgentMode, ToolCatalogItem } from '@/services/toolConfigService';
import { IntegrationSystem, listSystems } from '@/services/integrationService';
import { MODE_SYSTEM_PROMPTS } from '@/constants/modePrompts';

// ---------------------------------------------------------------------------
// zod schema（对齐后端 AgentProfilePayload）
// ---------------------------------------------------------------------------

const agentFormSchema = z
  .object({
    name: z.string().min(1, '请填写智能体名称'),
    slug: z
      .string()
      .regex(/^[a-z0-9-]*$/, 'slug 仅允许小写字母、数字和连字符'),
    description: z.string(),
    system_prompt: z.string().min(1, '系统提示词不能为空'),
    response_mode: z.enum(['general', 'ppt', 'website', 'email', 'bigdata']),
    max_steps: z.union([z.number().int().min(1).max(2147483647), z.null()]),
    enabled: z.boolean(),
    listed: z.boolean(),
    audience_mode: z.enum(['all', 'selected']),
    audience_user_ids: z.array(z.number()),
    tools: z.array(
      z.object({
        tool_name: z.string(),
        enabled: z.boolean(),
        requires_approval: z.boolean(),
        approval_sub_tools: z.array(z.string()),
      }),
    ),
    skill_ids: z.array(z.number()),
    external_systems: z.array(z.object({ system_id: z.number(), enabled: z.boolean() })),
  })
  .refine((data) => data.audience_mode !== 'selected' || data.audience_user_ids.length > 0, {
    message: '请选择至少一个用户，或切换为全体用户',
    path: ['audience_user_ids'],
  });

type AgentFormValues = z.infer<typeof agentFormSchema>;

const AGENT_MODES: AgentMode[] = ['general', 'ppt', 'website', 'email', 'bigdata'];

function modeLabel(mode: AgentMode): string {
  if (mode === 'ppt') return 'PPT';
  if (mode === 'website') return '网站';
  if (mode === 'email') return '邮箱';
  if (mode === 'bigdata') return '大数据';
  return '通用';
}

function modeDefaultPrompt(mode: AgentMode): string {
  return MODE_SYSTEM_PROMPTS[mode] || MODE_SYSTEM_PROMPTS.general;
}

function defaultTools(catalog: ToolCatalogItem[]): AgentProfileTool[] {
  return catalog.map((item) => ({
    tool_name: item.name,
    enabled: item.name === 'calc' || item.name === 'time',
    requires_approval: false,
    approval_sub_tools: [],
  }));
}

function draftFromProfile(profile: AgentProfile, catalog: ToolCatalogItem[]): AgentFormValues {
  return {
    name: profile.name,
    slug: profile.slug,
    description: profile.description,
    system_prompt: profile.system_prompt,
    response_mode: profile.response_mode,
    max_steps: profile.max_steps ?? null,
    enabled: profile.enabled,
    listed: profile.listed,
    audience_mode: profile.audience_mode,
    audience_user_ids: profile.audience_users.map((user) => user.id),
    tools:
      profile.tools.length > 0
        ? profile.tools.map((tool) => ({ ...tool, approval_sub_tools: [...tool.approval_sub_tools] }))
        : defaultTools(catalog),
    skill_ids: profile.skills.map((skill) => skill.id),
    external_systems: (profile.external_systems || []).map((es) => ({
      system_id: es.system_id,
      enabled: es.enabled,
    })),
  };
}

// ---------------------------------------------------------------------------
// Toggle 开关（视觉与旧版一致）
// ---------------------------------------------------------------------------

function Toggle({
  checked,
  disabled,
  onClick,
}: {
  checked: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex h-8 w-14 items-center rounded-full p-1 transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'justify-end bg-zinc-900 shadow-md' : 'justify-start bg-zinc-200 hover:bg-zinc-300',
      )}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-sm">
        {checked ? <Check size={12} className="text-zinc-900" /> : <X size={12} className="text-zinc-400" />}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// 智能体编辑弹窗
// ---------------------------------------------------------------------------

function AgentFormDialog({
  open,
  editingProfile,
  catalog,
  availableSkills,
  availableUsers,
  externalSystems,
  onClose,
}: {
  open: boolean;
  editingProfile: AgentProfile | null;
  catalog: ToolCatalogItem[];
  availableSkills: AgentProfile['skills'];
  availableUsers: AdminUser[];
  externalSystems: IntegrationSystem[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const isEdit = editingProfile !== null;
  const [rightTab, setRightTab] = React.useState<'tools' | 'skills' | 'integrations'>('tools');
  const [expandedTools, setExpandedTools] = React.useState<Set<string>>(new Set());

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    defaultValues: {
      name: '新的智能体',
      slug: '',
      description: '',
      system_prompt: MODE_SYSTEM_PROMPTS.general,
      response_mode: 'general',
      max_steps: null,
      enabled: true,
      listed: false,
      audience_mode: 'all',
      audience_user_ids: [],
      tools: defaultTools(catalog),
      skill_ids: [],
      external_systems: [],
    },
  });

  React.useEffect(() => {
    if (open) {
      setRightTab('tools');
      setExpandedTools(new Set());
      form.reset(
        editingProfile
          ? draftFromProfile(editingProfile, catalog)
          : {
              name: '新的智能体',
              slug: '',
              description: '',
              system_prompt: MODE_SYSTEM_PROMPTS.general,
              response_mode: 'general',
              max_steps: null,
              enabled: true,
              listed: false,
              audience_mode: 'all',
              audience_user_ids: [],
              tools: defaultTools(catalog),
              skill_ids: [],
              external_systems: [],
            },
      );
    }
  }, [open, editingProfile, catalog, form]);

  const saveMutation = useMutation({
    mutationFn: async (values: AgentFormValues) => {
      const payload: AgentProfilePayload = {
        name: values.name.trim(),
        slug: values.slug.trim() || undefined,
        description: values.description,
        system_prompt: values.system_prompt,
        response_mode: values.response_mode,
        enabled: values.enabled,
        listed: values.listed,
        audience_mode: values.audience_mode,
        audience_user_ids: values.audience_user_ids,
        tools: values.tools,
        skill_ids: values.skill_ids,
        external_systems: values.external_systems,
        max_steps: values.max_steps,
      };
      return isEdit && editingProfile
        ? updateAgentProfile(editingProfile.id, payload)
        : createAgentProfile(payload);
    },
    onSuccess: () => {
      toast.success(isEdit ? '智能体配置已更新' : '智能体已创建');
      void queryClient.invalidateQueries({ queryKey: ['admin', 'agents'] });
      onClose();
    },
    onError: (err: Error) => toast.error(err.message || '保存失败'),
  });

  const catalogByName = React.useMemo(
    () => new Map(catalog.map((item) => [item.name, item])),
    [catalog],
  );

  const tools = form.watch('tools');
  const skillIds = form.watch('skill_ids');
  const audienceMode = form.watch('audience_mode');
  const audienceUserIds = form.watch('audience_user_ids');
  const responseMode = form.watch('response_mode');
  const systemPrompt = form.watch('system_prompt');
  const slug = form.watch('slug');
  const maxSteps = form.watch('max_steps');
  const enabled = form.watch('enabled');
  const listed = form.watch('listed');
  const externalSystemsValue = form.watch('external_systems');

  const updateTool = (toolName: string, patch: Partial<AgentProfileTool>) => {
    const current = form.getValues('tools');
    form.setValue(
      'tools',
      current.map((tool) => (tool.tool_name === toolName ? { ...tool, ...patch } : tool)),
      { shouldDirty: true },
    );
  };

  const toggleSubToolApproval = (toolName: string, subToolName: string) => {
    const current = form.getValues('tools');
    form.setValue(
      'tools',
      current.map((tool) => {
        if (tool.tool_name !== toolName) return tool;
        const currentSubs = tool.approval_sub_tools;
        const next = currentSubs.includes(subToolName)
          ? currentSubs.filter((s) => s !== subToolName)
          : [...currentSubs, subToolName];
        return { ...tool, approval_sub_tools: next, requires_approval: true };
      }),
      { shouldDirty: true },
    );
  };

  const toggleToolExpand = (toolName: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(toolName)) next.delete(toolName);
      else next.add(toolName);
      return next;
    });
  };

  const toggleSkill = (skillId: number) => {
    const nextSkillIds = skillIds.includes(skillId)
      ? skillIds.filter((item) => item !== skillId)
      : [...skillIds, skillId];
    const hasAnySkills = nextSkillIds.length > 0;
    form.setValue('skill_ids', nextSkillIds, { shouldDirty: true });
    const current = form.getValues('tools');
    form.setValue(
      'tools',
      current.map((tool) =>
        tool.tool_name === 'skill' ? { ...tool, enabled: hasAnySkills ? true : tool.enabled } : tool,
      ),
      { shouldDirty: true },
    );
  };

  const toggleAudienceUser = (userId: number) => {
    form.setValue(
      'audience_user_ids',
      audienceUserIds.includes(userId)
        ? audienceUserIds.filter((item) => item !== userId)
        : [...audienceUserIds, userId],
      { shouldDirty: true },
    );
  };

  const toggleExternalSystem = (systemId: number) => {
    const current = externalSystemsValue;
    const exists = current.some((es) => es.system_id === systemId);
    form.setValue(
      'external_systems',
      exists
        ? current.filter((es) => es.system_id !== systemId)
        : [...current, { system_id: systemId, enabled: true }],
      { shouldDirty: true },
    );
  };

  const selectedSkills = availableSkills.filter((skill) => skillIds.includes(skill.id));
  const enabledTools = tools.filter((tool) => tool.enabled).length;
  const skillToolEnabled = tools.find((tool) => tool.tool_name === 'skill')?.enabled ?? false;

  const currentPromptIsDefault = Object.values(MODE_SYSTEM_PROMPTS).some(
    (p) => p.trim() === systemPrompt.trim(),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[min(92vh,980px)] w-[min(1180px,calc(100vw-32px))] max-w-none flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑智能体' : '新建智能体'}</DialogTitle>
          <DialogDescription>完成基础信息、工具审批和 Skill 绑定。</DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((values) => void saveMutation.mutateAsync(values))}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1.05fr)_420px]">
            {/* 左栏：基础信息 */}
            <div className="min-h-0 overflow-y-auto p-5">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="agent-name">名称</Label>
                  <Input id="agent-name" {...form.register('name')} />
                  {form.formState.errors.name ? (
                    <p className="text-xs font-medium text-rose-600">
                      {form.formState.errors.name.message}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="agent-slug">Slug</Label>
                  <Input
                    id="agent-slug"
                    disabled={editingProfile?.is_builtin}
                    value={slug}
                    onChange={(event) => form.setValue('slug', event.target.value, { shouldDirty: true })}
                  />
                  {form.formState.errors.slug ? (
                    <p className="text-xs font-medium text-rose-600">
                      {form.formState.errors.slug.message}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-1.5 lg:col-span-2">
                  <Label htmlFor="agent-description">描述</Label>
                  <Input id="agent-description" {...form.register('description')} />
                </div>

                <div className="space-y-1.5">
                  <Label>响应模式</Label>
                  <Select
                    value={responseMode}
                    onValueChange={(value) => {
                      const newMode = value as AgentMode;
                      form.setValue('response_mode', newMode, { shouldDirty: true });
                      if (currentPromptIsDefault) {
                        form.setValue('system_prompt', modeDefaultPrompt(newMode), {
                          shouldDirty: true,
                        });
                      }
                    }}
                  >
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {AGENT_MODES.map((mode) => (
                        <SelectItem key={mode} value={mode}>
                          {mode}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="agent-max-steps">最大步数</Label>
                  <Input
                    id="agent-max-steps"
                    type="number"
                    min={1}
                    max={2147483647}
                    placeholder="留空使用全局默认（10）"
                    value={maxSteps ?? ''}
                    onChange={(event) => {
                      const v = event.target.value;
                      form.setValue(
                        'max_steps',
                        v === '' ? null : Math.min(2147483647, Math.max(1, Number(v))),
                        { shouldDirty: true },
                      );
                    }}
                  />
                  <span className="text-[11px] font-medium text-zinc-400">
                    控制智能体单次对话的最大工具调用轮数，PPT 模式建议 30–50
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 lg:col-span-2">
                  <div className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white px-3.5 py-2.5">
                    <span className="text-sm font-semibold text-zinc-700">启用</span>
                    <Switch checked={enabled} onCheckedChange={(v) => form.setValue('enabled', v)} />
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-zinc-200 bg-white px-3.5 py-2.5">
                    <span className="text-sm font-semibold text-zinc-700">上架</span>
                    <Switch checked={listed} onCheckedChange={(v) => form.setValue('listed', v)} />
                  </div>
                </div>

                {/* 启用范围 */}
                <div className="space-y-3 lg:col-span-2">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
                      启用范围
                    </span>
                    <span className="text-xs font-medium text-zinc-400">
                      {audienceMode === 'selected'
                        ? `已选择 ${audienceUserIds.length} 人`
                        : '面向所有普通用户'}
                    </span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <button
                      type="button"
                      onClick={() => form.setValue('audience_mode', 'all', { shouldDirty: true })}
                      className={cn(
                        'rounded-lg border px-3.5 py-2.5 text-left transition-all',
                        audienceMode === 'all'
                          ? 'border-indigo-300 bg-indigo-50/80 shadow-sm'
                          : 'border-zinc-200 bg-white hover:border-zinc-300',
                      )}
                    >
                      <div className="text-sm font-semibold text-zinc-900">全体用户</div>
                      <div className="mt-1 text-xs font-medium text-zinc-500">
                        所有已登录用户都能看见并使用。
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => form.setValue('audience_mode', 'selected', { shouldDirty: true })}
                      className={cn(
                        'rounded-lg border px-3.5 py-2.5 text-left transition-all',
                        audienceMode === 'selected'
                          ? 'border-indigo-300 bg-indigo-50/80 shadow-sm'
                          : 'border-zinc-200 bg-white hover:border-zinc-300',
                      )}
                    >
                      <div className="text-sm font-semibold text-zinc-900">指定用户</div>
                      <div className="mt-1 text-xs font-medium text-zinc-500">
                        只有选中的用户能看见并使用。
                      </div>
                    </button>
                  </div>

                  {audienceMode === 'selected' && (
                    <div className="max-h-52 overflow-y-auto rounded-lg border border-zinc-200 bg-white p-3">
                      {availableUsers.length > 0 ? (
                        <div className="grid gap-2 md:grid-cols-2">
                          {availableUsers.map((user) => {
                            const selected = audienceUserIds.includes(user.id);
                            return (
                              <button
                                key={user.id}
                                type="button"
                                onClick={() => toggleAudienceUser(user.id)}
                                className={cn(
                                  'flex min-w-0 items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-all',
                                  selected
                                    ? 'border-indigo-300 bg-indigo-50 text-indigo-900'
                                    : 'border-zinc-200 bg-white text-zinc-600 hover:border-zinc-300',
                                )}
                              >
                                <span className="min-w-0">
                                  <span className="block truncate text-sm font-semibold">
                                    {user.name || user.email}
                                  </span>
                                  <span className="block truncate text-[11px] font-medium opacity-70">
                                    {user.email}
                                  </span>
                                </span>
                                <span
                                  className={cn(
                                    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border',
                                    selected
                                      ? 'border-indigo-400 bg-indigo-600 text-white'
                                      : 'border-zinc-200 bg-white text-transparent',
                                  )}
                                >
                                  <Check size={12} />
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="px-3 py-4 text-sm font-medium text-zinc-500">
                          暂无可选择的启用用户。
                        </div>
                      )}
                    </div>
                  )}
                  {form.formState.errors.audience_user_ids ? (
                    <p className="text-xs font-medium text-rose-600">
                      {form.formState.errors.audience_user_ids.message}
                    </p>
                  ) : null}
                </div>

                <div className="space-y-1.5 lg:col-span-2">
                  <Label htmlFor="agent-system-prompt">系统提示词</Label>
                  <textarea
                    id="agent-system-prompt"
                    rows={10}
                    {...form.register('system_prompt')}
                    className="w-full resize-y rounded-md border border-zinc-200 bg-white px-3.5 py-2.5 text-sm font-medium leading-6 text-zinc-800 outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
                  />
                  {form.formState.errors.system_prompt ? (
                    <p className="text-xs font-medium text-rose-600">
                      {form.formState.errors.system_prompt.message}
                    </p>
                  ) : null}
                </div>
              </div>
            </div>

            {/* 右栏：工具 / Skill / 集成 */}
            <div className="min-h-0 overflow-y-auto border-t border-zinc-100 bg-zinc-50/60 p-5 xl:border-l xl:border-t-0">
              <Tabs value={rightTab} onValueChange={(v) => setRightTab(v as typeof rightTab)}>
                <TabsList className="mb-4 grid w-full grid-cols-3">
                  <TabsTrigger value="tools">工具</TabsTrigger>
                  <TabsTrigger value="skills">技能</TabsTrigger>
                  <TabsTrigger value="integrations">集成</TabsTrigger>
                </TabsList>
              </Tabs>

              {rightTab === 'tools' && (
                <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                        工具与审批
                      </p>
                      <h4 className="mt-1 text-base font-semibold text-zinc-900">启用状态与审批开关</h4>
                    </div>
                    <span className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-500">
                      已启用 {enabledTools}/{tools.length}
                    </span>
                  </div>

                  <div className="space-y-3">
                    {tools.map((tool) => {
                      const meta = catalogByName.get(tool.tool_name);
                      const isSkillTool = tool.tool_name === 'skill';
                      const subTools = meta?.sub_tools || [];
                      const hasSubTools = subTools.length > 1;
                      const isExpanded = expandedTools.has(tool.tool_name);
                      const approvedSubTools = tool.approval_sub_tools;

                      return (
                        <div key={tool.tool_name} className="rounded-lg border border-zinc-200 bg-white p-3.5">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <p className="text-sm font-semibold text-zinc-900">
                                  {meta?.label || tool.tool_name}
                                </p>
                                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-zinc-400">
                                  {tool.tool_name}
                                </span>
                              </div>
                              <p className="mt-1 text-xs font-medium leading-5 text-zinc-500">
                                {meta?.description}
                              </p>
                              {isSkillTool && (
                                <p className="mt-2 text-xs font-semibold text-amber-700">
                                  Wuwei 已内建 skill 脚本执行审批、超时和路径校验；这里保留的是工具启用开关。
                                </p>
                              )}
                            </div>
                          </div>

                          <div className="mt-4 flex items-center gap-3">
                            <div className="flex flex-1 items-center justify-between rounded-lg border border-zinc-200 bg-white px-3.5 py-2.5">
                              <span className="text-sm font-semibold text-zinc-700">启用</span>
                              <Toggle
                                checked={tool.enabled}
                                onClick={() => updateTool(tool.tool_name, { enabled: !tool.enabled })}
                              />
                            </div>
                            {hasSubTools ? (
                              <Button
                                type="button"
                                variant="outline"
                                onClick={() => toggleToolExpand(tool.tool_name)}
                                className={cn('gap-2', isExpanded && 'border-indigo-300 text-indigo-700')}
                              >
                                子工具审批
                                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold">
                                  {subTools.length}
                                </span>
                                <svg
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2.5"
                                  className={cn('transition-transform', isExpanded && 'rotate-180')}
                                >
                                  <path d="M6 9l6 6 6-6" />
                                </svg>
                              </Button>
                            ) : (
                              <div className="flex flex-1 items-center justify-between rounded-lg border border-zinc-200 bg-white px-3.5 py-2.5">
                                <span className="text-sm font-semibold text-zinc-700">需要审批</span>
                                <Toggle
                                  checked={isSkillTool ? true : tool.requires_approval}
                                  disabled={!tool.enabled || isSkillTool}
                                  onClick={() =>
                                    updateTool(tool.tool_name, {
                                      requires_approval: !tool.requires_approval,
                                    })
                                  }
                                />
                              </div>
                            )}
                          </div>

                          {hasSubTools && isExpanded && (
                            <div className="mt-4 space-y-2 overflow-hidden border-t border-zinc-100 pt-4">
                              <div className="mb-3 flex items-center justify-between">
                                <span className="text-xs font-medium text-zinc-500">
                                  点击子工具可跳过审批直接执行
                                </span>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="xs"
                                  className="text-indigo-600"
                                  onClick={() => {
                                    const allNeedApproval =
                                      tool.requires_approval && approvedSubTools.length === 0;
                                    if (allNeedApproval) {
                                      updateTool(tool.tool_name, { requires_approval: false });
                                    } else {
                                      updateTool(tool.tool_name, {
                                        requires_approval: true,
                                        approval_sub_tools: [],
                                      });
                                    }
                                  }}
                                >
                                  {tool.requires_approval && approvedSubTools.length === 0
                                    ? '全部跳过审批'
                                    : '全部需要审批'}
                                </Button>
                              </div>
                              {subTools.map((sub) => {
                                const isSkipped =
                                  tool.requires_approval &&
                                  approvedSubTools.length > 0 &&
                                  !approvedSubTools.includes(sub.name);
                                const isApproved = tool.requires_approval && !isSkipped;
                                return (
                                  <div
                                    key={sub.name}
                                    className={cn(
                                      'flex items-center justify-between rounded-lg border px-3 py-2 transition-colors',
                                      isApproved
                                        ? 'border-amber-200/80 bg-amber-50/60'
                                        : 'border-zinc-200/80 bg-white/80',
                                    )}
                                  >
                                    <div className="min-w-0">
                                      <p className="text-xs font-medium text-zinc-800">{sub.label}</p>
                                      <p className="text-[10px] font-medium text-zinc-400">{sub.name}</p>
                                    </div>
                                    <Toggle
                                      checked={isApproved}
                                      disabled={!tool.enabled}
                                      onClick={() => toggleSubToolApproval(tool.tool_name, sub.name)}
                                    />
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {rightTab === 'skills' && (
                <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                        可用 Skill
                      </p>
                      <h4 className="mt-1 text-base font-semibold text-zinc-900">按智能体选择 Skill</h4>
                    </div>
                    <span className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-500">
                      已选 {selectedSkills.length}/{availableSkills.length}
                    </span>
                  </div>

                  {!skillToolEnabled && (
                    <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm font-medium text-amber-700">
                      选中 Skill 后，系统会自动打开 `skill` 工具；脚本执行审批由 Wuwei 在运行时接管。
                    </div>
                  )}

                  <div className="space-y-3">
                    {availableSkills.length > 0 ? (
                      availableSkills.map((skill) => {
                        const selected = skillIds.includes(skill.id);
                        return (
                          <button
                            key={skill.id}
                            type="button"
                            onClick={() => toggleSkill(skill.id)}
                            className={cn(
                              'w-full rounded-lg border p-3.5 text-left transition-all',
                              selected
                                ? 'border-indigo-300 bg-indigo-50/70 shadow-sm'
                                : 'border-zinc-200 bg-white hover:border-zinc-300',
                            )}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-zinc-900">{skill.name}</p>
                                <p className="mt-1 truncate text-[11px] font-semibold tracking-wide text-zinc-400">
                                  {skill.slug}
                                </p>
                              </div>
                              <span
                                className={cn(
                                  'rounded-full px-2 py-1 text-[10px] font-semibold',
                                  selected ? 'bg-indigo-100 text-indigo-700' : 'bg-zinc-100 text-zinc-500',
                                )}
                              >
                                {selected ? '已选择' : '可选择'}
                              </span>
                            </div>
                            <p className="mt-3 text-xs font-medium leading-5 text-zinc-500">
                              {skill.description || '暂无描述'}
                            </p>
                            {skill.has_python_scripts && (
                              <div className="mt-3">
                                <span className="rounded-full border border-amber-100 bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-700">
                                  含 Python 脚本
                                </span>
                              </div>
                            )}
                            {skill.has_references && (
                              <div className="mt-2">
                                <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2.5 py-1 text-[10px] font-semibold text-indigo-700">
                                  {skill.reference_paths.length} refs
                                </span>
                              </div>
                            )}
                          </button>
                        );
                      })
                    ) : (
                      <div className="rounded-lg border border-dashed border-zinc-200 bg-white/80 px-4 py-4 text-sm font-medium text-zinc-500">
                        还没有可绑定的 Skill，请先去 Skill 管理页创建或上传。
                      </div>
                    )}
                  </div>
                </div>
              )}

              {rightTab === 'integrations' && (
                <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                        集成系统
                      </p>
                      <h4 className="mt-1 text-base font-semibold text-zinc-900">绑定外部系统</h4>
                    </div>
                    <span className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs font-semibold text-zinc-500">
                      已选 {externalSystemsValue.length}/{externalSystems.length}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {externalSystems.length > 0 ? (
                      externalSystems.map((sys) => {
                        const selected = externalSystemsValue.some((es) => es.system_id === sys.id);
                        return (
                          <button
                            key={sys.id}
                            type="button"
                            onClick={() => toggleExternalSystem(sys.id)}
                            className={cn(
                              'w-full rounded-lg border p-3.5 text-left transition-all',
                              selected
                                ? 'border-emerald-300 bg-emerald-50/70 shadow-sm'
                                : 'border-zinc-200 bg-white hover:border-zinc-300',
                            )}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-semibold text-zinc-900">{sys.name}</p>
                                <p className="mt-1 truncate text-[11px] font-semibold tracking-wide text-zinc-400">
                                  {sys.base_url}
                                </p>
                              </div>
                              <span
                                className={cn(
                                  'rounded-full px-2 py-1 text-[10px] font-semibold',
                                  selected ? 'bg-emerald-100 text-emerald-700' : 'bg-zinc-100 text-zinc-500',
                                )}
                              >
                                {selected ? '已绑定' : '未绑定'}
                              </span>
                            </div>
                            <p className="mt-3 text-xs font-medium leading-5 text-zinc-500">
                              {sys.description || '暂无描述'}
                            </p>
                            <div className="mt-2 flex gap-2">
                              <span className="rounded-full border border-zinc-100 bg-zinc-50 px-2.5 py-1 text-[10px] font-semibold text-zinc-600">
                                {sys.auth_type}
                              </span>
                              <span className="rounded-full border border-zinc-100 bg-zinc-50 px-2.5 py-1 text-[10px] font-semibold text-zinc-600">
                                {sys.api_count} API
                              </span>
                            </div>
                          </button>
                        );
                      })
                    ) : (
                      <div className="rounded-lg border border-dashed border-zinc-200 bg-white/80 px-4 py-4 text-sm font-medium text-zinc-500">
                        还没有已启用的集成系统。
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="border-t border-zinc-100 pt-4">
            <Button type="button" variant="outline" onClick={onClose} disabled={saveMutation.isPending}>
              取消
            </Button>
            <Button type="submit" disabled={saveMutation.isPending} className="gap-2">
              {saveMutation.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Save size={16} />
              )}
              保存配置
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

export const AgentManagement = () => {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = React.useState(false);
  const [editingProfile, setEditingProfile] = React.useState<AgentProfile | null>(null);
  const [deletingProfile, setDeletingProfile] = React.useState<AgentProfile | null>(null);

  const profilesQuery = useQuery({
    queryKey: ['admin', 'agents'],
    queryFn: getAgentProfiles,
  });

  const usersQuery = useQuery({
    queryKey: ['admin', 'users', 'all'],
    queryFn: () => listUsers({ offset: 0, limit: 100 }),
    select: (data) => data.items.filter((user) => user.is_active),
  });

  const systemsQuery = useQuery({
    queryKey: ['admin', 'integrations', 'enabled'],
    queryFn: async () => {
      const response = await listSystems();
      return response.items.filter((s) => s.enabled);
    },
    retry: 0,
  });

  const profiles = profilesQuery.data?.items ?? [];
  const catalog = profilesQuery.data?.catalog ?? [];
  const availableSkills = profilesQuery.data?.available_skills ?? [];
  const availableUsers = usersQuery.data ?? [];
  const externalSystems = systemsQuery.data ?? [];

  const deleteMutation = useMutation({
    mutationFn: (profileId: number) => deleteAgentProfile(profileId),
    onSuccess: () => {
      toast.success('智能体已删除');
      setDeletingProfile(null);
      void queryClient.invalidateQueries({ queryKey: ['admin', 'agents'] });
    },
    onError: (err: Error) => toast.error(err.message || '删除失败'),
  });

  const enabledAgents = profiles.filter((profile) => profile.enabled).length;
  const listedAgents = profiles.filter((profile) => profile.listed).length;
  const totalBindings = profiles.reduce((sum, profile) => sum + profile.skills.length, 0);

  const columns = React.useMemo<ColumnDef<AgentProfile, unknown>[]>(
    () => [
      {
        id: 'agent',
        header: '智能体',
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <p className="truncate text-sm font-semibold text-zinc-900">{profile.name}</p>
                {profile.is_builtin && (
                  <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                    内置
                  </span>
                )}
              </div>
              <p className="mt-0.5 truncate text-xs font-semibold tracking-wide text-zinc-400">
                {profile.slug}
              </p>
              <p className="mt-1 line-clamp-2 max-w-[360px] text-sm font-medium leading-6 text-zinc-500">
                {profile.description || '暂无描述'}
              </p>
            </div>
          );
        },
      },
      {
        accessorKey: 'response_mode',
        header: '模式',
        cell: ({ getValue }) => (
          <span className="text-sm font-semibold text-zinc-900">
            {modeLabel(getValue() as AgentMode)}
          </span>
        ),
      },
      {
        id: 'tools',
        header: '工具',
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <span className="text-sm font-medium text-zinc-600">
              {profile.tools.filter((tool) => tool.enabled).length} / {profile.tools.length}
            </span>
          );
        },
      },
      {
        id: 'skills',
        header: 'Skill',
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          if (profile.skills.length === 0) {
            return <span className="text-sm font-medium text-zinc-400">未绑定</span>;
          }
          return (
            <div className="flex flex-wrap gap-1.5">
              {profile.skills.slice(0, 2).map((skill) => (
                <span
                  key={skill.id}
                  className="rounded-full border border-zinc-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-zinc-600"
                >
                  {skill.name}
                </span>
              ))}
              {profile.skills.length > 2 && (
                <span className="rounded-full border border-zinc-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-zinc-500">
                  +{profile.skills.length - 2}
                </span>
              )}
            </div>
          );
        },
      },
      {
        id: 'status',
        header: '状态',
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <div className="flex flex-wrap gap-1.5">
              <span
                className={cn(
                  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
                  profile.enabled
                    ? 'border-emerald-200/80 bg-emerald-50 text-emerald-700'
                    : 'border-zinc-200 bg-zinc-100 text-zinc-500',
                )}
              >
                {profile.enabled ? '启用' : '停用'}
              </span>
              <span
                className={cn(
                  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold',
                  profile.listed
                    ? 'border-amber-200/80 bg-amber-50 text-amber-700'
                    : 'border-zinc-200 bg-zinc-100 text-zinc-500',
                )}
              >
                {profile.listed ? '上架' : '未上架'}
              </span>
              <span className="inline-flex items-center rounded-full border border-indigo-200/80 bg-indigo-50 px-2.5 py-0.5 text-[11px] font-semibold text-indigo-700">
                {profile.audience_mode === 'selected'
                  ? `指定用户 ${profile.audience_users.length}`
                  : '全体用户'}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: 'updated_at',
        header: '更新时间',
        cell: ({ getValue }) => (
          <span className="text-sm font-medium text-zinc-600">{formatApiDate(String(getValue()))}</span>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="block text-right">操作</span>,
        enableSorting: false,
        cell: ({ row }) => {
          const profile = row.original;
          return (
            <div className="flex justify-end gap-1.5">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={() => {
                  setEditingProfile(profile);
                  setFormOpen(true);
                }}
              >
                <Wrench size={14} />
                编辑
              </Button>
              {!profile.is_builtin && (
                <Button
                  variant="destructive"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => setDeletingProfile(profile)}
                >
                  <Trash2 size={14} />
                  删除
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    [],
  );

  if (profilesQuery.isLoading) {
    return (
      <div className="space-y-4">
        <AdminPageHeader kicker="智能体配置" title="智能体目录" />
        <div className="space-y-3 rounded-lg border border-zinc-200/80 bg-white p-5 shadow-sm">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <AdminPageHeader
        kicker="智能体配置"
        title="智能体目录"
        actions={
          <>
            <KpiPill label="共" value={profiles.length} />
            <KpiPill label="已启用" value={enabledAgents} />
            <KpiPill label="已上架" value={listedAgents} />
            <KpiPill label="绑定" value={totalBindings} />
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => void profilesQuery.refetch()}
              disabled={profilesQuery.isFetching}
            >
              {profilesQuery.isFetching ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              刷新
            </Button>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => {
                setEditingProfile(null);
                setFormOpen(true);
              }}
            >
              <Plus size={14} />
              新建
            </Button>
          </>
        }
      />

      {profilesQuery.isError ? (
        <ErrorBanner message={(profilesQuery.error as Error).message || '智能体配置加载失败'} />
      ) : null}

      <section className="overflow-hidden rounded-lg border border-zinc-200/80 bg-white shadow-sm">
        <DataTable
          columns={columns}
          data={profiles}
          emptyState={
            <div className="flex flex-col items-center justify-center py-8">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-lg border border-zinc-200 bg-white text-zinc-400 shadow-sm">
                <Bot size={20} />
              </div>
              <p className="text-sm font-semibold text-zinc-600">还没有智能体配置</p>
              <p className="mt-1 text-xs font-medium text-zinc-400">先创建一个智能体，再绑定工具和 Skill</p>
            </div>
          }
        />
      </section>

      <AgentFormDialog
        open={formOpen}
        editingProfile={editingProfile}
        catalog={catalog}
        availableSkills={availableSkills}
        availableUsers={availableUsers}
        externalSystems={externalSystems}
        onClose={() => {
          setFormOpen(false);
          setEditingProfile(null);
        }}
      />

      <AlertDialog
        open={deletingProfile !== null}
        onOpenChange={(next) => !next && setDeletingProfile(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除智能体</AlertDialogTitle>
            <AlertDialogDescription>
              确认删除智能体「{deletingProfile?.name}」吗？删除后用户将无法继续使用该智能体。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMutation.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-rose-600 text-white hover:bg-rose-600/90"
              disabled={deleteMutation.isPending}
              onClick={(event) => {
                event.preventDefault();
                if (deletingProfile) deleteMutation.mutate(deletingProfile.id);
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
