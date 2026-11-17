/**
 * 常驻时钟 / 问候岛。
 *
 * 用户反馈：空闲时岛上什么都没有，一片黑。这里让空闲态也有内容：
 * - 左侧时钟 glyph，右侧走秒的时间（HH:MM:SS，等宽数字避免跳动）
 * - 展开视图：今天的日期 + 时段问候 + 当前会话轮数
 *
 * **为什么是 activity 而不是改引擎的 idle 形态**：引擎把 idle 硬编码成
 * 空内容（`lib/island/layer.tsx` 的 `case "idle": return root(null)`），
 * 改它等于 fork 上游渲染逻辑。用一个 priority 最低的 activity 达到同样
 * 效果，且天然复用引擎的形变/离场动画。
 *
 * **怎么让位**：`deriveScene` 按 priority 排序取前两个活动。本岛 priority=-10，
 * 任何真实任务都能顶掉它。但为了让"让位"在视觉上是干净的（不是两个活动
 * 并排成 minimal 分裂态），这里在检测到其它活动时**直接不挂载** ——
 * 与 DraftTypingIsland 同一套做法。
 *
 * 秒级走时：`useActivity` 的 content 只在 deps 变化时重建，所以用一个
 * 自己 hold 的 interval 每秒推进一次 `now`。这会让岛每秒收到一次 update，
 * 但引擎对同 key 的 update 是原地跨帧更新（不重新挂层），代价可接受。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { TimerGlyph } from '@/components/islandcn/glyphs';
import { ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  ExpandedTitle,
  TitleStack,
  tabularFigures,
} from '@/components/islandcn/island-text';
import { islandInk } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useIsland } from '@/lib/island';
import { useChatStore } from '@/stores/chatStore';

const ACCENT = islandInk.secondary;

const pad = (n: number) => String(n).padStart(2, '0');

/** 时分秒（等宽数字，避免秒数跳动时整块文字左右抖）。 */
const clockText = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;

/** 时段问候 —— 都是 ≤4 汉字（紧凑槽上限 72px：4 汉字 = 60px）。 */
function greetingFor(hour: number): string {
  if (hour < 5) return '夜深了';
  if (hour < 9) return '早上好';
  if (hour < 12) return '上午好';
  if (hour < 14) return '中午好';
  if (hour < 18) return '下午好';
  if (hour < 23) return '晚上好';
  return '夜深了';
}

/** 完整日期（展开视图里用，不受紧凑槽宽度限制）。 */
const fullDate = (d: Date) => {
  const week = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日 ${week}`;
};

/** 有其它活动在跑时必须让位（不能并排成 minimal 分裂态）。 */
const BUSY_PHASES = new Set(['thinking', 'streaming', 'generating_ppt', 'rendering_ppt', 'rendering_website']);

export const IdleClockIsland: React.FC = () => {
  const phase = useChatStore((s) => s.runStatus.phase);
  const inputValue = useChatStore((s) => s.inputValue);
  const island = useIsland();

  // 每秒推进一次，驱动秒级走时
  const [now, setNow] = React.useState(() => new Date());
  React.useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // 让位判断：
  // - AI 在跑（运行岛已占胶囊）
  // - 草稿 ≥2 字（输入岛已占胶囊）
  // - 有其它活动（导出/上传/发布/压缩提醒）—— 用引擎的活动列表判断，
  //   这样以后新增的岛不需要来这里登记
  const drafting = inputValue.trim().length >= 2;
  const othersRunning = island.activities.some((a) => a.id !== 'idle-clock');
  if (BUSY_PHASES.has(phase) || drafting || othersRunning) return null;

  return <ClockActivity now={now} />;
};

const ClockActivity: React.FC<{ now: Date }> = ({ now }) => {
  const time = clockText(now);
  const greeting = greetingFor(now.getHours());
  const date = fullDate(now);

  useActivity(
    () => ({
      id: 'idle-clock',
      // 最低优先级：任何真实任务都该顶掉它
      priority: -10,
      label: `${greeting}，现在是 ${time}`,
      compact: {
        leading: <Glyph icon={TimerGlyph} color={ACCENT} />,
        // "14:32:07"=58.7px 在 72px 内（含秒；不含秒只有 37px，但秒在动才像活的）
        trailing: <CompactText style={tabularFigures}>{time}</CompactText>,
      },
      minimal: (
        <CompactText style={tabularFigures}>{time}</CompactText>
      ),
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={TimerGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>{greeting}</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={4}>
            <TitleStack
              title={<ExpandedTitle>{time}</ExpandedTitle>}
              subtitle={<ExpandedSubtitle color={islandInk.secondary}>{date}</ExpandedSubtitle>}
            />
            <ExpandedSubtitle color={islandInk.tertiary}>
              随时可以开始 · 在下面说说你想做什么
            </ExpandedSubtitle>
          </ExpandedBottom>
        ),
      },
    }),
    [time, greeting, date],
  );

  return null;
};
