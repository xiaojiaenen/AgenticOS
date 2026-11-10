import React from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import {
  MascotHappy, MascotCurious, MascotSleepy, MascotSurprised,
  MascotCool, MascotThinking, MascotExcited, MascotLove,
  MascotStarstruck, MascotSad, MascotWink, MascotDizzy,
} from './MascotIcons';

export interface RandomMascotProps {
  size?: number;
  className?: string;
  /** 表情漫游的基准间隔（毫秒）；传 0 可关闭变化。默认 7000 */
  interval?: number;
}

const FACES: Record<string, React.FC<{ size?: number; className?: string }>> = {
  happy: MascotHappy, curious: MascotCurious, sleepy: MascotSleepy,
  surprised: MascotSurprised, cool: MascotCool, thinking: MascotThinking,
  excited: MascotExcited, love: MascotLove, starstruck: MascotStarstruck,
  sad: MascotSad, wink: MascotWink, dizzy: MascotDizzy,
};

/**
 * 情绪漫游路径：相邻表情之间是自然过渡（开心 → 好奇 → 思考 → …），
 * 而不是每隔几秒突兀地乱跳一个。起点仍然随机，所以多个实例不同步。
 */
const MOOD_PATH = [
  'happy', 'curious', 'thinking', 'happy', 'wink', 'excited',
  'happy', 'sleepy', 'happy', 'starstruck', 'love', 'happy',
  'surprised', 'cool', 'happy', 'dizzy', 'sad', 'curious',
];

export const RandomMascot: React.FC<RandomMascotProps> = ({ size = 24, className, interval = 7000 }) => {
  const reduced = useReducedMotion();
  const [step, setStep] = React.useState(() => Math.floor(Math.random() * MOOD_PATH.length));

  React.useEffect(() => {
    if (!interval || reduced) return;
    let timer: ReturnType<typeof setTimeout>;
    // 间隔带抖动，避免几个背景实例形成整齐划一的节拍
    const tick = () => {
      setStep((s) => (s + 1) % MOOD_PATH.length);
      timer = setTimeout(tick, interval + Math.random() * 3500);
    };
    timer = setTimeout(tick, interval + Math.random() * 2000);
    return () => clearTimeout(timer);
  }, [interval, reduced]);

  const name = MOOD_PATH[step];
  const Face = FACES[name];

  return (
    <div className={className} style={{ position: 'relative', width: size, height: size }}>
      {/* sync（非 wait）：两个表情叠着交叉淡入淡出，切换时背景不会空一拍 */}
      <AnimatePresence>
        <motion.div
          key={name + step}
          className="absolute inset-0"
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 1.02 }}
          transition={{ duration: 0.65, ease: 'easeInOut' }}
        >
          <Face size={size} />
        </motion.div>
      </AnimatePresence>
    </div>
  );
};
