import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowLeft, Check, Loader2, Plus, Sparkles, Store, X } from 'lucide-react';
import { Logo } from '../components/Logo';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { RandomMascot } from '../components/ui/RandomMascot';
import { AgentProfile, getAgentStore, installAgent, uninstallAgent } from '../services/agentProfileService';
import { cn } from '../lib/utils';

export const AgentStore = () => {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadStore = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAgentStore();
      setAgents(response.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : '智能体商店加载失败');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStore();
  }, []);

  const toggleInstall = async (agent: AgentProfile) => {
    if (agent.is_builtin) return;
    setBusyId(agent.id);
    setError(null);
    try {
      if (agent.installed) {
        await uninstallAgent(agent.id);
        setAgents((prev) => prev.map((item) => item.id === agent.id ? { ...item, installed: false } : item));
      } else {
        const updated = await installAgent(agent.id);
        setAgents((prev) => prev.map((item) => item.id === agent.id ? updated : item));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '安装状态更新失败');
    } finally {
      setBusyId(null);
    }
  };

  const startChat = (agent: AgentProfile) => {
    navigate('/chat', {
      state: {
        mode: agent.response_mode,
        agentProfileId: agent.id,
      },
    });
  };

  return (
    <motion.div
      key="agent-store"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="relative min-h-screen overflow-hidden bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] font-sans text-slate-800 selection:bg-zinc-200 selection:text-zinc-900"
    >
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <RandomMascot size={760} className="absolute -bottom-44 -right-36 text-slate-900 opacity-[0.025]" />
        <div className="absolute bottom-[-20%] left-[-10%] h-[70vw] w-[70vw] rounded-full bg-teal-300 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] h-[80vw] w-[80vw] rounded-full bg-blue-400 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute left-[30%] top-[10%] h-[50vw] w-[50vw] rounded-full bg-cyan-300 opacity-25 mix-blend-overlay blur-[120px]" />
      </div>

      <nav className="relative z-10 mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-4">
        <Logo />
        <Button variant="secondary" onClick={() => navigate('/')} className="gap-2">
          <ArrowLeft size={16} />
          返回首页
        </Button>
      </nav>

      <main className="relative z-10 mx-auto w-full max-w-7xl px-5 pb-14 pt-6 md:px-8">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.25em] text-slate-500">
              <Store size={16} />
              Agent Store
            </p>
            <h1 className="mt-3 text-4xl font-black tracking-tight text-slate-900">智能体商店</h1>
            <p className="mt-2 max-w-2xl text-sm font-medium leading-6 text-slate-600">
              安装管理员上架的智能体，聊天时可直接切换到对应 prompt 与工具组合。
            </p>
          </div>
          <Button variant="secondary" onClick={loadStore} disabled={isLoading} className="gap-2 self-start md:self-auto">
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />}
            刷新
          </Button>
        </div>

        {error && (
          <div className="mb-5 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex h-80 items-center justify-center gap-3 rounded-[28px] border border-white/60 bg-white/45 text-sm font-bold text-slate-500 backdrop-blur-2xl">
            <Loader2 size={18} className="animate-spin" />
            正在加载智能体
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {agents.map((agent) => {
              const toolCount = agent.tools.filter((tool) => tool.enabled).length;
              const approvalCount = agent.tools.filter((tool) => tool.enabled && tool.requires_approval).length;
              return (
                <Card key={agent.id} className="flex min-h-[260px] flex-col p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/70 bg-white/75 text-zinc-900 shadow-sm">
                      <Sparkles size={22} />
                    </div>
                    <span className={cn(
                      'rounded-full border px-3 py-1 text-xs font-black',
                      agent.installed ? 'border-emerald-100 bg-emerald-50 text-emerald-700' : 'border-slate-200 bg-white/70 text-slate-500',
                    )}>
                      {agent.installed ? '已可用' : '未安装'}
                    </span>
                  </div>

                  <h2 className="mt-5 text-xl font-black tracking-tight text-slate-900">{agent.name}</h2>
                  <p className="mt-2 line-clamp-3 min-h-[72px] text-sm font-medium leading-6 text-slate-500">{agent.description || '暂无描述'}</p>

                  <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-2xl border border-white/70 bg-white/55 px-3 py-2">
                      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">模式</p>
                      <p className="mt-1 text-sm font-black text-slate-800">{agent.response_mode}</p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/55 px-3 py-2">
                      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">工具</p>
                      <p className="mt-1 text-sm font-black text-slate-800">{toolCount}</p>
                    </div>
                    <div className="rounded-2xl border border-white/70 bg-white/55 px-3 py-2">
                      <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">审批</p>
                      <p className="mt-1 text-sm font-black text-slate-800">{approvalCount}</p>
                    </div>
                  </div>

                  <div className="mt-auto flex gap-3 pt-5">
                    <Button onClick={() => startChat(agent)} disabled={!agent.installed && !agent.is_builtin} className="flex-1 gap-2">
                      <Sparkles size={16} />
                      开始对话
                    </Button>
                    {!agent.is_builtin && (
                      <Button variant="secondary" onClick={() => toggleInstall(agent)} disabled={busyId === agent.id} className="gap-2">
                        {busyId === agent.id ? <Loader2 size={16} className="animate-spin" /> : agent.installed ? <X size={16} /> : <Plus size={16} />}
                        {agent.installed ? '卸载' : '安装'}
                      </Button>
                    )}
                    {agent.is_builtin && (
                      <Button variant="secondary" disabled className="gap-2">
                        <Check size={16} />
                        内置
                      </Button>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </main>
    </motion.div>
  );
};
