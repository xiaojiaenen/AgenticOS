import React from 'react';
import { motion, useReducedMotion, type Transition } from 'motion/react';

/* ═══════════════════════════════════════════════════════════════
   吉祥物 / 表情库

   造型沿用旧版猫头鹰骨架：双尖耳 + 圆角方形身体 + 面盘 + 大眼。
   在旧版基础上做了三处精修：

   1. 耳尖从硬三角改成圆头（一个 Q 收角），缩到 24px 时不再糊成一团；
   2. 身体与面盘改用 path 表达，边缘比整块 rect 更贴手感，
      面盘不再刺眼纯白，混入一点主色，深色主题下也不突兀；
   3. 旧版「思考」表情有一条 `M30 60 L20 50` 的斜线，从面盘左边缘
      伸到脸外悬空 —— 本意是托腮的手，实际看着就是脸上挂了一条黑线。
      这里删掉它，改用高低差眼位 + 一道眉弧表达思考，不再有悬空笔画。

   动画节奏统一改成「动一下 → 停很久 → 再动一下」，
   不用匀速 repeat 的正弦波 —— 那是最容易被看出「机器在循环」的来源。
   ═══════════════════════════════════════════════════════════════ */

export interface MascotIconProps {
  size?: number;
  className?: string;
  /** 传入即作为无障碍名称；不传视为装饰图案（aria-hidden） */
  title?: string;
}

const INK = 'var(--mascot-ink)';
const FACE = 'var(--mascot-face)';

const S = {
  stroke: INK,
  strokeWidth: 2.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  fill: 'none',
};

/* ── 几何 ─────────────────────────────────────────────────────
   坐标沿用旧版 viewBox 0 0 100 100，尺寸与位置保持可辨识：
   耳尖 y≈12、身体 y 25–80、面盘 x 25–75 / y 35–70。
   只是把硬角换成圆角，让它在 16–24px 下也不粘成一块。
   ─────────────────────────────────────────────────────────────── */
const PATHS = {
  // 尖耳 + 圆头：顶点处用三次贝塞尔收成一个明显的圆头（控制点外扩），
  // 比 Q 单控制点更圆，24px 下也不会糊成硬三角。
  earLeft:
    'M20 40 C22 30 26 20 29 13 C30.2 9.6 32.4 9.6 33.6 13 C37 21 42 27 50 30 Z',
  earRight:
    'M80 40 C78 30 74 20 71 13 C69.8 9.6 67.6 9.6 66.4 13 C63 21 58 27 50 30 Z',
  // 垂耳（失落时用）：整体下压、尖端朝外下方，与竖耳形成明显情绪差
  earLeftDroop: 'M21 42 C22 33 23.5 25 25 21 C25.8 18.4 28 18.8 28.8 21.6 L48 31 Z',
  earRightDroop: 'M79 42 C78 33 76.5 25 75 21 C74.2 18.4 72 18.8 71.2 21.6 L52 31 Z',
  // 身体：旧版 rect(15,25,70,55,r25) 的 path 版，顶部加一点不对称起伏
  body:
    'M50 25 C65 25 78.5 27.5 83 37.5 C87 46 85 62 78 71 C71 78 60 80 50 80 ' +
    'C40 80 29 78 22 71 C15 62 13 46 17 37.5 C21.5 27.5 35 25 50 25 Z',
  // 面盘：旧版 rect(25,35,50,35,r15) 的 path 版（四角用 A 弧）
  face: 'M40 35 H60 A15 15 0 0 1 75 50 V55 A15 15 0 0 1 60 70 H40 A15 15 0 0 1 25 55 V50 A15 15 0 0 1 40 35 Z',
};

/* ── 耳朵抽动：左右各自在不同时刻动，永不同步 ─────────────── */
const EAR_T_L: Transition = {
  duration: 9.5, times: [0, 0.62, 0.68, 0.74, 0.82, 1],
  repeat: Infinity, ease: 'easeInOut',
};
const EAR_T_R: Transition = {
  duration: 13.5, times: [0, 0.7, 0.76, 0.82, 0.9, 1],
  repeat: Infinity, ease: 'easeInOut', delay: 2.6,
};

