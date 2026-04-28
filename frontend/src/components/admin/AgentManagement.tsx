import React, { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  AlertCircle,
  Bot,
  Check,
  Loader2,
  Plus,
  Save,
  Trash2,
  Wrench,
  X,
} from 'lucide-react';
import { Button } from '../ui/Button';
import { formatApiDate } from '../../lib/datetime';
import { cn } from '../../lib/utils';
import {
  AgentProfile,
  AgentProfilePayload,
  AgentProfileSkill,
  AgentProfileTool,
  createAgentProfile,
  deleteAgentProfile,
  getAgentProfiles,
  updateAgentProfile,
} from '../../services/agentProfileService';
import { AgentMode, ToolCatalogItem } from '../../services/toolConfigService';

type Draft = AgentProfilePayload & { id?: number; is_builtin?: boolean };

const emptyPrompt =
  '你是一个专注于特定任务的 AgenticOS 智能体。请根据用户目标主动拆解任务，必要时调用可用工具，并给出清晰可执行的结果。';

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
        'flex h-8 w-14 items-center rounded-full p-1 transition-all disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'justify-end bg-slate-900' : 'justify-start bg-slate-200',
      )}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-sm">
        {checked ? <Check size={12} className="text-slate-900" /> : <X size={12} className="text-slate-400" />}
      </span>
    </button>
  );
}

function makeDraft(profile: AgentProfile | null, catalog: ToolCatalogItem[]): Draft {
  if (profile) {
    return {
      id: profile.id,
      name: profile.name,
      slug: profile.slug,
      description: profile.description,
      system_prompt: profile.system_prompt,
      response_mode: profile.response_mode,
      avatar: profile.avatar,
      enabled: profile.enabled,
      listed: profile.listed,
      tools: profile.tools.map((tool) => ({ ...tool })),
      skill_ids: profile.skills.map((skill) => skill.id),
      is_builtin: profile.is_builtin,
    };
  }

  return {
    name: '新的智能体',
    slug: '',
    description: '',
    system_prompt: emptyPrompt,
    response_mode: 'general',
    avatar: 'sparkles',
    enabled: true,
    listed: false,
    tools: catalog.map((item) => ({
      tool_name: item.name,
      enabled: item.name === 'calc' || item.name === 'time',
      requires_approval: false,
    })),
    skill_ids: [],
  };
}

function modeLabel(mode: AgentMode) {
  if (mode === 'ppt') return 'PPT';
  if (mode === 'website') return '网站';
  return '通用';
}

