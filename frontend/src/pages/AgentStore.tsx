import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowLeft, Bot, Check, Loader2, Plus, RefreshCw, Sparkles, X } from 'lucide-react';
import { Logo } from '../components/Logo';
import { Button } from '../components/ui/Button';
import { RandomMascot } from '../components/ui/RandomMascot';
import { AgentProfile, getAgentStore, installAgent, uninstallAgent } from '../services/agentProfileService';
import { cn } from '../lib/utils';

const agentAccent = [
  'from-cyan-400 to-sky-500',
  'from-emerald-400 to-teal-500',
  'from-amber-300 to-orange-400',
  'from-fuchsia-400 to-rose-500',
  'from-indigo-400 to-blue-500',
  'from-lime-300 to-emerald-500',
];

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
        <RandomMascot size={720} className="absolute -bottom-44 -right-32 text-slate-900 opacity-[0.025]" />
        <div className="absolute bottom-[-20%] left-[-10%] h-[70vw] w-[70vw] rounded-full bg-teal-300 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] h-[80vw] w-[80vw] rounded-full bg-blue-400 opacity-35 mix-blend-overlay blur-[120px]" />
        <div className="absolute left-[30%] top-[10%] h-[50vw] w-[50vw] rounded-full bg-cyan-300 opacity-25 mix-blend-overlay blur-[120px]" />
      </div>

      <nav className="relative z-10 mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-4">
        <Logo />
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={loadStore} disabled={isLoading} size="icon" title="刷新">
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </Button>
          <Button variant="secondary" onClick={() => navigate('/')} className="gap-2">
            <ArrowLeft size={16} />
            返回
          </Button>
        </div>
      </nav>

      <main className="relative z-10 mx-auto w-full max-w-7xl px-5 pb-14 pt-5 md:px-8">
        <div className="mb-7 flex flex-col gap-2">
          <p className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.25em] text-slate-500">
            <Sparkles size={16} />
            Agent Store
          </p>
          <h1 className="text-4xl font-black tracking-tight text-slate-900">智能体商店</h1>
        </div>

        {error && (
          <div className="mb-5 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
            <AlertCircle size={18} />
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="flex h-72 items-center justify-center gap-3 rounded-[28px] border border-white/60 bg-white/45 text-sm font-bold text-slate-500 backdrop-blur-2xl">
            <Loader2 size={18} className="animate-spin" />
            正在加载智能体
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {agents.map((agent, index) => {
              const canUse = agent.installed || agent.is_builtin;
              const accent = agentAccent[index % agentAccent.length];
              return (
                <motion.article
                  key={agent.id}
                  layout
                  whileHover={{ y: -4 }}
                  transition={{ duration: 0.2 }}
                  className="group flex min-h-[190px] flex-col rounded-[24px] border border-white/65 bg-white/62 p-4 shadow-[0_8px_26px_rgba(15,23,42,0.06)] backdrop-blur-2xl"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className={cn('flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br text-white shadow-lg shadow-sky-500/15', accent)}>
                      <Bot size={21} />
                    </div>
                    {canUse && (
                      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-[11px] font-black text-emerald-700">
                        <Check size={12} />
                        可用
                      </span>
                    )}
                  </div>

                  <div className="mt-4 min-h-[86px]">
                    <h2 className="line-clamp-1 text-lg font-black tracking-tight text-slate-900">{agent.name}</h2>
                    <p className="mt-2 line-clamp-3 text-sm font-medium leading-6 text-slate-500">
                      {agent.description || '适合处理特定任务的智能体。'}
                    </p>
                  </div>

                  <div className="mt-auto flex items-center gap-2 pt-4">
                    {canUse ? (
                      <Button onClick={() => startChat(agent)} size="sm" className="flex-1 gap-2">
                        <Sparkles size={15} />
                        对话
                      </Button>
                    ) : (
                      <Button onClick={() => toggleInstall(agent)} disabled={busyId === agent.id} size="sm" className="flex-1 gap-2">
                        {busyId === agent.id ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
                        安装
                      </Button>
                    )}
                    {!agent.is_builtin && agent.installed && (
                      <Button
                        variant="secondary"
                        size="icon"
                        onClick={() => toggleInstall(agent)}
                        disabled={busyId === agent.id}
                        title="卸载"
                        className="h-9 w-9 rounded-xl"
                      >
                        {busyId === agent.id ? <Loader2 size={15} className="animate-spin" /> : <X size={15} />}
                      </Button>
                    )}
                  </div>
                </motion.article>
              );
            })}
          </div>
        )}
      </main>
    </motion.div>
  );
};