/** 所有吉祥物（含 MascotCompanion）共用的几何基座。children 是五官。 */
export const MascotBase: React.FC<{
  ears?: 'up' | 'droop';
  animated?: boolean;
  children?: React.ReactNode;
}> = ({ ears = 'up', animated = true, children }) => {
  const reduced = useReducedMotion();
  const a = animated && !reduced;
  const droop = ears === 'droop';

  return (
    // 恒定的一点侧倾：完全对称正面是「呆」的主要来源
    <g transform="rotate(-2 50 54)">
      <motion.g
        style={{ transformOrigin: '30px 34px' }}
        animate={a && !droop ? { rotate: [0, 0, -2.4, 1.2, 0, 0] } : undefined}
        transition={a && !droop ? EAR_T_L : undefined}
      >
        <path d={droop ? PATHS.earLeftDroop : PATHS.earLeft} fill="currentColor" />
      </motion.g>
      <motion.g
        style={{ transformOrigin: '70px 34px' }}
        animate={a && !droop ? { rotate: [0, 0, 2.4, -1.2, 0, 0] } : undefined}
        transition={a && !droop ? EAR_T_R : undefined}
      >
        <path d={droop ? PATHS.earRightDroop : PATHS.earRight} fill="currentColor" />
      </motion.g>

      <path d={PATHS.body} fill="currentColor" />

      {/* 面盘混入一点主色：纯白在深色主题里像贴了张纸，
          混色后与身体同色系，两种主题都自然。color-mix 不支持时回退到 FACE */}
      <path
        d={PATHS.face}
        fill={FACE}
        style={{ fill: 'color-mix(in srgb, currentColor 14%, var(--mascot-face))' }}
      />

      {children}
    </g>
  );
};

/* ── 眨眼：长间隔 + 偶发双眨 ─────────────────────────────── */
const BLINK_FRAMES = [1, 1, 1, 0.08, 1, 1, 0.08, 1, 1];
const BLINK_T: Transition = {
  duration: 8.5, times: [0, 0.46, 0.54, 0.56, 0.59, 0.65, 0.67, 0.7, 1],
  repeat: Infinity, ease: 'easeInOut',
};

const Blink: React.FC<{ a: boolean; on?: boolean; children: React.ReactNode }> = ({
  a, on = true, children,
}) => (
  <motion.g
    style={{ transformOrigin: '50px 48px' }}
    animate={a && on ? { scaleY: BLINK_FRAMES } : undefined}
    transition={a && on ? BLINK_T : undefined}
  >
    {children}
  </motion.g>
);

/* ── 视线漂移：五官整体极缓慢飘一下 ───────────────────────── */
const GAZE_T: Transition = {
  duration: 12, times: [0, 0.3, 0.44, 0.58, 0.72, 1],
  repeat: Infinity, ease: 'easeInOut',
};

/* ── 整体姿态 ─────────────────────────────────────────────── */
type MotionKind = 'float' | 'tilt' | 'breathe' | 'pop' | 'jitter' | 'settle' | 'none';

const MOTION: Record<MotionKind, { animate: Record<string, number[]>; transition: Transition }> = {
  float: {
    animate: { y: [0, -2, -0.8, -2.4, 0, 0] },
    transition: { duration: 7.5, times: [0, 0.16, 0.3, 0.46, 0.62, 1], repeat: Infinity, ease: 'easeInOut' },
  },
  tilt: {
    animate: { rotate: [0, -2.2, -0.8, 1.8, 0, 0] },
    transition: { duration: 9, times: [0, 0.2, 0.34, 0.5, 0.66, 1], repeat: Infinity, ease: 'easeInOut' },
  },
  breathe: {
    animate: { scale: [1, 1.02, 1, 1.012, 1, 1] },
    transition: { duration: 6.5, times: [0, 0.22, 0.44, 0.62, 0.8, 1], repeat: Infinity, ease: 'easeInOut' },
  },
  pop: {
    animate: { scale: [1, 1.06, 0.985, 1, 1] },
    transition: { duration: 1.6, times: [0, 0.2, 0.45, 0.7, 1], repeat: Infinity, repeatDelay: 3.4, ease: 'easeOut' },
  },
  jitter: {
    animate: { x: [0, -1.4, 1.2, -0.6, 0, 0], rotate: [0, -2.2, 2.2, -1, 0, 0] },
    transition: { duration: 1.1, times: [0, 0.2, 0.4, 0.6, 0.8, 1], repeat: Infinity, repeatDelay: 4.2, ease: 'easeInOut' },
  },
  settle: {
    animate: { y: [0, 2.6, 2.6] },
    transition: { duration: 1.2, times: [0, 0.5, 1], ease: 'easeOut' },
  },
  none: { animate: {}, transition: { duration: 1 } },
};

