import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Bot, Check, Loader2, Plus, Save, ShieldCheck, Sparkles, Trash2, Wrench, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import { cn } from '../../lib/utils';
import {
  AgentProfile,
  AgentProfilePayload,
  AgentProfileTool,
  createAgentProfile,
  deleteAgentProfile,
  getAgentProfiles,
  updateAgentProfile,
} from '../../services/agentProfileService';
import { AgentMode, ToolCatalogItem } from '../../services/toolConfigService';

type Draft = AgentProfilePayload & { id?: number; is_builtin?: boolean };

const emptyPrompt = '你是一个专注于特定任务的 AgenticOS 智能体。请根据用户目标主动拆解任务，必要时调用可用工具，并给出清晰可执行的结果。';

function Toggle({ checked, disabled, onClick }: { checked: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex h-8 w-14 items-center rounded-full p-1 transition-all disabled:cursor-not-allowed disabled:opacity-50',
        checked ? 'justify-end bg-zinc-900' : 'justify-start bg-slate-200',
      )}
    >
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-sm">
        {checked ? <Check size={12} className="text-zinc-900" /> : <X size={12} className="text-slate-400" />}
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
  };
}

export const AgentManagement = () => {
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);
  const [catalog, setCatalog] = useState<ToolCatalogItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | 'new' | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selectedProfile = useMemo(() => profiles.find((item) => item.id === selectedId) || null, [profiles, selectedId]);
  const catalogByName = useMemo(() => new Map(catalog.map((item) => [item.name, item])), [catalog]);
  const enabledAgents = profiles.filter((profile) => profile.enabled).length;
  const listedAgents = profiles.filter((profile) => profile.listed).length;
  const enabledTools = draft?.tools.filter((tool) => tool.enabled).length ?? 0;

  const loadProfiles = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAgentProfiles();
      setProfiles(response.items);
      setCatalog(response.catalog);
      const first = selectedId && selectedId !== 'new'
        ? response.items.find((item) => item.id === selectedId)
        : response.items[0];
      setSelectedId(first?.id ?? null);
      setDraft(first ? makeDraft(first, response.catalog) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '智能体配置加载失败');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  const selectProfile = (profile: AgentProfile) => {
    setSelectedId(profile.id);
    setDraft(makeDraft(profile, catalog));
    setMessage(null);
    setError(null);
  };

  const startCreate = () => {
    setSelectedId('new');
    setDraft(makeDraft(null, catalog));
    setMessage(null);
    setError(null);
  };

  const patchDraft = (patch: Partial<Draft>) => {
    setDraft((prev) => prev ? { ...prev, ...patch } : prev);
  };

  const updateTool = (toolName: string, patch: Partial<AgentProfileTool>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        tools: prev.tools.map((tool) => tool.tool_name === toolName ? { ...tool, ...patch } : tool),
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
      };
      const saved = draft.id
        ? await updateAgentProfile(draft.id, payload)
        : await createAgentProfile(payload);
      setProfiles((prev) => draft.id ? prev.map((item) => item.id === saved.id ? saved : item) : [...prev, saved]);
      setSelectedId(saved.id);
      setDraft(makeDraft(saved, catalog));
      setMessage('智能体配置已保存');
      window.setTimeout(() => setMessage(null), 2200);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  const removeProfile = async () => {
    if (!draft?.id || draft.is_builtin) return;
    setIsSaving(true);
    setError(null);
    try {
      await deleteAgentProfile(draft.id);
      const nextProfiles = profiles.filter((item) => item.id !== draft.id);
      setProfiles(nextProfiles);
      const next = nextProfiles[0] ?? null;
      setSelectedId(next?.id ?? null);
      setDraft(next ? makeDraft(next, catalog) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.25em] text-slate-500">Agent Profiles</p>
          <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-900">智能体配置</h2>
          <p className="mt-2 max-w-2xl text-sm font-medium leading-6 text-slate-500">
            每个智能体都有独立 prompt、响应模式、工具启用和审批策略，上架后会出现在智能体商店。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {message && <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-700">{message}</div>}
          <Button variant="secondary" onClick={loadProfiles} disabled={isLoading || isSaving} className="gap-2">
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Wrench size={16} />}
            重新加载
          </Button>
          <Button onClick={startCreate} disabled={isLoading || isSaving} className="gap-2">
            <Plus size={16} />
            新建智能体
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { label: '智能体', value: profiles.length, icon: Bot, tone: 'bg-sky-50 text-sky-700 border-sky-100' },
          { label: '已启用', value: enabledAgents, icon: Sparkles, tone: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
          { label: '已上架', value: listedAgents, icon: ShieldCheck, tone: 'bg-amber-50 text-amber-700 border-amber-100' },
        ].map((item) => (
          <Card key={item.label} className="p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-widest text-slate-400">{item.label}</p>
                <p className="mt-2 text-3xl font-black tracking-tight text-slate-900">{item.value}</p>
              </div>
              <div className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${item.tone}`}>
                <item.icon size={21} />
              </div>
            </div>
          </Card>
        ))}
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      {isLoading && !draft ? (
        <div className="flex h-80 items-center justify-center gap-3 rounded-[28px] border border-white/60 bg-white/45 text-sm font-bold text-slate-500 backdrop-blur-2xl">
          <Loader2 size={18} className="animate-spin" />
          正在加载智能体配置
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[360px_minmax(0,1fr)]">
          <Card className="overflow-hidden p-0">
            <div className="border-b border-white/70 p-5">
              <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Profiles</p>
              <h3 className="mt-1 text-xl font-black tracking-tight text-slate-900">配置列表</h3>
            </div>
            <div className="max-h-[720px] space-y-2 overflow-y-auto p-3">
              {profiles.map((profile) => (
                <button
                  key={profile.id}
                  type="button"
                  onClick={() => selectProfile(profile)}
                  className={cn(
                    'w-full rounded-2xl border p-4 text-left transition-all',
                    selectedId === profile.id ? 'border-white/80 bg-white/85 shadow-sm' : 'border-white/40 bg-white/35 hover:bg-white/60',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-black text-slate-900">{profile.name}</p>
                      <p className="mt-1 truncate text-xs font-bold text-slate-400">{profile.slug}</p>
                    </div>
                    <span className={cn('rounded-full px-2 py-1 text-[10px] font-black', profile.listed ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500')}>
                      {profile.listed ? '上架' : '未上架'}
                    </span>
                  </div>
                  <p className="mt-3 line-clamp-2 text-xs font-medium leading-5 text-slate-500">{profile.description || '暂无描述'}</p>
                </button>
              ))}
            </div>
          </Card>

          {draft && (
            <Card className="overflow-hidden p-0">
              <div className="flex flex-col gap-4 border-b border-white/70 p-5 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Current Agent</p>
                  <h3 className="mt-1 text-2xl font-black tracking-tight text-slate-900">{draft.name || '新的智能体'}</h3>
                </div>
                <div className="flex flex-wrap gap-3">
                  {draft.id && !draft.is_builtin && (
                    <Button variant="danger" onClick={removeProfile} disabled={isSaving} className="gap-2">
                      <Trash2 size={16} />
                      删除
                    </Button>
                  )}
                  <Button onClick={saveDraft} disabled={isSaving} className="gap-2">
                    {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                    保存配置
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400">名称</span>
                  <input value={draft.name} onChange={(e) => patchDraft({ name: e.target.value })} className="w-full rounded-2xl border border-white/70 bg-white/65 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:border-sky-300" />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400">Slug</span>
                  <input value={draft.slug || ''} disabled={draft.is_builtin} onChange={(e) => patchDraft({ slug: e.target.value })} className="w-full rounded-2xl border border-white/70 bg-white/65 px-4 py-3 text-sm font-bold text-slate-800 outline-none disabled:opacity-60 focus:border-sky-300" />
                </label>
                <label className="space-y-2 lg:col-span-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400">描述</span>
                  <input value={draft.description} onChange={(e) => patchDraft({ description: e.target.value })} className="w-full rounded-2xl border border-white/70 bg-white/65 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:border-sky-300" />
                </label>
                <label className="space-y-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400">响应模式</span>
                  <select value={draft.response_mode} onChange={(e) => patchDraft({ response_mode: e.target.value as AgentMode })} className="w-full rounded-2xl border border-white/70 bg-white/65 px-4 py-3 text-sm font-bold text-slate-800 outline-none focus:border-sky-300">
                    <option value="general">general</option>
                    <option value="ppt">ppt</option>
                    <option value="website">website</option>
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex items-center justify-between rounded-2xl border border-white/70 bg-white/55 px-4 py-3">
                    <span className="text-sm font-black text-slate-700">启用</span>
                    <Toggle checked={draft.enabled} onClick={() => patchDraft({ enabled: !draft.enabled })} />
                  </div>
                  <div className="flex items-center justify-between rounded-2xl border border-white/70 bg-white/55 px-4 py-3">
                    <span className="text-sm font-black text-slate-700">上架</span>
                    <Toggle checked={draft.listed} onClick={() => patchDraft({ listed: !draft.listed })} />
                  </div>
                </div>
                <label className="space-y-2 lg:col-span-2">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400">Prompt</span>
                  <textarea value={draft.system_prompt} onChange={(e) => patchDraft({ system_prompt: e.target.value })} rows={8} className="w-full resize-y rounded-2xl border border-white/70 bg-white/65 px-4 py-3 text-sm font-medium leading-6 text-slate-800 outline-none focus:border-sky-300" />
                </label>
              </div>

              <div className="border-t border-white/70 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Tools</p>
                    <h4 className="mt-1 text-xl font-black text-slate-900">工具配置</h4>
                  </div>
                  <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-black text-slate-500">{enabledTools}/{draft.tools.length} 启用</span>
                </div>
                <div className="divide-y divide-slate-100/80 overflow-hidden rounded-2xl border border-white/70 bg-white/40">
                  {draft.tools.map((tool) => {
                    const meta = catalogByName.get(tool.tool_name);
                    return (
                      <div key={tool.tool_name} className="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(260px,1fr)_150px_170px] lg:items-center">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="text-sm font-black text-slate-900">{meta?.label || tool.tool_name}</p>
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-black uppercase text-slate-400">{tool.tool_name}</span>
                          </div>
                          <p className="mt-1 text-xs font-medium leading-5 text-slate-500">{meta?.description}</p>
                        </div>
                        <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-white/60 px-4 py-3">
                          <span className="text-sm font-black text-slate-700">启用</span>
                          <Toggle checked={tool.enabled} onClick={() => updateTool(tool.tool_name, { enabled: !tool.enabled })} />
                        </div>
                        <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-white/60 px-4 py-3">
                          <span className="text-sm font-black text-slate-700">审批</span>
                          <Toggle checked={tool.requires_approval} disabled={!tool.enabled} onClick={() => updateTool(tool.tool_name, { requires_approval: !tool.requires_approval })} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};
