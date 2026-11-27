import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import {
  AlertCircle,
  Bot,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  SearchX,
} from 'lucide-react';
import { EmptyState } from '../components/ui/EmptyState';
import { getAgentIcon } from '../components/ui/AgentIcon';
import { CardSkeleton } from '../components/ui/Skeletons';
import { AgentProfile, getAgentStore, installAgent, uninstallAgent } from '../services/agentProfileService';
import { cn } from '../lib/utils';
import { toast } from 'sonner';
import { toastError } from '../lib/errors';

function getAgentBadgeVisual(avatar?: string | null, mode?: string, slug?: string): {
  tone: string;
  Icon: React.ComponentType<{ size?: number; className?: string }>;
  roleTag: string;
} {
  // 全站统一按 avatar 取图标；avatar 为空时按 slug/mode 兜底成内置 avatar key
  const key = (avatar || slug || mode || 'general').toLowerCase();
  const mapped = key.includes('ppt') ? 'presentation'
    : key.includes('web') ? 'globe'
    : key.includes('office') || key.includes('sheet') ? 'table'
    : key.includes('mail') ? 'mail'
    : key.includes('data') ? 'database' : key;
  const { Icon, tone } = getAgentIcon(mapped);
  return { tone, Icon, roleTag: mode || 'general' };
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
    return agents.filter(
      (a) =>
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
      setError(toastError(err, '智能体广场加载失败'));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadStore();
  }, []);

  const toggleInstall = async (agent: AgentProfile) => {
    if (agent.is_builtin) {
      toast.info(`「${agent.name}」是内置智能体，无需安装`);
      return;
    }
    setBusyId(agent.id);
    setError(null);
    try {
      if (agent.installed) {
        await uninstallAgent(agent.id);
        setAgents((prev) => prev.map((item) => (item.id === agent.id ? { ...item, installed: false } : item)));
        toast.success(`已卸载「${agent.name}」`);
      } else {
        const updated = await installAgent(agent.id);
        setAgents((prev) => prev.map((item) => (item.id === agent.id ? updated : item)));
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
      initial={false}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="relative h-full w-full overflow-y-auto px-1 pb-14 font-sans text-[var(--foreground)] sm:px-3"
    >
      <main id="main-content" className="mx-auto w-full max-w-[1140px] px-1 sm:px-4">
        {/* 原版原型同款暖橙+天蓝渐层英雄横幅 */}
        <div className="aos-hero-banner mb-6 mt-1 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[var(--border-subtle)] p-6">
          <div className="flex items-center gap-3.5">
            <span className="aos-icon-badge aos-tone-amber h-11 w-11 !rounded-2xl">
              <Bot size={20} />
            </span>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-[var(--foreground)] sm:text-2xl">
                AI 智能体广场
              </h1>
              <p className="mt-0.5 text-xs text-[var(--muted-foreground)] sm:text-sm">
                智能体不是简单的小工具，它能理解你的意图、记住上下文，还能调用工具帮你把事办成。选一个直接用，或自己做一个
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search
                size={14}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
              />
              <input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索智能体..."
                aria-label="搜索智能体"
                className="aos-glass-surface w-44 rounded-full py-1.5 pl-8 pr-3 text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] focus:border-[var(--border-strong)] sm:w-52"
              />
            </div>
            <button
              type="button"
              onClick={() => void loadStore()}
              disabled={isLoading}
              title="刷新"
              className="aos-pill-btn !p-2"
            >
              {isLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            </button>
            <button
              type="button"
              onClick={() => navigate('/agents/new')}
              className="aos-cta-pill"
            >
              <Plus size={15} />
              <span>创建自定义智能体</span>
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-5 flex items-center gap-2 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300">
            <AlertCircle size={18} className="shrink-0" />
            <span className="min-w-0 flex-1 break-words">{error}</span>
            <button type="button" onClick={() => void loadStore()} className="aos-pill-btn !py-1 !px-2.5">
              重试
            </button>
          </div>
        )}

        {isLoading ? (
          <CardSkeleton count={6} />
        ) : agents.length === 0 ? (
          <div className="aos-glass-surface rounded-2xl">
            <EmptyState
              icon={<Bot className="size-5" />}
              title="还没有可用的智能体"
              description="智能体广场里还没有任何助手。你可以自己创建一个，或请管理员在后台配置后发布。"
              action={{ label: '创建自定义智能体', onClick: () => navigate('/agents/new') }}
            />
          </div>
        ) : filteredAgents.length === 0 ? (
          <div className="aos-glass-surface rounded-2xl">
            <EmptyState
              icon={<SearchX className="size-5" />}
              title={`没有匹配「${searchQuery}」的智能体`}
              description="换个关键词试试，或者清空搜索条件查看全部智能体。"
              action={{ label: '清除搜索条件', onClick: () => setSearchQuery('') }}
            />
          </div>
        ) : (
          /* 原型同款 3 列卡片网格 */
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {filteredAgents.map((agent) => {
              const { tone, Icon, roleTag } = getAgentBadgeVisual(agent.avatar, agent.response_mode, agent.slug);
              const canUse = agent.installed || agent.is_builtin;
              return (
                <article
                  key={agent.id}
                  className="aos-glass-surface aos-surface-interactive flex flex-col justify-between gap-4 rounded-2xl p-5"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <span className={cn('aos-icon-badge h-11 w-11 !rounded-2xl', tone)}>
                        <Icon size={20} />
                      </span>
                      <span className="rounded-full bg-[var(--surface-2)] px-2.5 py-0.5 font-mono text-[11px] text-[var(--muted-foreground)]">
                        {roleTag}
                      </span>
                    </div>
                    <h2 className="mt-3.5 line-clamp-1 text-[15.5px] font-semibold text-[var(--foreground)]">
                      {agent.name}
                    </h2>
                    <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-[var(--muted-foreground)]">
                      {agent.description || '按作用域与工具策略统一管理的专属智能体。'}
                    </p>
                  </div>

                  <div className="flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] pt-3">
                    <div className="truncate text-[11px] text-[var(--muted-foreground)]">
                      {agent.is_builtin ? '内置 · 全员可用' : agent.is_owner ? '自定义 · 我创建' : canUse ? '已安装 · 可用' : '未安装'}
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {agent.is_owner ? (
                        <button
                          type="button"
                          onClick={() => navigate(`/agents/${agent.id}/edit`)}
                          className="aos-pill-btn !py-1 !px-2.5 !text-[11.5px]"
                        >
                          配置
                        </button>
                      ) : agent.installed && !agent.is_builtin ? (
                        <button
                          type="button"
                          onClick={() => void toggleInstall(agent)}
                          disabled={busyId === agent.id}
                          className="aos-pill-btn !py-1 !px-2.5 !text-[11.5px]"
                        >
                          {busyId === agent.id ? '处理中' : '卸载'}
                        </button>
                      ) : null}

                      {canUse ? (
                        <button
                          type="button"
                          onClick={() => startChat(agent)}
                          className="aos-cta-pill !py-1 !px-3 !text-[11.5px]"
                        >
                          对话
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void toggleInstall(agent)}
                          disabled={busyId === agent.id}
                          className="aos-cta-pill !py-1 !px-3 !text-[11.5px]"
                        >
                          {busyId === agent.id ? <Loader2 size={12} className="animate-spin" /> : '安装'}
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </main>
    </motion.div>
  );
};