/* ── 12 张脸 ────────────────────────────────────────────── */
type FaceFn = (a: boolean) => React.ReactNode;

interface Expression {
  label: string;
  motion: MotionKind;
  ears?: 'up' | 'droop';
  blink?: boolean;
  face: FaceFn;
}

/** 旧版的大圆眼，保留（这是猫头鹰造型的核心特征之一） */
const Eye: React.FC<{ cx: number; cy: number; r?: number }> = ({ cx, cy, r = 4 }) => (
  <ellipse cx={cx} cy={cy} rx={r} ry={r} fill={INK} />
);

const EXPRESSIONS: Record<string, Expression> = {
  happy: {
    label: '开心', motion: 'float', blink: true,
    face: (a) => (
      <>
        <Blink a={a}>
          <Eye cx={40} cy={48} />
          <Eye cx={60} cy={48} />
        </Blink>
        {/* 腮红保留（旧版特征），但降到 0.55 不透明度，不再抢眼 */}
        <circle cx={32} cy={55} r={3} fill="var(--mascot-shine)" opacity={0.55} />
        <circle cx={68} cy={55} r={3} fill="var(--mascot-shine)" opacity={0.55} />
        <path {...S} d="M46 56 Q50 60 54 56" strokeWidth={2.1} />
      </>
    ),
  },
  curious: {
    label: '好奇', motion: 'tilt', blink: true,
    face: (a) => (
      <>
        {/* 一眼大一眼小是「好奇」的关键，但旧版左眼 r=5 且 cy=47 偏高，
            压到面盘上缘像贴在外面。收到 r=4.6、cy=48.5 并保持右眼更小，
            高低差保留、越界消失。 */}
        <Blink a={a}>
          <Eye cx={40} cy={48.5} r={4.6} />
          <Eye cx={60} cy={49.5} r={3.6} />
        </Blink>
        <path {...S} d="M41 61 Q50 66 59 61" strokeWidth={2.1} />
      </>
    ),
  },
  sleepy: {
    label: '困', motion: 'breathe',
    face: () => (
      <>
        <path {...S} d="M35 48 L45 48" strokeWidth={2.6} />
        <path {...S} d="M55 48 L65 48" strokeWidth={2.6} />
        <circle cx={50} cy={59} r={2.2} fill={INK} opacity={0.75} />
      </>
    ),
  },
  surprised: {
    label: '惊讶', motion: 'pop', blink: true,
    face: (a) => (
      <>
        <Blink a={a} on={false}>
          <Eye cx={40} cy={48} r={6} />
          <Eye cx={60} cy={48} r={6} />
        </Blink>
        <circle cx={50} cy={62} r={6} {...S} strokeWidth={2.6} />
      </>
    ),
  },
  cool: {
    label: '酷', motion: 'tilt',
    face: () => (
      <>
        {/* 墨镜：两片圆角条 + 中间细桥，比旧版两个裸矩形更像一副眼镜 */}
        <rect x={30} y={44} width={16} height={7} rx={3.2} fill={INK} />
        <rect x={54} y={44} width={16} height={7} rx={3.2} fill={INK} />
        <path d="M46 47 H54" stroke={INK} strokeWidth={1.8} />
        <path {...S} d="M43 61 Q50 57 57 61" strokeWidth={2.1} />
      </>
    ),
  },
  thinking: {
    label: '思考', motion: 'tilt', blink: true,
    face: (a) => (
      <>
        {/* 旧版这里有一条 M30 60 L20 50 的斜线，从面盘左缘伸到脸外悬空，
            看着就是「脸上挂了条黑线」。改成一道眉弧 + 高低差眼位：
            表达同一件事，但不留悬空笔画。 */}
        <path {...S} d="M34 40.5 Q40 38 45.5 40" strokeWidth={1.9} />
        <Blink a={a}>
          <Eye cx={40} cy={49} r={4} />
          <Eye cx={60} cy={47} r={4} />
        </Blink>
        <path {...S} d="M45 60 Q50 62.5 55 60" strokeWidth={2} />
      </>
    ),
  },
  excited: {
    label: '兴奋', motion: 'pop',
    face: () => (
      <>
        <Eye cx={40} cy={45} r={5} />
        <Eye cx={60} cy={45} r={5} />
        <rect x={40} y={55} width={20} height={10} rx={5} fill={INK} />
      </>
    ),
  },
  love: {
    label: '喜欢', motion: 'float',
    face: () => (
      <>
        {/* 心形眼：用两段三次曲线画，比旧版两个菱形拼接更圆润 */}
        <path
          d="M40 44 C36 40 31 43.5 31 47.5 C31 51.5 35.5 55 40 57.5 C44.5 55 49 51.5 49 47.5 C49 43.5 44 40 40 44 Z"
          fill="#e0778a"
        />
        <path
          d="M60 44 C56 40 51 43.5 51 47.5 C51 51.5 55.5 55 60 57.5 C64.5 55 69 51.5 69 47.5 C69 43.5 64 40 60 44 Z"
          fill="#e0778a"
        />
        <path {...S} d="M46 63 Q50 66 54 63" strokeWidth={2} />
      </>
    ),
  },
  starstruck: {
    label: '出神', motion: 'breathe', blink: true,
    face: (a) => (
      <>
        <Blink a={a} on={false}>
          {/* 五角星眼睛：半径略收，避免和 surprised 的大圆眼撞脸 */}
          <path
            d="M40 42.5 L42 47.2 L47 47.6 L43.2 50.9 L44.4 55.6 L40 52.8 L35.6 55.6 L36.8 50.9 L33 47.6 L38 47.2 Z"
            fill="#d9a94e"
          />
          <path
            d="M60 42.5 L62 47.2 L67 47.6 L63.2 50.9 L64.4 55.6 L60 52.8 L55.6 55.6 L56.8 50.9 L53 47.6 L58 47.2 Z"
            fill="#d9a94e"
          />
        </Blink>
        <ellipse cx={50} cy={62} rx={4.4} ry={3.4} fill={INK} />
      </>
    ),
  },
  sad: {
    label: '失落', motion: 'settle', ears: 'droop',
    face: () => (
      <>
        <path {...S} d="M34 46 Q40 42.5 46 46" strokeWidth={2.4} />
        <path {...S} d="M54 46 Q60 42.5 66 46" strokeWidth={2.4} />
        <path {...S} d="M45 62 Q50 58.5 55 62" strokeWidth={2.1} />
        {/* 一滴泪：从眼角缓慢滑落再消失，比两颗常驻泪点自然 */}
        <motion.circle
          cx={37} cy={52} r={2.4} fill="#8aa4b8" opacity={0.85}
          animate={{ cy: [52, 58, 60], opacity: [0.85, 0.7, 0] }}
          transition={{ duration: 3.4, times: [0, 0.7, 1], repeat: Infinity, repeatDelay: 2.6, ease: 'easeIn' }}
        />
      </>
    ),
  },
  wink: {
    label: '眨眼', motion: 'tilt',
    face: () => (
      <>
        <Eye cx={40} cy={48} />
        <path {...S} d="M55 48 L65 48" strokeWidth={2.6} />
        <path {...S} d="M45 58 Q50 62 55 58" strokeWidth={2} />
        {/* 小舌头：静态版也保留，但用圆角三角而非旧版尖角 */}
        <motion.path
          d="M48.5 59.5 Q50 65 51.5 59.5 Z" fill="#e0778a"
          style={{ transformOrigin: '50px 59.5px' }}
          animate={{ scaleY: [1, 1.18, 1] }}
          transition={{ duration: 1.6, times: [0, 0.4, 1], repeat: Infinity, repeatDelay: 1.4, ease: 'easeOut' }}
        />
      </>
    ),
  },
  dizzy: {
    label: '晕', motion: 'jitter',
    face: () => (
      <>
        {/* 叉眼：四段短线收在 8px 见方内，比旧版更紧凑不糊 */}
        <path d="M36.5 44.5 L43.5 51.5 M43.5 44.5 L36.5 51.5" stroke={INK} strokeWidth={2.6} strokeLinecap="round" />
        <path d="M56.5 44.5 L63.5 51.5 M63.5 44.5 L56.5 51.5" stroke={INK} strokeWidth={2.6} strokeLinecap="round" />
        <path {...S} d="M42 62 Q46 58 50 62 Q54 66 58 62" strokeWidth={2} />
      </>
    ),
  },
};

