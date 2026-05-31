import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';

type CompanionPhase = 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'done' | 'error';

interface MascotCompanionProps {
  phase: CompanionPhase;
  label?: string;
  className?: string;
  size?: number;
}

/* ── Per‑state colour palette ────────────────────────────── */

const palette: Record<CompanionPhase, { body: string; glow: string; particle: string }> = {
  thinking:        { body: '#7dd3fc', glow: 'rgba(56,189,248,0.22)',  particle: '#bae6fd' },
  streaming:       { body: '#38bdf8', glow: 'rgba(14,165,233,0.28)',  particle: '#7dd3fc' },
  generating_ppt:  { body: '#a78bfa', glow: 'rgba(124,58,237,0.22)',  particle: '#c4b5fd' },
  rendering_ppt:   { body: '#a78bfa', glow: 'rgba(124,58,237,0.22)',  particle: '#c4b5fd' },
  done:            { body: '#34d399', glow: 'rgba(52,211,153,0.28)',  particle: '#6ee7b7' },
  error:           { body: '#fb7185', glow: 'rgba(251,113,133,0.22)', particle: '#fda4af' },
};

const defaultLabel: Record<CompanionPhase, string> = {
  thinking:       '正在思考...',
  streaming:      '正在输出...',
  generating_ppt: '正在生成 PPT...',
  rendering_ppt:  '正在渲染预览...',
  done:           '完成啦',
  error:          '出错了',
};

/* ═══════════════════════════════════════════════════════════
   Animation config — each state gets its own "performance"
   ═══════════════════════════════════════════════════════════ */

interface AnimConfig {
  container: Record<string, number[]>;
  containerTrans: { duration: number; ease: 'linear' | 'easeIn' | 'easeOut' | 'easeInOut'; repeat?: number };
  orbitSpeed: number;             // seconds per revolution, 0 = hidden
  arm?: { range: number[]; duration: number };
  pupilWander: boolean;
  blinkEvery: number;             // 0 = no blink
  earWiggle: boolean;
  streamingDots: boolean;
  pptExtra: boolean;
  sweatDrops: number;
  bodyShake: boolean;             // extra body rect shake
}

const A: Record<CompanionPhase, AnimConfig> = {
  thinking: {
    container: { y: [0, -5, 0] },
    containerTrans: { duration: 2.8, ease: 'easeInOut', repeat: Infinity },
    orbitSpeed: 5,
    arm: { range: [-4, 6, -4], duration: 3 },
    pupilWander: true,
    blinkEvery: 4,
    earWiggle: true,
    streamingDots: false,
    pptExtra: false,
    sweatDrops: 0,
    bodyShake: false,
  },
  streaming: {
    container: { y: [0, -4, 0] },
    containerTrans: { duration: 2.2, ease: 'easeInOut', repeat: Infinity },
    orbitSpeed: 6,
    pupilWander: false,
    blinkEvery: 3.5,
    earWiggle: false,
    streamingDots: true,
    pptExtra: false,
    sweatDrops: 0,
    bodyShake: false,
  },
  generating_ppt: {
    container: { y: [0, -6, 0] },
    containerTrans: { duration: 2.5, ease: 'easeInOut', repeat: Infinity },
    orbitSpeed: 4,
    arm: { range: [-5, 7, -5], duration: 2.6 },
    pupilWander: true,
    blinkEvery: 4,
    earWiggle: true,
    streamingDots: false,
    pptExtra: true,
    sweatDrops: 0,
    bodyShake: false,
  },
  rendering_ppt: {
    container: { y: [0, -6, 0] },
    containerTrans: { duration: 2.5, ease: 'easeInOut', repeat: Infinity },
    orbitSpeed: 4,
    arm: { range: [-5, 7, -5], duration: 2.6 },
    pupilWander: true,
    blinkEvery: 4,
    earWiggle: true,
    streamingDots: false,
    pptExtra: true,
    sweatDrops: 0,
    bodyShake: false,
  },
  done: {
    container: { y: [0, -18, 0, -10, 0, -5, 0] },
    containerTrans: { duration: 0.9, ease: 'easeOut' },
    orbitSpeed: 0,
    pupilWander: false,
    blinkEvery: 0,
    earWiggle: false,
    streamingDots: false,
    pptExtra: false,
    sweatDrops: 0,
    bodyShake: false,
  },
  error: {
    container: {},
    containerTrans: { duration: 0.3, ease: 'easeInOut' },
    orbitSpeed: 0,
    pupilWander: false,
    blinkEvery: 0,
    earWiggle: false,
    streamingDots: false,
    pptExtra: false,
    sweatDrops: 3,
    bodyShake: false,
  },
};

