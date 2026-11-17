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
import { useSecondTick, useTieredTick } from './secondTicker';

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

/** 「你回来啦」停留时长（毫秒）：够看清、又不占住时钟太久。 */
const WELCOME_BACK_MS = 4000;

/**
 * 离开超过这个时长才算"真离开"（毫秒）。
 * 切一下标签页立刻回来看不该触发问候 —— 那更接近误触，不是"回来"。
 */
const AWAY_THRESHOLD_MS = 1500;

/**
 * 标签页可见性。
 *
 * 用户不在这个标签页时，岛**什么都不显示**（省电、也不在后台瞎动）；
 * 切回来时先亮一句"你回来啦"，几秒后自动回到时钟。
 *
 * 用 `visibilitychange` 而不是 `window.blur`：切到浏览器另一个标签、最小化
 * 窗口都会触发 visibilitychange，而 blur 在点页面里别的输入框时也会触发，
 * 那样用户只是在页面内点了一下就被判定为"离开了"。
 */
function useTabPresence() {
  // hidden 的初值取当前状态：深链直接打开一个后台标签时不该先亮一下再灭
  const [hidden, setHidden] = React.useState(
    () => typeof document !== 'undefined' && document.visibilityState === 'hidden',
  );
  const [justReturned, setJustReturned] = React.useState(false);
  const [awayMs, setAwayMs] = React.useState(0);
  const hiddenAtRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    const onVisibility = () => {
      const nowHidden = document.visibilityState === 'hidden';
      setHidden(nowHidden);
      if (nowHidden) {
        hiddenAtRef.current = Date.now();
        setJustReturned(false);
        return;
      }
      // 回到前台：离开够久才打招呼
      const leftAt = hiddenAtRef.current;
      hiddenAtRef.current = null;
      if (leftAt !== null) {
        const away = Date.now() - leftAt;
        if (away >= AWAY_THRESHOLD_MS) {
          setAwayMs(away);
          setJustReturned(true);
        }
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  // 问候几秒后自动收起
  React.useEffect(() => {
    if (!justReturned) return;
    const timer = window.setTimeout(() => setJustReturned(false), WELCOME_BACK_MS);
    return () => window.clearTimeout(timer);
  }, [justReturned]);

  return { hidden, justReturned, awayMs };
}

export const IdleClockIsland: React.FC = () => {
  const phase = useChatStore((s) => s.runStatus.phase);
  const inputValue = useChatStore((s) => s.inputValue);
  const island = useIsland();
  const { hidden, justReturned, awayMs } = useTabPresence();

  const expanded = island.presentation === 'expanded';

  // 走时粒度跟着可见精度走：展开时按秒（用户正在看秒），收起时按分钟
  // （胶囊只显示 HH:MM，每秒重渲染没有任何视觉收益，却会把岛引擎按需静止
  // 的帧循环一直叫醒 —— 静止页面上白跑 60fps）。
  const secondTick = useSecondTick(expanded);
  const minuteTick = useTieredTick(60);
  const now = React.useMemo(
    () => new Date((expanded ? secondTick : minuteTick) * 1000),
    [expanded, secondTick, minuteTick],
  );

  // 用户不在这个标签页 → 岛上什么都不显示
  if (hidden) return null;

  // 让位判断：
  // - AI 在跑（运行岛已占胶囊）
  // - 草稿 ≥2 字（输入岛已占胶囊）
  // - 有其它活动（导出/上传/发布/压缩提醒）—— 用引擎的活动列表判断，
  //   这样以后新增的岛不需要来这里登记
  const drafting = inputValue.trim().length >= 2;
  const othersRunning = island.activities.some((a) => a.id !== 'idle-clock' && a.id !== 'welcome-back');
  if (BUSY_PHASES.has(phase) || drafting || othersRunning) return null;

  // 刚回到前台：先打一句招呼（几秒后自动回到时钟）
  if (justReturned) return <WelcomeBackActivity now={now} awayMs={awayMs} />;

  // 展开态才需要秒级刷新（收起时只显示到分钟，见 ClockActivity 的注释）
  return <ClockActivity now={now} expanded={expanded} />;
};

/**
 * "你回来啦"短提示。
 *
 * 不 alert：用户刚回来，没必要抢注意力；它自己 4 秒后让位给时钟。
 * 展开视图里顺带给出离开时长，让这句问候有实感（"离开了 12 分钟"）。
 */
const WelcomeBackActivity: React.FC<{ now: Date; awayMs: number }> = ({ now, awayMs }) => {
  const time = clockText(now);
  const away = formatAway(awayMs);

  useActivity(
    () => ({
      id: 'welcome-back',
      // 比时钟略高，确保回到前台那一刻是它先出现
      priority: -9,
      label: `欢迎回来，${away}没见了，现在是 ${time}`,
      compact: {
        leading: <Glyph icon={TimerGlyph} color={ACCENT} />,
        // "你回来啦"=60px 在 72px 内
        trailing: <CompactText>你回来啦</CompactText>,
      },
      minimal: <CompactText>你回来啦</CompactText>,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={TimerGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>欢迎回来</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={4}>
            <TitleStack
              title={<ExpandedTitle>你回来啦</ExpandedTitle>}
              subtitle={
                <ExpandedSubtitle color={islandInk.secondary}>
                  {away}没见 · 现在 {time}
                </ExpandedSubtitle>
              }
            />
          </ExpandedBottom>
        ),
      },
    }),
    [time, away],
  );

  return null;
};

/** 把离开时长说成人话（展开视图里用，不受宽度限制）。 */
function formatAway(ms: number): string {
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return `${Math.max(1, Math.round(ms / 1000))} 秒`;
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} 小时` : `${hours} 小时 ${rest} 分钟`;
}

/** 时分（紧凑态用；不含秒，一分钟才变一次）。 */
const clockShort = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

/**
 * 时钟只在需要时才秒级刷新。
 *
 * 性能考量（这条是实测出来的，不是为了好看）：岛引擎的帧循环是**按需静止**的
 * —— `surface.tsx` 在所有弹簧静止后会 `unsubscribe()` 掉 rAF。但每次 activity
 * update 都会把它重新叫醒跑 300–500ms。如果紧凑态每秒 update 一次，就等于让
 * 一个静止页面持续以 60fps 跑近一半的时间，纯属空转。
 *
 * 所以：紧凑胶囊只显示 `HH:MM`（每分钟变一次），秒级跳动只在**展开视图**里
 * 出现 —— 那时用户正盯着它看，这点开销是值得的。
 */
const ClockActivity: React.FC<{ now: Date; expanded: boolean }> = ({ now, expanded }) => {
  // 展开时用带秒的完整时间，收起时用时分（宽度也更省：37px vs 58.7px）
  const full = clockText(now);
  const time = expanded ? full : clockShort(now);
  const greeting = greetingFor(now.getHours());
  const date = fullDate(now);

  useActivity(
    () => ({
      id: 'idle-clock',
      // 最低优先级：任何真实任务都该顶掉它
      priority: -10,
      label: `${greeting}，现在是 ${full}`,
      compact: {
        leading: <Glyph icon={TimerGlyph} color={ACCENT} />,
        trailing: <CompactText style={tabularFigures}>{time}</CompactText>,
      },
      minimal: <CompactText style={tabularFigures}>{time}</CompactText>,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={TimerGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>{greeting}</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={4}>
            <TitleStack
              title={<ExpandedTitle>{full}</ExpandedTitle>}
              subtitle={<ExpandedSubtitle color={islandInk.secondary}>{date}</ExpandedSubtitle>}
            />
            <ExpandedSubtitle color={islandInk.tertiary}>
              随时可以开始 · 在下面说说你想做什么
            </ExpandedSubtitle>
          </ExpandedBottom>
        ),
      },
    }),
    // 关键：deps 里**不能**有 full（含秒）——否则收起状态下每秒都会重建 activity，
    // 把引擎按需静止的帧循环一直叫醒。展开时才需要秒级刷新。
    [time, expanded, greeting, date],
  );

  return null;
};