/* ── 模式徽章 ──────────────────────────────────────────────── */
type ModeKey = 'general' | 'ppt' | 'website' | 'bigdata' | 'video' | 'email';

const MODE: Record<ModeKey, { color: string; glyph: React.ReactNode; spin?: boolean }> = {
  general: {
    color: '#5E7F96',
    glyph: <><circle cx="71" cy="79" r="2" fill="#fff" /><circle cx="78" cy="79" r="2" fill="#fff" /><circle cx="85" cy="79" r="2" fill="#fff" /></>,
  },
  ppt: {
    color: '#7A6A93',
    glyph: <path d="M71 86 V79 M78 86 V73 M85 86 V81" stroke="#fff" strokeWidth="3" strokeLinecap="round" />,
  },
  website: {
    color: '#5E8A73',
    glyph: (
      <>
        <circle cx="78" cy="79" r="8" stroke="#fff" strokeWidth="2" fill="none" />
        <path d="M70 79 H86 M78 71 Q83 79 78 87 Q73 79 78 71" stroke="#fff" strokeWidth="1.6" fill="none" />
      </>
    ),
  },
  bigdata: {
    color: '#A57A55', spin: true,
    glyph: (
      <>
        <circle cx="78" cy="79" r="5.5" stroke="#fff" strokeWidth="2.2" fill="none" />
        <path d="M78 70 v3 M78 85 v3 M69 79 h3 M84 79 h3 M71.5 72.5 l2 2 M82.5 83.5 l2 2 M84.5 72.5 l-2 2 M73.5 83.5 l-2 2" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
      </>
    ),
  },
  video: {
    color: '#8A6A82',
    glyph: <path d="M74 73 L86 79 L74 85 Z" fill="#fff" />,
  },
  email: {
    color: '#5B7E92',
    glyph: <path d="M70 74 L78 80 L86 74 M70 74 V85 H86 V74" stroke="#fff" strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />,
  },
};

