import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { AlertCircle, Calculator, Check, Clock3, Code2, FileText, GitBranch, Globe2, Loader2, PackagePlus, Presentation, Save, ShieldCheck, Sparkles, Terminal, Wrench, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { Card } from '../ui/Card';
import {
  AgentMode,
  AgentModeToolConfig,
  getToolConfig,
  ToolCatalogItem,
  ToolConfigResponse,
  updateModeToolConfig,
} from '../../services/toolConfigService';
import { cn } from '../../lib/utils';

const modeIcons: Record<AgentMode, React.ElementType> = {
  general: Sparkles,
  ppt: Presentation,
  website: Globe2,
};

const toolIcons: Record<string, React.ElementType> = {
  calc: Calculator,
  time: Clock3,
  file: FileText,
  python: Terminal,
  git: GitBranch,
  npm: PackagePlus,
};

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
        checked ? 'justify-end bg-zinc-900' : 'justify-start bg-slate-200',
      )}
    >
      <motion.span layout className="flex h-6 w-6 items-center justify-center rounded-full bg-white shadow-sm">
        {checked ? <Check size={12} className="text-zinc-900" /> : <X size={12} className="text-slate-400" />}
      </motion.span>
    </button>
  );
}

function cloneConfig(data: ToolConfigResponse): ToolConfigResponse {
  return {
    catalog: data.catalog.map((item) => ({ ...item, approval_scope: [...item.approval_scope] })),
    modes: data.modes.map((mode) => ({
      ...mode,
      tools: mode.tools.map((tool) => ({ ...tool })),
    })),
  };
}

