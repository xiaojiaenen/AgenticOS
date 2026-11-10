import React from 'react';
import { AnimatePresence, motion, useReducedMotion, type Transition } from 'motion/react';
import { cn } from '../../lib/utils';
import { MascotBase } from './MascotIcons';

type CompanionPhase = 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'done' | 'error';

interface MascotCompanionProps {
  phase: CompanionPhase;
  label?: string;
  className?: string;
  size?: number;
}

/* ═══════════════════════════════════════════════════════════
   陪伴态吉祥物

   旧版靠光晕 / 轨道粒子 / 庆祝星点 / 汗滴 / 飞行小圆点表达状态，
   是典型的「装饰堆砌」。这里全部去掉，只让角色本人表演：
   歪头、呼吸节奏、耳朵抽动、视线飘移、一次跳跃、垂耳下沉。
   颜色走低饱和色 + CSS 变量，深浅主题与图标完全一致。
   ═══════════════════════════════════════════════════════════ */

const palette: Record<CompanionPhase, string> = {
  thinking:       '#6E93AC',
  streaming:      '#4E8AA6',
  generating_ppt: '#8877A3',
  rendering_ppt:  '#8877A3',
  done:           '#6A9A7E',
  error:          '#B0757C',
};

const defaultLabel: Record<CompanionPhase, string> = {
  thinking:       '正在思考...',
  streaming:      '正在输出...',
  generating_ppt: '正在生成 PPT...',
  rendering_ppt:  '正在渲染预览...',
  done:           '完成啦',
  error:          '出错了',
};

type PoseKey = 'ponder' | 'flow' | 'busy' | 'hop' | 'slump';

const POSES: Record<PoseKey, { animate: Record<string, number[]>; transition: Transition }> = {
  // 歪一下头，然后停很久
  ponder: {
    animate: { rotate: [0, 0, -2.4, 1, 0, 0] },
    transition: { duration: 8, times: [0, 0.42, 0.5, 0.58, 0.68, 1], repeat: Infinity, ease: 'easeInOut' },
  },
  // 输出时呼吸稍快，但不做匀速正弦
  flow: {
    animate: { y: [0, -2, 0, -1, 0, 0], scale: [1, 1.012, 1, 1.006, 1, 1] },
    transition: { duration: 5, times: [0, 0.2, 0.4, 0.6, 0.8, 1], repeat: Infinity, ease: 'easeInOut' },
  },
  busy: {
    animate: { y: [0, -3, 0, -2, 0, 0], rotate: [0, -1.5, 0, 1.5, 0, 0] },
    transition: { duration: 4.2, times: [0, 0.2, 0.4, 0.6, 0.8, 1], repeat: Infinity, ease: 'easeInOut' },
  },
  // 完成只跳一次，不循环蹦
  hop: {
    animate: { y: [0, -16, 0, -5, 0], scale: [1, 1.04, 1, 1.01, 1] },
    transition: { duration: 0.95, times: [0, 0.25, 0.55, 0.78, 1], ease: 'easeOut' },
  },
  slump: {
    animate: { y: [0, 3, 3], rotate: [0, -1.5, -1.5] },
    transition: { duration: 1.1, times: [0, 0.55, 1], ease: 'easeOut' },
  },
};

const poseFor: Record<CompanionPhase, PoseKey> = {
  thinking: 'ponder',
  streaming: 'flow',
  generating_ppt: 'busy',
  rendering_ppt: 'busy',
  done: 'hop',
  error: 'slump',
};

const INK = 'var(--mascot-ink)';
const S = {
  stroke: INK,
  strokeWidth: 2.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  fill: 'none',
};

/* 眨眼：长间隔 + 偶发双眨 */
const BLINK: Transition = {
  duration: 7.5, times: [0, 0.44, 0.52, 0.54, 0.57, 0.64, 0.66, 0.69, 1],
  repeat: Infinity, ease: 'easeInOut',
};
const GAZE: Transition = {
  duration: 10, times: [0, 0.28, 0.42, 0.56, 0.7, 1],
  repeat: Infinity, ease: 'easeInOut',
};