const BADGE_T: Transition = {
  duration: 10, times: [0, 0.55, 0.62, 0.7, 0.78, 1],
  repeat: Infinity, ease: 'easeInOut',
};

const ModeBadge: React.FC<{ mode: ModeKey; animated: boolean }> = ({ mode, animated }) => {
  const m = MODE[mode];
  return (
    <motion.g
      style={{ transformOrigin: '78px 79px' }}
      animate={animated ? { rotate: m.spin ? [0, 0, 0, 12, 0, 0] : [0, 0, -5, 0, 0] } : undefined}
      transition={animated ? { ...BADGE_T, duration: m.spin ? 12 : 10 } : undefined}
    >
      <circle cx="78" cy="79" r="16" fill={m.color} />
      {m.glyph}
    </motion.g>
  );
};

/* ── 组装 ─────────────────────────────────────────────────── */
interface RenderOptions {
  expression: string;
  staticMode?: boolean;
  mode?: ModeKey;
}

const makeMascot = ({ expression, staticMode = false, mode }: RenderOptions) => {
  const Mascot: React.FC<MascotIconProps> = ({ size = 24, className, title }) => {
    const reduced = useReducedMotion();
    const a = !staticMode && !reduced;
    const expr = EXPRESSIONS[expression];
    const pose = MOTION[expr.motion];

    return (
      <motion.svg
        width={size} height={size} viewBox="0 0 100 100" fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={className}
        role={title ? 'img' : undefined}
        aria-label={title}
        aria-hidden={title ? undefined : true}
        focusable="false"
      >
        <motion.g
          style={{ transformOrigin: '50px 52px' }}
          animate={a ? pose.animate : undefined}
          transition={a ? pose.transition : undefined}
        >
          <g transform={mode ? 'translate(-3 -5) scale(0.88)' : undefined}>
            <MascotBase ears={expr.ears} animated={a}>
              <motion.g
                animate={a ? { x: [0, 0, 0.9, -0.6, 0, 0] } : undefined}
                transition={a ? GAZE_T : undefined}
              >
                {expr.face(a)}
              </motion.g>
            </MascotBase>
          </g>
        </motion.g>
        {mode && <ModeBadge mode={mode} animated={a} />}
      </motion.svg>
    );
  };
  Mascot.displayName = `Mascot(${expression}${staticMode ? ':static' : ''}${mode ? `:${mode}` : ''})`;
  return Mascot;
};

