import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, Bot, Check, Loader2, Plus, RefreshCw, Search, SearchX, Settings, Sparkles, X } from 'lucide-react';
import { Logo } from '../components/Logo';
import { Button } from '../components/shadcn/button';
import { Badge } from '../components/ui/Badge';
import { EmptyState } from '../components/ui/EmptyState';
import { CardSkeleton } from '../components/ui/Skeletons';
import { MascotGeneral, MascotPPT, MascotWebsite, MascotBigData } from '../components/ui/MascotIcons';
import { AgentProfile, getAgentStore, installAgent, uninstallAgent } from '../services/agentProfileService';
import { cn } from '../lib/utils';
import { toast } from 'sonner';
import { toastError } from '../lib/errors';
import { PageHeader } from '../components/ui/PageShell';

// 模式 → 小精灵 + 颜色
const MODE_CARD_STYLES: Record<string, { Mascot: React.FC<{ size?: number; className?: string }>; gradient: string; shadow: string }> = {
  general: { Mascot: MascotGeneral, gradient: 'from-cyan-400 to-sky-500',    shadow: 'shadow-sky-500/15' },
  ppt:     { Mascot: MascotPPT,     gradient: 'from-violet-400 to-purple-500', shadow: 'shadow-violet-500/15' },
  website: { Mascot: MascotWebsite, gradient: 'from-emerald-400 to-teal-500',  shadow: 'shadow-emerald-500/15' },
  bigdata: { Mascot: MascotBigData, gradient: 'from-orange-400 to-amber-500',  shadow: 'shadow-orange-500/15' },
};

function getCardStyle(mode?: string) {
  return MODE_CARD_STYLES[mode || ''] || MODE_CARD_STYLES.general;
}

