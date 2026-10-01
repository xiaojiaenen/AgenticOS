/**
 * 智能体配置：智能体编辑弹窗（左栏基础信息 + 右栏工具/技能/集成面板）。
 * 从 AgentManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Loader2, Save } from 'lucide-react';
import { Button } from '@/components/shadcn/button';
import { Input } from '@/components/shadcn/input';
import { Label } from '@/components/shadcn/label';
import { Switch } from '@/components/shadcn/switch';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shadcn/select';
import { cn } from '@/lib/utils';
import {
  AgentProfile,
  AgentProfilePayload,
  createAgentProfile,
  updateAgentProfile,
} from '@/services/agentProfileService';
import type { AdminUser } from '@/services/userService';
import { AgentMode, ToolCatalogItem } from '@/services/toolConfigService';
import type { IntegrationSystem } from '@/services/integrationService';
import { MODE_SYSTEM_PROMPTS } from '@/constants/modePrompts';
import { AgentToolsPanel } from './AgentToolsPanel';
import { AgentSkillsPanel } from './AgentSkillsPanel';
import { AgentIntegrationsPanel } from './AgentIntegrationsPanel';
import {
  AGENT_MODES,
  agentFormSchema,
  defaultTools,
  draftFromProfile,
  modeDefaultPrompt,
  type AgentFormValues,
} from './agentHelpers';

export function AgentFormDialog({
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

  const audienceMode = form.watch('audience_mode');
  const audienceUserIds = form.watch('audience_user_ids');
  const responseMode = form.watch('response_mode');
  const systemPrompt = form.watch('system_prompt');
  const slug = form.watch('slug');
  const maxSteps = form.watch('max_steps');
  const enabled = form.watch('enabled');
  const listed = form.watch('listed');

  const toggleToolExpand = (toolName: string) => {
    setExpandedTools((prev) => {
      const next = new Set(prev);
      if (next.has(toolName)) next.delete(toolName);
      else next.add(toolName);
      return next;
    });
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
                  <span className="text-[11px] font-medium text-[var(--muted-foreground)]">
                    控制智能体单次对话的最大工具调用轮数，PPT 模式建议 30–50
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 lg:col-span-2">
                  <div className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5">
                    <span className="text-sm font-semibold text-zinc-700">启用</span>
                    <Switch checked={enabled} onCheckedChange={(v) => form.setValue('enabled', v)} />
                  </div>
                  <div className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5">
                    <span className="text-sm font-semibold text-zinc-700">上架</span>
                    <Switch checked={listed} onCheckedChange={(v) => form.setValue('listed', v)} />
                  </div>
                </div>

                {/* 启用范围 */}
                <div className="space-y-3 lg:col-span-2">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs font-semibold uppercase tracking-wide text-[var(--muted-foreground)]">
                      启用范围
                    </span>
                    <span className="text-xs font-medium text-[var(--muted-foreground)]">
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
                          : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-zinc-300',
                      )}
                    >
                      <div className="text-sm font-semibold text-[var(--foreground)]">全体用户</div>
                      <div className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
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
                          : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-zinc-300',
                      )}
                    >
                      <div className="text-sm font-semibold text-[var(--foreground)]">指定用户</div>
                      <div className="mt-1 text-xs font-medium text-[var(--muted-foreground)]">
                        只有选中的用户能看见并使用。
                      </div>
                    </button>
                  </div>

                  {audienceMode === 'selected' && (
                    <div className="max-h-52 overflow-y-auto rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-3">
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
                                    : 'border-[var(--border-subtle)] bg-[var(--surface-1)] text-zinc-600 hover:border-zinc-300',
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
                                      : 'border-[var(--border-subtle)] bg-[var(--surface-1)] text-transparent',
                                  )}
                                >
                                  <Check size={12} />
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="px-3 py-4 text-sm font-medium text-[var(--muted-foreground)]">
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
                    className="w-full resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3.5 py-2.5 text-sm font-medium leading-6 text-[var(--foreground)] outline-none transition focus:border-indigo-300 focus:ring-[3px] focus:ring-indigo-100"
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
            <div className="min-h-0 overflow-y-auto border-t border-zinc-100 bg-[var(--surface-2)] p-5 xl:border-l xl:border-t-0">
              <Tabs value={rightTab} onValueChange={(v) => setRightTab(v as typeof rightTab)}>
                <TabsList className="mb-4 grid w-full grid-cols-3">
                  <TabsTrigger value="tools">工具</TabsTrigger>
                  <TabsTrigger value="skills">技能</TabsTrigger>
                  <TabsTrigger value="integrations">集成</TabsTrigger>
                </TabsList>
              </Tabs>

              {rightTab === 'tools' && (
                <AgentToolsPanel
                  form={form}
                  catalog={catalog}
                  expandedTools={expandedTools}
                  onToggleToolExpand={toggleToolExpand}
                />
              )}

              {rightTab === 'skills' && (
                <AgentSkillsPanel form={form} availableSkills={availableSkills} />
              )}

              {rightTab === 'integrations' && (
                <AgentIntegrationsPanel form={form} externalSystems={externalSystems} />
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