export const SystemSettings = () => {
  const [data, setData] = useState<ToolConfigResponse | null>(null);
  const [draft, setDraft] = useState<ToolConfigResponse | null>(null);
  const [activeMode, setActiveMode] = useState<AgentMode>('general');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const catalogByName = useMemo(() => {
    const map = new Map<string, ToolCatalogItem>();
    draft?.catalog.forEach((item) => map.set(item.name, item));
    return map;
  }, [draft]);

  const activeConfig = draft?.modes.find((mode) => mode.mode === activeMode);
  const originalActiveConfig = data?.modes.find((mode) => mode.mode === activeMode);
  const hasChanges = JSON.stringify(activeConfig?.tools ?? []) !== JSON.stringify(originalActiveConfig?.tools ?? []);

  const loadConfig = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getToolConfig();
      setData(response);
      setDraft(cloneConfig(response));
    } catch (err) {
      setError(err instanceof Error ? err.message : '工具配置加载失败');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadConfig();
  }, []);

  const updateTool = (toolName: string, patch: Partial<AgentModeToolConfig>) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        modes: prev.modes.map((mode) => (
          mode.mode === activeMode
            ? {
                ...mode,
                tools: mode.tools.map((tool) => (
                  tool.tool_name === toolName ? { ...tool, ...patch } : tool
                )),
              }
            : mode
        )),
      };
    });
  };

  const handleSave = async () => {
    if (!activeConfig) return;
    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await updateModeToolConfig(activeMode, activeConfig.tools);
      setData(response);
      setDraft(cloneConfig(response));
      setMessage('工具配置已保存，新会话将使用最新策略');
      window.setTimeout(() => setMessage(null), 2600);
    } catch (err) {
      setError(err instanceof Error ? err.message : '工具配置保存失败');
    } finally {
      setIsSaving(false);
    }
  };

  const resetDraft = () => {
    if (data) setDraft(cloneConfig(data));
  };

  const enabledTotal = draft?.modes.reduce((sum, mode) => sum + mode.tools.filter((tool) => tool.enabled).length, 0) ?? 0;
  const approvalTotal = draft?.modes.reduce((sum, mode) => sum + mode.tools.filter((tool) => tool.enabled && tool.requires_approval).length, 0) ?? 0;

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.25em] text-slate-500">Agent Profiles</p>
          <h2 className="mt-2 text-3xl font-black tracking-tight text-slate-900">工具与审批管理</h2>
          <p className="mt-2 max-w-2xl text-sm font-medium leading-6 text-slate-500">
            每个前台模式都是一套独立 Agent 配置，可分别控制工具启用和人工审批策略。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {message && (
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-700">
              {message}
            </div>
          )}
          <Button variant="secondary" onClick={loadConfig} disabled={isLoading || isSaving} className="gap-2 self-start md:self-auto">
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Wrench size={16} />}
            重新加载
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          { label: 'Agent 模式', value: draft?.modes.length ?? 0, icon: Sparkles, tone: 'bg-sky-50 text-sky-700 border-sky-100' },
          { label: '已启用工具', value: enabledTotal, icon: Wrench, tone: 'bg-emerald-50 text-emerald-700 border-emerald-100' },
          { label: '审批保护', value: approvalTotal, icon: ShieldCheck, tone: 'bg-amber-50 text-amber-700 border-amber-100' },
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
          正在加载工具配置
        </div>
      ) : draft ? (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {draft.modes.map((mode) => {
              const Icon = modeIcons[mode.mode];
              const enabledCount = mode.tools.filter((tool) => tool.enabled).length;
              return (
                <button
                  key={mode.mode}
                  type="button"
                  onClick={() => setActiveMode(mode.mode)}
                  className={cn(
                    'rounded-[24px] border p-5 text-left transition-all',
                    activeMode === mode.mode
                      ? 'border-white/80 bg-white/80 shadow-md'
                      : 'border-white/50 bg-white/45 hover:bg-white/65',
                  )}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/70 bg-white/70 text-slate-800 shadow-sm">
                      <Icon size={21} />
                    </div>
                    <span className="rounded-full border border-slate-200 bg-white/70 px-3 py-1 text-xs font-black text-slate-500">
                      {enabledCount}/{mode.tools.length} 启用
                    </span>
                  </div>
                  <h3 className="mt-4 text-lg font-black text-slate-900">{mode.label}</h3>
                  <p className="mt-1 text-sm font-medium leading-6 text-slate-500">{mode.description}</p>
                </button>
              );
            })}
          </div>

          <Card className="overflow-hidden p-0">
            <div className="flex flex-col gap-4 border-b border-white/70 p-5 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.22em] text-slate-400">Current Profile</p>
                <h3 className="mt-1 text-2xl font-black tracking-tight text-slate-900">{activeConfig?.label}</h3>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button variant="secondary" onClick={resetDraft} disabled={!hasChanges || isSaving}>
                  还原
                </Button>
                <Button onClick={handleSave} disabled={!hasChanges || isSaving} className="gap-2">
                  {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                  保存配置
                </Button>
              </div>
            </div>

            <div className="divide-y divide-slate-100/80">
              {activeConfig?.tools.map((tool) => {
                const catalog = catalogByName.get(tool.tool_name);
                const Icon = toolIcons[tool.tool_name] || Code2;
                return (
                  <div key={tool.tool_name} className="grid grid-cols-1 gap-5 p-5 lg:grid-cols-[minmax(260px,1fr)_160px_180px] lg:items-center">
                    <div className="flex min-w-0 items-start gap-4">
                      <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-2xl border border-white/70 bg-white/70 text-slate-800 shadow-sm">
                        <Icon size={22} />
                      </div>
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h4 className="text-base font-black text-slate-900">{catalog?.label || tool.tool_name}</h4>
                          <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-black uppercase text-slate-400">
                            {tool.tool_name}
                          </span>
                        </div>
                        <p className="mt-1 text-sm font-medium leading-6 text-slate-500">{catalog?.description}</p>
                        {tool.requires_approval && (
                          <p className="mt-2 flex items-center gap-1.5 text-xs font-bold text-amber-600">
                            <ShieldCheck size={14} />
                            审批覆盖：{catalog?.approval_scope.join('、')}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-white/55 px-4 py-3">
                      <span className="text-sm font-black text-slate-700">启用工具</span>
                      <Toggle
                        checked={tool.enabled}
                        onClick={() => updateTool(tool.tool_name, { enabled: !tool.enabled })}
                      />
                    </div>

                    <div className="flex items-center justify-between rounded-2xl border border-slate-100 bg-white/55 px-4 py-3">
                      <span className="text-sm font-black text-slate-700">需要审批</span>
                      <Toggle
                        checked={tool.requires_approval}
                        disabled={!tool.enabled}
                        onClick={() => updateTool(tool.tool_name, { requires_approval: !tool.requires_approval })}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
};