export const AgentStore = () => {
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredAgents = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return agents;
    return agents.filter((a) =>
      a.name.toLowerCase().includes(q) ||
      (a.description || '').toLowerCase().includes(q) ||
      a.slug.toLowerCase().includes(q),
    );
  }, [agents, searchQuery]);

  const loadStore = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await getAgentStore();
      setAgents(response.items);
    } catch (err) {
      setError(toastError(err, '智能体商店加载失败'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStore();
  }, []);

  const toggleInstall = async (agent: AgentProfile) => {
    // 内置智能体是平台自带能力，不需要安装/卸载；直接 return 会让按钮点击
    // 毫无反馈，这里给出明确提示。
    if (agent.is_builtin) {
      toast.info(`「${agent.name}」是内置智能体，无需安装`);
      return;
    }
    setBusyId(agent.id);
    setError(null);
    try {
      if (agent.installed) {
        await uninstallAgent(agent.id);
        setAgents((prev) => prev.map((item) => item.id === agent.id ? { ...item, installed: false } : item));
        toast.success(`已卸载「${agent.name}」`);
      } else {
        const updated = await installAgent(agent.id);
        setAgents((prev) => prev.map((item) => item.id === agent.id ? updated : item));
        toast.success(`已安装「${agent.name}」`);
      }
    } catch (err) {
      setError(toastError(err, '安装状态更新失败'));
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
      /* 挂载即可见：整页可见性不依赖 motion 入场（防懒加载竞态白屏） */
      initial={false}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'relative min-h-screen overflow-hidden font-sans',
        'text-[var(--foreground)] bg-[var(--surface-0)] selection:bg-[var(--border-medium)] selection:text-[var(--foreground)]'
      )}
    >
      <nav className="relative z-10 mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-4">
        <Logo />
        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={loadStore} disabled={isLoading} size="icon" title="刷新">
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </Button>
          <Button onClick={() => navigate('/agents/new')} className="gap-2">
            <Plus size={16} />
            创建智能体
          </Button>
        </div>
      </nav>

      <main id="main-content" className="relative z-10 mx-auto w-full max-w-7xl px-5 pb-14 pt-5 md:px-8">
        <div className="mb-7">
          <PageHeader
            kicker="AGENT STORE"
            title="智能体商店"
            description="安装同事分享的助手，或创建只属于你的智能体并为它挑选工具"
            back
          />
        </div>

        {/* 搜索：智能体数量增长后避免整页长滚动查找 */}
        <div className="mb-5 flex items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]" aria-hidden="true" />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索智能体名称或介绍..."
              aria-label="搜索智能体"
              className="admin-input h-11 pl-10"
            />
          </div>
          {searchQuery && (
            <span className="text-xs font-medium text-[var(--muted-foreground)]">
              {filteredAgents.length} 个结果
            </span>
          )}
        </div>

        {error && (
          <div className="mb-5 flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300">
            <AlertCircle size={18} className="shrink-0" />
            <span className="min-w-0 flex-1 break-words">{error}</span>
            <button
              type="button"
              onClick={loadStore}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-red-700 transition-colors hover:bg-red-100 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)] dark:text-red-200 dark:hover:bg-red-500/20"
            >
              <RefreshCw size={13} />
              重试
            </button>
          </div>
        )}

        {isLoading ? (
          <CardSkeleton count={8} />
        ) : agents.length === 0 ? (
          <div className={cn(
            'rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] backdrop-blur-2xl'
          )}>
            <EmptyState
              icon={<Bot className="size-5" />}
              title="还没有可用的智能体"
              description="智能体商店里还没有任何助手。你可以自己创建一个，或请管理员在后台配置后发布。"
              action={{ label: '创建智能体', onClick: () => navigate('/agents/new') }}
            />
          </div>
        ) : filteredAgents.length === 0 ? (
          <div className={cn(
            'rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-1)] backdrop-blur-2xl'
          )}>
            <EmptyState
              icon={<SearchX className="size-5" />}
              title={`没有匹配「${searchQuery}」的智能体`}
              description="换个关键词试试，或者清空搜索条件查看全部智能体。"
              action={{ label: '清除搜索条件', onClick: () => setSearchQuery('') }}
            />
          </div>
        ) : (
          // 不做入场 stagger：卡片初始不可见会让 e2e 的可见性计数（getByRole.count）
          // 在动画完成前数到 0；入场生命交给骨架屏，卡片只保留 hover 反馈
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredAgents.map((agent) => {
              const canUse = agent.installed;
              const cardContent = (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <div className={cn('flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br text-white shadow-lg transition-transform duration-300 group-hover:scale-110', getCardStyle(agent.response_mode).gradient, getCardStyle(agent.response_mode).shadow)}>
                      {(() => { const M = getCardStyle(agent.response_mode).Mascot; return <M size={28} className="text-white" />; })()}
                    </div>
                    {agent.is_owner ? (
                      <Badge variant="info" size="md">
                        <Sparkles size={12} />
                        我创建的
                      </Badge>
                    ) : canUse ? (
                      <Badge variant="success" size="md">
                        <Check size={12} />
                        可用
                      </Badge>
                    ) : null}
                  </div>

                  <div className="mt-4 min-h-[86px]">
                    <h2 className={cn("line-clamp-1 text-lg font-bold tracking-tight", "text-[var(--foreground)]")}>{agent.name}</h2>
                    <p className={cn("mt-2 line-clamp-3 text-sm font-medium leading-6", "text-[var(--muted-foreground)]")}>
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
                    {agent.is_owner ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/agents/${agent.id}/edit`)}
                        className="gap-1.5"
                      >
                        <Settings size={14} />
                        编辑
                      </Button>
                    ) : agent.installed && !agent.is_builtin ? (
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={() => toggleInstall(agent)}
                        disabled={busyId === agent.id}
                        title="卸载"
                        className="h-9 w-9 rounded-xl"
                      >
                        {busyId === agent.id ? <Loader2 size={15} className="animate-spin" /> : <X size={15} />}
                      </Button>
                    ) : null}
                  </div>
                </>
              );
              return (
                <motion.article
                  key={agent.id}
                  layout
                  whileHover={{ y: -4 }}
                  transition={{ duration: 0.2 }}
                  className={cn(
                    'group flex min-h-[190px] flex-col rounded-2xl',
                    'border border-[var(--border-subtle)] bg-[var(--surface-1)] shadow-md p-4',
                    'transition-[border-color,box-shadow] duration-200',
                    'hover:border-[var(--border-strong)] hover:shadow-lg'
                  )}
                >
                  <div className="flex flex-col flex-1">
                    {cardContent}
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