/* ── Orbit particle ──────────────────────────────────────── */

const OrbitDot: React.FC<{ color: string; angle: number; delay: number; opacityRange: [number, number] }> = ({
  color, angle, delay, opacityRange,
}) => {
  const rad = (angle * Math.PI) / 180;
  const r = 70;
  return (
    <motion.div
      className="absolute rounded-full"
      style={{
        width: 5, height: 5,
        background: color,
        left: `calc(50% + ${Math.cos(rad) * r}px - 2.5px)`,
        top: `calc(50% + ${Math.sin(rad) * r}px - 2.5px)`,
      }}
      animate={{ opacity: [opacityRange[0], opacityRange[1], opacityRange[0]], scale: [0.7, 1.3, 0.7] }}
      transition={{ duration: 1.8, delay, repeat: Infinity, ease: 'easeInOut' }}
    />
  );
};

/* ── Done sparkle ────────────────────────────────────────── */

const Sparkle: React.FC<{ x: number; y: number; delay: number; size?: number; color: string }> = ({ x, y, delay, size = 4, color }) => (
  <motion.circle
    cx={String(x)} cy={String(y)} r={size}
    fill={color}
    opacity={0}
    animate={{ opacity: [0, 1, 0], scale: [0.2, 1.3, 0.2] }}
    transition={{ duration: 1.6, delay, repeat: Infinity, ease: 'easeInOut' }}
  />
);

/* ═══════════════════════════════════════════════════════════
   MascotCompanion
   ═══════════════════════════════════════════════════════════ */

