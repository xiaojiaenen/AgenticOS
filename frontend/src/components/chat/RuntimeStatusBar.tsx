import React from 'react';
import { motion } from 'motion/react';
import { BrainCircuit, Database, Radio, ShieldCheck, Timer } from 'lucide-react';
import { Session } from '../../types';
import { cn } from '../../lib/utils';

type RuntimeStatusBarProps = {
  session?: Session;
  isLoading: boolean;
  runStatus?: {
    phase: 'idle' | 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'done' | 'error';
    label: string;
  };
};

const Metric = ({
  icon,
  label,
  value,
  active = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  active?: boolean;
}) => (
  <div
    className={cn(
      'flex min-w-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors',
      active
        ? 'border-zinc-900 bg-zinc-900 text-white'
        : 'border-white/70 bg-white/62 text-slate-600 backdrop-blur-xl',
    )}
  >
    <span className={cn('flex h-4 w-4 items-center justify-center', active ? 'text-white' : 'text-slate-500')}>
      {icon}
    </span>
    <span className="text-[10px] uppercase tracking-[0.14em] opacity-70">{label}</span>
    <span className="truncate text-[11px]">{value}</span>
  </div>
);

export const RuntimeStatusBar: React.FC<RuntimeStatusBarProps> = ({ session, isLoading, runStatus }) => {
  if (!session) {
    return null;
  }

  const totalTokens = session.lastUsage?.total_tokens ?? session.lastUsage?.totalTokens;
  const hasSummary = Boolean(session.summary);
  const statusLabel = runStatus?.label || (isLoading ? '大模型正在输出' : '已就绪');
  const statusActive = isLoading || runStatus?.phase === 'done';

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="mx-auto mb-5 flex w-full max-w-[92rem] flex-col gap-3 px-8"
    >
      <div className="flex flex-wrap items-center gap-2">
        <Metric
          icon={<Radio size={14} className={isLoading ? 'animate-pulse' : undefined} />}
          label="Status"
          value={statusLabel}
          active={statusActive}
        />
        <Metric icon={<Database size={14} />} label="Store" value={session.storage === 'sqlalchemy' ? 'SQLite' : 'Local'} active />
        <Metric
          icon={<BrainCircuit size={14} />}
          label="Context"
          value={hasSummary ? 'Compressed' : 'Live'}
          active={hasSummary || Boolean(session.contextCompressed)}
        />
        <Metric
          icon={<ShieldCheck size={14} />}
          label="HITL"
          value={isLoading ? 'Watching' : 'Ready'}
        />
        <Metric
          icon={<Timer size={14} />}
          label="Run"
          value={session.llmCalls ? `${session.llmCalls} calls` : totalTokens ? `${totalTokens} tokens` : 'Idle'}
        />
      </div>
      {session.summary && (
        <div className="max-w-4xl rounded-[1.35rem] border border-white/70 bg-white/64 px-4 py-3 text-xs leading-relaxed text-slate-600 shadow-[0_14px_34px_rgba(15,23,42,0.06)] backdrop-blur-xl">
          <div className="mb-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-400">Context summary</div>
          <p className="line-clamp-3 whitespace-pre-wrap">{session.summary}</p>
        </div>
      )}
    </motion.div>
  );
};
