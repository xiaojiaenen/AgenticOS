import React from 'react';
import { motion } from 'motion/react';
import { cn } from '../../lib/utils';
import { MascotThinking, MascotHappy, MascotSad, MascotCurious } from './MascotIcons';

type MascotPhase = 'idle' | 'thinking' | 'streaming' | 'done' | 'error';

interface MascotStateProps {
  phase: MascotPhase;
  size?: number;
  className?: string;
  label?: string;
}

const phaseConfig: Record<MascotPhase, {
  Component: React.FC<{ size?: number; className?: string }>;
  color: string;
}> = {
  // idle 用「好奇」：会自己歪头、眨眼，比墨镜 + animate-pulse 的双层匀速动画自然
  idle: {
    Component: MascotCurious,
    color: 'text-[var(--muted-foreground)]',
  },
  thinking: {
    Component: MascotThinking,
    color: 'text-brand-500',
  },
  streaming: {
    Component: MascotThinking,
    color: 'text-brand-400',
  },
  done: {
    Component: MascotHappy,
    color: 'text-emerald-600 dark:text-emerald-400',
  },
  error: {
    Component: MascotSad,
    color: 'text-rose-600 dark:text-rose-400',
  },
};

export const MascotState: React.FC<MascotStateProps> = ({
  phase,
  size = 32,
  className,
  label,
}) => {
  const config = phaseConfig[phase] || phaseConfig.idle;
  const Icon = config.Component;

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: 'spring', damping: 20, stiffness: 300 }}
      className={cn('flex items-center gap-2', className)}
    >
      <div className={cn(
        'flex items-center justify-center rounded-2xl p-1.5',
        phase === 'thinking' && 'bg-brand-50 shadow-glow',
        phase === 'streaming' && 'bg-brand-50/70',
        phase === 'done' && 'bg-emerald-50 dark:bg-emerald-950/40',
        phase === 'error' && 'bg-rose-50 dark:bg-rose-950/40',
      )}>
        <Icon size={size} className={config.color} />
      </div>
      {label && (
        <motion.span
          key={label}
          initial={{ opacity: 0, x: -4 }}
          animate={{ opacity: 1, x: 0 }}
          className="text-xs font-semibold whitespace-nowrap text-[var(--muted-foreground)]"
        >
          {label}
        </motion.span>
      )}
    </motion.div>
  );
};