export const MascotCompanion: React.FC<MascotCompanionProps> = ({ phase, label, className, size = 100 }) => {
  const c = palette[phase] || palette.thinking;
  const cfg = A[phase] || A.thinking;
  const text = label || defaultLabel[phase];
  const scaleFactor = size / 100;

  const isThinking = phase === 'thinking' || phase === 'generating_ppt' || phase === 'rendering_ppt';
  const isDone    = phase === 'done';
  const isError   = phase === 'error';

  /* ── Eyes ───────────────────────────────────────────── */
  /* Error: X eyes. Done: happy curves. Default: static circle eyes.
     (Blink handled via CSS animation on a wrapper, not motion.circle scaleY.) */

  const eyeR = isThinking ? 4 : 4.5;

  const leftEye = isError
    ? <path d="M33 45 L43 53 M43 45 L33 53" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
    : isDone
    ? <path d="M33 45 Q38 41 43 45" stroke="#0f172a" strokeWidth="3" fill="none" strokeLinecap="round" />
    : <circle cx={38} cy={47} r={eyeR} fill="#0f172a" />;

  const rightEye = isError
    ? <path d="M57 45 L67 53 M67 45 L57 53" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
    : isDone
    ? <path d="M57 45 Q62 41 67 45" stroke="#0f172a" strokeWidth="3" fill="none" strokeLinecap="round" />
    : <circle cx={62} cy={47} r={eyeR} fill="#0f172a" />;

  /* ── Eye catchlights (with pupil wander for thinking states) ── */
  const leftPupil = (!isError && !isDone) && (
    <motion.circle
      r={1.5} fill="white"
      cx={isThinking ? '39' : '39.5'}
      cy={isThinking ? '45' : '45.5'}
      animate={cfg.pupilWander
        ? { cx: ['39', '40', '38', '39.5', '39'], cy: ['45', '44', '46', '44.5', '45'] }
        : {}}
      transition={cfg.pupilWander
        ? { duration: 4, repeat: Infinity, ease: 'easeInOut' }
        : {}}
    />
  );

  const rightPupil = (!isError && !isDone) && (
    <motion.circle
      r={1.5} fill="white"
      cx={isThinking ? '63' : '63.5'}
      cy={isThinking ? '45' : '45.5'}
      animate={cfg.pupilWander
        ? { cx: ['63', '64', '62', '63.5', '63'], cy: ['45', '44', '46', '44.5', '45'] }
        : {}}
      transition={cfg.pupilWander
        ? { duration: 4, repeat: Infinity, ease: 'easeInOut' }
        : {}}
    />
  );

  /* ── Mouth ───────────────────────────────────────────── */
  const mouth = isDone
    ? <path d="M44 57 Q50 67 56 57" stroke="#0f172a" strokeWidth="2.5" strokeLinecap="round" fill="none" />
    : isError
    ? <path d="M44 60 Q50 56 56 60" stroke="#0f172a" strokeWidth="2.5" strokeLinecap="round" fill="none" />
    : isThinking
    ? <circle cx={50} cy={58} r={3} fill="#0f172a" />
    : <path d="M46 56 Q50 61 54 56" stroke="#0f172a" strokeWidth="2.5" strokeLinecap="round" fill="none" />;

  /* ── Thinking arm ────────────────────────────────────── */
  const thinkingArm = cfg.arm && (
    <motion.path
      d="M68 55 L78 48"
      stroke="#0f172a" strokeWidth="3" strokeLinecap="round"
      animate={{ rotate: cfg.arm.range }}
      transition={{ duration: cfg.arm.duration, repeat: Infinity, ease: 'easeInOut' }}
      style={{ transformOrigin: '68px 55px' }}
    />
  );

  /* ── Ear wiggle ──────────────────────────────────────── */
  const leftEar = (
    <motion.path
      d="M20 40 L30 10 L50 30 Z"
      fill={c.body} stroke={c.body} strokeWidth="4" strokeLinejoin="round"
      style={{ transformOrigin: '30px 35px' }}
      animate={cfg.earWiggle
        ? { rotate: [-2, 3, -2] }
        : {}}
      transition={cfg.earWiggle
        ? { duration: 2.5, repeat: Infinity, ease: 'easeInOut' }
        : {}}
    />
  );

  /* ── Glow animation (matches container timing) ───────── */
  const glowScale = isDone
    ? [1, 1.25, 1, 1.12, 1, 1.06, 1, 1, 1, 1, 1] as number[]
    : isError
    ? [1, 1.3, 1] as number[]
    : [1, 1.18, 1] as number[];

  const glowDuration = isDone ? 0.9 : isError ? 0.8 : 2.2;

  /* ══════════════════════════════════════════════════════
     Render
     ══════════════════════════════════════════════════════ */

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={phase}
        initial={{ opacity: 0, scale: 0.7, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.7, y: -16 }}
        transition={{ type: 'spring', damping: 20, stiffness: 280 }}
        className={cn('flex flex-col items-center gap-3 select-none pointer-events-none', className)}
      >
        {/* ── Character + glow + orbit ───────────────── */}
        <motion.div
          className="relative"
          animate={cfg.container}
          transition={cfg.containerTrans}
        >
          {/* soft glow */}
          <motion.div
            className="absolute rounded-full blur-2xl"
            style={{
              width: Math.round(96 * scaleFactor), height: Math.round(96 * scaleFactor),
              left: '50%', top: '50%',
              marginLeft: Math.round(-48 * scaleFactor), marginTop: Math.round(-48 * scaleFactor),
              background: c.glow,
            }}
            animate={{ scale: glowScale, opacity: [0.45, 0.75, 0.45] }}
            transition={{ duration: glowDuration, repeat: Infinity, ease: 'easeInOut' }}
          />

          {/* orbit ring */}
          {cfg.orbitSpeed > 0 && (
            <motion.div
              className="absolute"
              style={{
                width: Math.round(140 * scaleFactor), height: Math.round(140 * scaleFactor),
                left: '50%', top: '50%',
                marginLeft: Math.round(-70 * scaleFactor), marginTop: Math.round(-70 * scaleFactor),
              }}
              animate={{ rotate: 360 }}
              transition={{ duration: cfg.orbitSpeed, repeat: Infinity, ease: 'linear' }}
            >
              {[0, 72, 144, 216, 288].map((angle, i) => (
                <OrbitDot key={i} color={c.particle} angle={angle} delay={i * 0.35} opacityRange={cfg.orbitSpeed <= 5 ? [0.15, 1] : [0.25, 0.85]} />
              ))}
            </motion.div>
          )}

          {/* ── SVG character ── */}
          <motion.svg
            width={size} height={size}
            viewBox="0 0 100 100" fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="relative z-10"
          >
            {/* Ears */}
            {leftEar}
            <path d="M80 40 L70 10 L50 30 Z" fill={c.body} stroke={c.body} strokeWidth="4" strokeLinejoin="round" />

            {/* Body */}
            <motion.rect
              x="15" y="25" width="70" height="55" rx="25"
              fill={c.body}
              animate={cfg.bodyShake ? { x: [15, 19, 13, 17, 15] } : {}}
              transition={cfg.bodyShake ? { duration: 0.35, repeat: 2 } : {}}
            />

            {/* Face plate */}
            <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />

            {/* Blush */}
            {!isError && (
              <>
                <ellipse cx="30" cy="52" rx="6" ry="4" fill="#f9a8d4" opacity="0.4" />
                <ellipse cx="70" cy="52" rx="6" ry="4" fill="#f9a8d4" opacity="0.4" />
              </>
            )}

            {/* Eyes */}
            {leftEye}
            {rightEye}

            {/* Eye catchlights */}
            {leftPupil}
            {rightPupil}

            {/* Mouth */}
            {mouth}

            {/* Thinking arm */}
            {thinkingArm}

            {/* Done celebratory sparkles */}
            {isDone && (
              <>
                <Sparkle x={8} y={8} delay={0} size={4.5} color={c.body} />
                <Sparkle x={92} y={12} delay={0.25} size={3.5} color={c.body} />
                <Sparkle x={90} y={80} delay={0.5} size={4} color={c.body} />
                <Sparkle x={10} y={78} delay={0.75} size={3} color={c.body} />
                <Sparkle x={50} y={2} delay={1.0} size={5} color={c.body} />
                <Sparkle x={18} y={18} delay={1.25} size={3} color={c.body} />
              </>
            )}

            {/* Error sweat drops */}
            {isError && [0, 1, 2].map(i => (
              <motion.circle
                key={i}
                cx={String(68 + i * 4)} cy={String(38 - i * 3)} r={2}
                fill="#94a3b8"
                animate={{ y: [0, 10, 10], opacity: [1, 1, 0] }}
                transition={{ duration: 1.4, delay: i * 0.35, repeat: Infinity }}
              />
            ))}

            {/* PPT extra: small construction dots */}
            {cfg.pptExtra && (
              <g>
                {[0, 1, 2].map(i => (
                  <motion.circle
                    key={i}
                    cx={String(20 + i * 30)} cy="85"
                    r={2} fill={c.particle}
                    animate={{ opacity: [0, 1, 0], y: [0, -8, 0] }}
                    transition={{ duration: 1.2, delay: i * 0.3, repeat: Infinity }}
                  />
                ))}
              </g>
            )}
          </motion.svg>

          {/* streaming flying dots — redesign: continuous flow shoot right */}
          {cfg.streamingDots && (
            <div className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-4 flex flex-col gap-1.5">
              {[
                { delay: 0, dur: 1.0 },
                { delay: 0.15, dur: 1.3 },
                { delay: 0.3, dur: 0.9 },
                { delay: 0.5, dur: 1.2 },
                { delay: 0.7, dur: 1.5 },
              ].map((d, i) => (
                <motion.div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: c.body }}
                  animate={{ x: [0, 30], opacity: [1, 0] }}
                  transition={{ duration: d.dur, delay: d.delay, repeat: Infinity, ease: 'easeOut' }}
                />
              ))}
            </div>
          )}
        </motion.div>

        {/* ── Label ──────────────────────────────────── */}
        <motion.p
          key={text}
          initial={{ opacity: 0, y: 3 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-sm font-bold tracking-wide"
          style={{ color: c.body }}
        >
          {text}
        </motion.p>
      </motion.div>
    </AnimatePresence>
  );
};