/* ── 动画表情（12） ───────────────────────────────────────── */
export const MascotHappy = makeMascot({ expression: 'happy' });
export const MascotCurious = makeMascot({ expression: 'curious' });
export const MascotSleepy = makeMascot({ expression: 'sleepy' });
export const MascotSurprised = makeMascot({ expression: 'surprised' });
export const MascotCool = makeMascot({ expression: 'cool' });
export const MascotThinking = makeMascot({ expression: 'thinking' });
export const MascotExcited = makeMascot({ expression: 'excited' });
export const MascotLove = makeMascot({ expression: 'love' });
export const MascotStarstruck = makeMascot({ expression: 'starstruck' });
export const MascotSad = makeMascot({ expression: 'sad' });
export const MascotWink = makeMascot({ expression: 'wink' });
export const MascotDizzy = makeMascot({ expression: 'dizzy' });

/** 兼容旧导入名 */
export const MascotIcon = MascotHappy;

/* ── 静态表情（12）：同一渲染器，只是不挂动画 ─────────────── */
export const MascotHappyStatic = makeMascot({ expression: 'happy', staticMode: true });
export const MascotCuriousStatic = makeMascot({ expression: 'curious', staticMode: true });
export const MascotSleepyStatic = makeMascot({ expression: 'sleepy', staticMode: true });
export const MascotSurprisedStatic = makeMascot({ expression: 'surprised', staticMode: true });
export const MascotCoolStatic = makeMascot({ expression: 'cool', staticMode: true });
export const MascotThinkingStatic = makeMascot({ expression: 'thinking', staticMode: true });
export const MascotExcitedStatic = makeMascot({ expression: 'excited', staticMode: true });
export const MascotLoveStatic = makeMascot({ expression: 'love', staticMode: true });
export const MascotStarstruckStatic = makeMascot({ expression: 'starstruck', staticMode: true });
export const MascotSadStatic = makeMascot({ expression: 'sad', staticMode: true });
export const MascotWinkStatic = makeMascot({ expression: 'wink', staticMode: true });
export const MascotDizzyStatic = makeMascot({ expression: 'dizzy', staticMode: true });

/* ── 模式图标（6）：正方形构图 + 右下角小徽章 ─────────────── */
export const MascotGeneral = makeMascot({ expression: 'happy', mode: 'general' });
export const MascotPPT = makeMascot({ expression: 'happy', mode: 'ppt' });
export const MascotWebsite = makeMascot({ expression: 'happy', mode: 'website' });
export const MascotBigData = makeMascot({ expression: 'happy', mode: 'bigdata' });
export const MascotVideo = makeMascot({ expression: 'happy', mode: 'video' });
export const MascotEmail = makeMascot({ expression: 'happy', mode: 'email' });
