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
  // 已用秒数：用 kit 的 TickingTime 之外，这里自己算一次（activity 的 content
  // 只在依赖变化时重建，所以这里给一个由 25s 刷新的 elapsed 就够 —— 真正的
  // 秒级跳动交给 Text 里的秒数，由我们自己的 interval 驱动，避免整块重渲染）。
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    const update = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  useActivity(
    () => ({
      id: 'ppt-export',
      label: `正在导出 ${title}，已用 ${elapsed} 秒`,
      compact: {
        leading: <Glyph icon={DocumentPlusGlyph} color={ACCENT} />,
        trailing: (
          <CompactText>
            {/* 胶囊只有约 20pt：两位数字刚好（"45"），三位会被裁 */}
            {elapsed < 100 ? `${elapsed}s` : '99+'}
          </CompactText>
        ),
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
