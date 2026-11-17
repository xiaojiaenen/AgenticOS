/**
 * PPTX 导出岛。
 *
 * 这是一次真实的长时间等待：后端要把每页 SVG 转成 DrawingML、打包成
 * .pptx，实测 1–2 分钟，而期间界面上只有按钮转圈、**没有任何进度** ——
 * 用户经常以为卡死了又点一次。
 *
 * 映射（skill §3 三问）：
 * - 是什么：DocumentPlus glyph（在写文件）
 * - 一眼要看什么：已用秒数（TickingTime 自己走，不需要每秒 update）
 * - 展开看什么：文件名 + 已用时间 + 一条"不确定进度"的脉冲条
 *
 * 这里**故意不显示百分比**：后端不回报导出进度，编一个假的 0→100 比
 * 不显示更糟。用一个 indeterminate 的动效表达"在处理"，用时给真实值。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { DocumentPlusGlyph } from '@/components/islandcn/glyphs';
import { BottomBar, ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  TitleStack,
  ExpandedTitle,
} from '@/components/islandcn/island-text';
import { islandAccent, islandInk, islandMono } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { usePptExportStore } from '@/features/island/exportStore';
import { useSecondTick } from './secondTicker';

const ACCENT = islandAccent.purple;

export const PptExportIsland: React.FC = () => {
  const job = usePptExportStore((s) => s.job);
  if (!job) return null;
  return <PptExportActivity title={job.title} startedAt={job.startedAt} />;
};

const PptExportActivity: React.FC<{ title: string; startedAt: number }> = ({
  title,
  startedAt,
}) => {
  // 已用秒数：走共享秒级 ticker（后台标签会停表；同一秒内多个订阅者只更新一次）。
  // 用整秒比较而不是自己 setInterval —— 计时器漂移会产生多余的 activity update，
  // 而每次 update 都会把岛引擎按需静止的帧循环重新叫醒。
  const second = useSecondTick();
  const elapsed = Math.max(0, second - Math.floor(startedAt / 1000));

  useActivity(
    () => ({
      id: 'ppt-export',
      label: `正在导出 ${title}，已用 ${elapsed} 秒`,
      compact: {
        leading: <Glyph icon={DocumentPlusGlyph} color={ACCENT} />,
        // 只写 "45s" 看不出在干什么：加"导出"前缀（"导出 45s"=60.9px，在上限内）
        trailing: <CompactText>{elapsed < 100 ? `导出 ${elapsed}s` : '导出 99+'}</CompactText>,
      },
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={DocumentPlusGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>导出中</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={6}>
            <TitleStack
              title={<ExpandedTitle>{title}</ExpandedTitle>}
              subtitle={
                <ExpandedSubtitle color={islandInk.secondary}>
                  <span style={{ fontFamily: islandMono }}>{elapsed}s</span>
                  {' · '}正在生成本地 .pptx
                </ExpandedSubtitle>
              }
            />
            <BottomBar>
              {/* 后端不回报导出进度，所以这里用不确定态的脉冲条，
                  不编造百分比。 */}
              <IndeterminateBar />
            </BottomBar>
          </ExpandedBottom>
        ),
      },
    }),
    [title, elapsed],
  );

  return null;
};

/** 不确定进度条：一条来回滑动的光条（纯 CSS，不动 island 自己的弹簧）。 */
const IndeterminateBar: React.FC = () => (
  <div className="relative h-[5px] w-full overflow-hidden rounded-full bg-[rgba(255,255,255,0.16)]">
    <div className="island-indeterminate" />
  </div>
);