export const AgentManagement = () => {
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [catalog, setCatalog] = useState<ToolCatalogItem[]>([]);
  const [availableSkills, setAvailableSkills] = useState<AgentProfileSkill[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const catalogByName = useMemo(() => new Map(catalog.map((item) => [item.name, item])), [catalog]);
  const enabledAgents = profiles.filter((profile) => profile.enabled).length;
  const listedAgents = profiles.filter((profile) => profile.listed).length;
  const totalBindings = profiles.reduce((sum, profile) => sum + profile.skills.length, 0);
  const enabledTools = draft?.tools.filter((tool) => tool.enabled).length ?? 0;
  const selectedSkills = availableSkills.filter((skill) => draft?.skill_ids.includes(skill.id));
  const skillToolEnabled = draft?.tools.find((tool) => tool.tool_name === 'skill')?.enabled ?? false;

  const loadProfiles = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAgentProfiles();
      setProfiles(response.items);
      setCatalog(response.catalog);
      setAvailableSkills(response.available_skills);
    } catch (err) {
      setError(err instanceof Error ? err.message : '智能体配置加载失败');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  const openCreateModal = () => {
    setDraft(makeDraft(null, catalog));
    setMessage(null);
    setError(null);
    setIsModalOpen(true);
  };

  const openEditModal = (profile: AgentProfile) => {
    setDraft(makeDraft(profile, catalog));
    setMessage(null);
    setError(null);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    if (isSaving) return;
    setIsModalOpen(false);
    setDraft(null);
  };

  const patchDraft = (patch: Partial<Draft>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
  };

  const updateTool = (toolName: string, patch: Partial<AgentProfileTool>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        tools: prev.tools.map((tool) => (tool.tool_name === toolName ? { ...tool, ...patch } : tool)),
      };
    });
  };

  const toggleSkill = (skillId: number) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const nextSkillIds = prev.skill_ids.includes(skillId)
        ? prev.skill_ids.filter((item) => item !== skillId)
        : [...prev.skill_ids, skillId];
      const hasAnySkills = nextSkillIds.length > 0;
      return {
        ...prev,
        skill_ids: nextSkillIds,
        tools: prev.tools.map((tool) =>
          tool.tool_name === 'skill'
            ? {
                ...tool,
                enabled: hasAnySkills ? true : tool.enabled,
                requires_approval: hasAnySkills ? true : tool.requires_approval,
              }
            : tool,
        ),
      };
    });
  };

  const saveDraft = async () => {
    if (!draft) return;
    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const payload: AgentProfilePayload = {
        name: draft.name,
        slug: draft.slug || undefined,
        description: draft.description,
        system_prompt: draft.system_prompt,
        response_mode: draft.response_mode,
        avatar: draft.avatar,
        enabled: draft.enabled,
        listed: draft.listed,
        tools: draft.tools,
        skill_ids: draft.skill_ids,
      };
      const saved = draft.id ? await updateAgentProfile(draft.id, payload) : await createAgentProfile(payload);
      setProfiles((prev) => (draft.id ? prev.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...prev]));
      setMessage('智能体配置已保存');
      setIsModalOpen(false);
      setDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  const removeProfile = async (profile: AgentProfile) => {
    if (profile.is_builtin) return;
    const confirmed = window.confirm(`确认删除智能体“${profile.name}”吗？`);
    if (!confirmed) return;
    setIsSaving(true);
    setError(null);
    try {
      await deleteAgentProfile(profile.id);
      setProfiles((prev) => prev.filter((item) => item.id !== profile.id));
      setMessage('智能体已删除');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="admin-page-stage space-y-5">
      <section className="admin-solid-panel px-6 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="admin-section-kicker">智能体配置</p>
            <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">智能体目录</h2>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {message && (
              <div className="rounded-[22px] border border-emerald-100 bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-700">
                {message}
              </div>
            )}
            <div className="rounded-full border border-white/80 bg-white/72 px-4 py-2 text-sm font-semibold text-slate-500">
              共 <span className="font-black text-slate-900">{profiles.length}</span> 个智能体
            </div>
            <div className="rounded-full border border-white/80 bg-white/72 px-4 py-2 text-sm font-semibold text-slate-500">
              已启用 <span className="font-black text-slate-900">{enabledAgents}</span>
            </div>
            <div className="rounded-full border border-white/80 bg-white/72 px-4 py-2 text-sm font-semibold text-slate-500">
              已上架 <span className="font-black text-slate-900">{listedAgents}</span>
            </div>
            <div className="rounded-full border border-white/80 bg-white/72 px-4 py-2 text-sm font-semibold text-slate-500">
              Skill 绑定 <span className="font-black text-slate-900">{totalBindings}</span>
            </div>
            <Button variant="secondary" onClick={loadProfiles} disabled={isLoading || isSaving} className="gap-2">
              {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Wrench size={16} />}
              重新加载
            </Button>
            <Button onClick={openCreateModal} disabled={isLoading || isSaving} className="gap-2">
              <Plus size={16} />
              新建智能体
            </Button>
          </div>
        </div>
      </section>

      {error && (
        <div className="flex items-center gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      <section className="overflow-hidden rounded-[32px] border border-white/70 bg-white/62 shadow-[0_20px_50px_rgba(15,23,42,0.08)] ring-1 ring-white/40 backdrop-blur-[28px]">
        <div className="flex flex-col gap-4 border-b border-white/70 px-6 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="text-center lg:text-left">
            <p className="admin-section-kicker">智能体列表</p>
            <h3 className="mt-2 text-lg font-black tracking-tight text-slate-900">已创建的智能体</h3>
          </div>
        </div>

        <div className="hidden grid-cols-[minmax(250px,1.35fr)_110px_120px_minmax(220px,1fr)_120px_130px_170px] border-b border-slate-100 px-5 py-3 text-center text-xs font-black tracking-[0.18em] text-slate-400 xl:grid">
          <span>智能体</span>
          <span>模式</span>
          <span>工具</span>
          <span>Skill</span>
          <span>状态</span>
          <span>更新时间</span>
          <span>操作</span>
        </div>

        {isLoading ? (
          <div className="flex h-80 items-center justify-center gap-3 text-sm font-bold text-slate-400">
            <Loader2 size={18} className="animate-spin" />
            正在加载智能体配置
          </div>
        ) : profiles.length > 0 ? (
          profiles.map((profile) => (
            <div
              key={profile.id}
              className="admin-table-row grid grid-cols-1 gap-4 border-b border-slate-100/80 px-5 py-4 text-center xl:grid-cols-[minmax(250px,1.35fr)_110px_120px_minmax(220px,1fr)_120px_130px_170px] xl:items-center"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center justify-center gap-2">
                  <p className="truncate text-sm font-black text-slate-900">{profile.name}</p>
                  {profile.is_builtin && (
                    <span className="rounded-full border border-sky-100 bg-sky-50 px-2 py-0.5 text-[10px] font-black text-sky-700">
                      内置
                    </span>
                  )}
                </div>
                <p className="mt-1 truncate text-xs font-black tracking-[0.14em] text-slate-400">{profile.slug}</p>
                <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-slate-500">
                  {profile.description || '暂无描述'}
                </p>
              </div>

              <div className="text-sm font-black text-slate-900">{modeLabel(profile.response_mode)}</div>

              <div className="text-sm font-bold text-slate-600">
                {profile.tools.filter((tool) => tool.enabled).length} / {profile.tools.length}
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                {profile.skills.length > 0 ? (
                  <>
                    {profile.skills.slice(0, 2).map((skill) => (
                      <span
                        key={skill.id}
                        className="rounded-full border border-white/80 bg-white/80 px-3 py-1 text-[11px] font-bold text-slate-600"
                      >
                        {skill.name}
                      </span>
                    ))}
                    {profile.skills.length > 2 && (
                      <span className="rounded-full border border-white/80 bg-white/80 px-3 py-1 text-[11px] font-bold text-slate-500">
                        +{profile.skills.length - 2}
                      </span>
                    )}
                  </>
                ) : (
                  <span className="text-sm font-medium text-slate-400">未绑定</span>
                )}
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1 text-[10px] font-black',
                    profile.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500',
                  )}
                >
                  {profile.enabled ? '启用' : '停用'}
                </span>
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1 text-[10px] font-black',
                    profile.listed ? 'bg-amber-50 text-amber-700' : 'bg-slate-100 text-slate-500',
                  )}
                >
                  {profile.listed ? '上架' : '未上架'}
                </span>
              </div>

              <div className="text-sm font-bold text-slate-600">{formatApiDate(profile.updated_at)}</div>

              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="secondary" onClick={() => openEditModal(profile)} className="gap-2 bg-white/85" size="sm">
                  <Wrench size={15} />
                  编辑
                </Button>
                {!profile.is_builtin && (
                  <Button variant="danger" onClick={() => removeProfile(profile)} className="gap-2" size="sm">
                    <Trash2 size={15} />
                    删除
                  </Button>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="flex h-80 flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/70 text-slate-400 shadow-sm">
              <Bot size={24} />
            </div>
            <p className="text-sm font-black text-slate-600">还没有智能体配置</p>
            <p className="mt-1 text-xs font-medium text-slate-400">先创建一个智能体，再绑定工具和 Skill</p>
          </div>
        )}
      </section>

      <AnimatePresence>
        {isModalOpen && draft && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="admin-modal-shell"
            onMouseDown={closeModal}
          >
            <motion.div
              initial={{ opacity: 0, y: 20, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 20, scale: 0.97 }}
              transition={{ duration: 0.22 }}
              onMouseDown={(event) => event.stopPropagation()}
              className="admin-solid-panel admin-modal-panel flex max-h-[90vh] w-full max-w-7xl flex-col overflow-hidden"
            >
              <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
                <div>
                  <p className="admin-section-kicker">{draft.id ? '编辑智能体' : '新建智能体'}</p>
                  <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">{draft.name || '新的智能体'}</h3>
                  <p className="mt-2 text-sm font-medium text-slate-500">
                    在这里完成基础信息、工具审批和 Skill 绑定。
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closeModal}
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="grid flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1.05fr)_420px]">
                <div className="overflow-y-auto p-6">
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">名称</span>
                      <input
                        value={draft.name}
                        onChange={(event) => patchDraft({ name: event.target.value })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>

                    <label className="space-y-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">Slug</span>
                      <input
                        value={draft.slug || ''}
                        disabled={draft.is_builtin}
                        onChange={(event) => patchDraft({ slug: event.target.value })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition disabled:opacity-60 focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>

                    <label className="space-y-2 lg:col-span-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">描述</span>
                      <input
                        value={draft.description}
                        onChange={(event) => patchDraft({ description: event.target.value })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>

                    <label className="space-y-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">响应模式</span>
                      <select
                        value={draft.response_mode}
                        onChange={(event) => patchDraft({ response_mode: event.target.value as AgentMode })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      >
                        <option value="general">general</option>
                        <option value="ppt">ppt</option>
                        <option value="website">website</option>
                      </select>
                    </label>

                    <div className="grid grid-cols-2 gap-3">
                      <div className="flex items-center justify-between rounded-[24px] border border-white/80 bg-white/72 px-4 py-3">
                        <span className="text-sm font-black text-slate-700">启用</span>
                        <Toggle checked={draft.enabled} onClick={() => patchDraft({ enabled: !draft.enabled })} />
                      </div>
                      <div className="flex items-center justify-between rounded-[24px] border border-white/80 bg-white/72 px-4 py-3">
                        <span className="text-sm font-black text-slate-700">上架</span>
                        <Toggle checked={draft.listed} onClick={() => patchDraft({ listed: !draft.listed })} />
                      </div>
                    </div>

                    <label className="space-y-2 lg:col-span-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">系统提示词</span>
                      <textarea
                        value={draft.system_prompt}
                        onChange={(event) => patchDraft({ system_prompt: event.target.value })}
                        rows={10}
                        className="w-full resize-y rounded-[24px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-medium leading-6 text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>
                  </div>
                </div>

                <div className="overflow-y-auto border-l border-slate-100 bg-white/50 p-6">
                  <div className="space-y-4">
                    <div className="rounded-[28px] border border-white/80 bg-white/82 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                      <div className="mb-4 flex items-center justify-between">
                        <div>
                          <p className="admin-section-kicker">工具与审批</p>
                          <h4 className="mt-1 text-lg font-black text-slate-900">启用状态与审批开关</h4>
                        </div>
                        <span className="rounded-full border border-white/80 bg-white px-3 py-1 text-xs font-black text-slate-500">
                          已启用 {enabledTools}/{draft.tools.length}
                        </span>
                      </div>

                      <div className="space-y-3">
                        {draft.tools.map((tool) => {
                          const meta = catalogByName.get(tool.tool_name);
                          const isSkillTool = tool.tool_name === 'skill';
                          return (
                            <div key={tool.tool_name} className="rounded-[24px] border border-white/85 bg-white/78 p-4">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="flex items-center gap-2">
                                    <p className="text-sm font-black text-slate-900">{meta?.label || tool.tool_name}</p>
                                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-black uppercase text-slate-400">
                                      {tool.tool_name}
                                    </span>
                                  </div>
                                  <p className="mt-1 text-xs font-medium leading-5 text-slate-500">{meta?.description}</p>
                                  {isSkillTool && (
                                    <p className="mt-2 text-xs font-semibold text-amber-700">
                                      绑定任意 Skill 后，会默认开启该工具，并至少要求管理员可控审批。
                                    </p>
                                  )}
                                </div>
                              </div>

                              <div className="mt-4 grid gap-3 md:grid-cols-2">
                                <div className="flex items-center justify-between rounded-2xl border border-white/80 bg-white/72 px-4 py-3">
                                  <span className="text-sm font-black text-slate-700">启用</span>
                                  <Toggle checked={tool.enabled} onClick={() => updateTool(tool.tool_name, { enabled: !tool.enabled })} />
                                </div>
                                <div className="flex items-center justify-between rounded-2xl border border-white/80 bg-white/72 px-4 py-3">
                                  <span className="text-sm font-black text-slate-700">审批</span>
                                  <Toggle
                                    checked={tool.requires_approval}
                                    disabled={!tool.enabled}
                                    onClick={() => updateTool(tool.tool_name, { requires_approval: !tool.requires_approval })}
                                  />
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    <div className="rounded-[28px] border border-white/80 bg-white/82 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                      <div className="mb-4 flex items-center justify-between">
                        <div>
                          <p className="admin-section-kicker">可用 Skill</p>
                          <h4 className="mt-1 text-lg font-black text-slate-900">按智能体选择 Skill</h4>
                        </div>
                        <span className="rounded-full border border-white/80 bg-white px-3 py-1 text-xs font-black text-slate-500">
                          已选 {selectedSkills.length}/{availableSkills.length}
                        </span>
                      </div>

                      {!skillToolEnabled && (
                        <div className="mb-4 rounded-[22px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-bold text-amber-700">
                          选中 Skill 后，系统会自动打开 `skill` 工具，并默认保留审批。
                        </div>
                      )}

                      <div className="space-y-3">
                        {availableSkills.length > 0 ? (
                          availableSkills.map((skill) => {
                            const selected = draft.skill_ids.includes(skill.id);
                            return (
                              <button
                                key={skill.id}
                                type="button"
                                onClick={() => toggleSkill(skill.id)}
                                className={cn(
                                  'w-full rounded-[24px] border p-4 text-left transition-all',
                                  selected
                                    ? 'border-sky-200 bg-sky-50/72 shadow-sm'
                                    : 'border-white/80 bg-white/72 hover:bg-white',
                                )}
                              >
                                <div className="flex items-start justify-between gap-3">
                                  <div className="min-w-0">
                                    <p className="truncate text-sm font-black text-slate-900">{skill.name}</p>
                                    <p className="mt-1 truncate text-[11px] font-black tracking-[0.14em] text-slate-400">
                                      {skill.slug}
                                    </p>
                                  </div>
                                  <span
                                    className={cn(
                                      'rounded-full px-2 py-1 text-[10px] font-black',
                                      selected ? 'bg-sky-100 text-sky-700' : 'bg-white text-slate-500',
                                    )}
                                  >
                                    {selected ? '已选择' : '可选择'}
                                  </span>
                                </div>
                                <p className="mt-3 text-xs font-medium leading-5 text-slate-500">{skill.description || '暂无描述'}</p>
                                {skill.has_python_scripts && (
                                  <div className="mt-3">
                                    <span className="rounded-full border border-amber-100 bg-amber-50 px-2.5 py-1 text-[10px] font-black text-amber-700">
                                      含 Python 脚本
                                    </span>
                                  </div>
                                )}
                              </button>
                            );
                          })
                        ) : (
                          <div className="rounded-[24px] border border-dashed border-slate-200 bg-white/60 px-4 py-5 text-sm font-medium text-slate-500">
                            还没有可绑定的 Skill，请先去 Skill 管理页创建或上传。
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-100 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm font-medium text-slate-500">保存后将更新当前智能体配置。</p>
                <div className="flex items-center gap-3">
                  <Button type="button" variant="secondary" onClick={closeModal} disabled={isSaving}>
                    取消
                  </Button>
                  <Button type="button" onClick={saveDraft} disabled={isSaving} className="gap-2">
                    {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    保存配置
                  </Button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