/** 五官：只换线条形态，不加贴纸符号 */
const Face: React.FC<{ phase: CompanionPhase; animated: boolean }> = ({ phase, animated }) => {
  const reduced = useReducedMotion();
  const a = animated && !reduced;

  if (phase === 'done') {
    return (
      <>
        <path {...S} d="M35 51 Q39.5 46 45 51" strokeWidth={2.5} />
        <path {...S} d="M55 50 Q60.5 45.5 66 50" strokeWidth={2.5} />
        <path {...S} d="M45 61.5 Q50 64 55 61.5" strokeWidth={2.2} />
      </>
    );
  }
  if (phase === 'error') {
    return (
      <>
        <path {...S} d="M35 47 Q40 51 45 48" strokeWidth={2.5} />
        <path {...S} d="M56 47 Q61 51 66 46" strokeWidth={2.5} />
        <path {...S} d="M46 63 Q50 60 54 63" strokeWidth={2.2} />
      </>
    );
  }

  const isPpt = phase === 'generating_ppt' || phase === 'rendering_ppt';
  const shift = phase === 'streaming' ? 1.2 : 0;
  const eyeY = isPpt ? 48 : 49;
  const eyeY2 = isPpt ? 50 : 48;
  return (
    <motion.g
      animate={a ? { x: [0, 0, 0.9 + shift, -0.6, 0, 0] } : undefined}
      transition={a ? GAZE : undefined}
    >
      <motion.g
        style={{ transformOrigin: '50px 50px' }}
        animate={a ? { scaleY: [1, 1, 1, 0.08, 1, 1, 0.08, 1, 1] } : undefined}
        transition={a ? BLINK : undefined}
      >
        <ellipse cx={39.5} cy={eyeY} rx="2.5" ry="3.7" fill={INK} transform={`rotate(-9 39.5 ${eyeY})`} />
        <ellipse cx={61.5} cy={eyeY2} rx="2.5" ry="3.7" fill={INK} transform={`rotate(-9 61.5 ${eyeY2})`} />
      </motion.g>
      {phase === 'thinking'
        ? <circle cx="50" cy="61" r="2.1" fill={INK} />
        : <path {...S} d="M46.5 62 L53.5 62" strokeWidth={2.1} />}
    </motion.g>
  );
};

export const MascotCompanion: React.FC<MascotCompanionProps> = ({ phase, label, className, size = 100 }) => {
  const reduced = useReducedMotion();
  const a = !reduced;
  const pose = POSES[poseFor[phase]];
  const text = label || defaultLabel[phase];
  const isError = phase === 'error';

  // 文字与间距跟着 size 走；旧版字号固定，32px 的吉祥物配 14px 文字严重失衡
  const fontSize = Math.min(16, Math.max(10, Math.round(size * 0.13)));
  const gap = Math.max(4, Math.round(size * 0.09));

  return (
    <div className={cn('flex flex-col items-center select-none pointer-events-none', className)} style={{ gap }}>
      <div className="relative" style={{ width: size, height: size }}>
        <AnimatePresence>
          <motion.div
            key={phase}
            initial={{ opacity: 0, scale: 0.94, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 1.03, y: -5 }}
            transition={{ duration: 0.32, ease: 'easeOut' }}
            className="absolute inset-0"
          >
            <motion.svg
              width={size} height={size}
              viewBox="0 0 100 100" fill="none"
              xmlns="http://www.w3.org/2000/svg"
              style={{ color: palette[phase] }}
              role="img" aria-label={text} focusable="false"
            >
              <motion.g
                style={{ transformOrigin: '50px 55px' }}
                animate={a ? pose.animate : undefined}
                transition={a ? pose.transition : undefined}
              >
                <MascotBase ears={isError ? 'droop' : 'up'} animated={a}>
                  <Face phase={phase} animated={a} />
                </MascotBase>
              </motion.g>
            </motion.svg>
          </motion.div>
        </AnimatePresence>
      </div>
      <AnimatePresence mode="wait">
        <motion.p
          key={text}
          initial={{ opacity: 0, y: 3 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -3 }}
          transition={{ duration: 0.24 }}
          className="font-medium tracking-wide"
          style={{ fontSize, color: 'var(--muted-foreground)' }}
        >
          {text}
        </motion.p>
      </AnimatePresence>
    </div>
  );
};
