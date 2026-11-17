/**
 * 网站发布岛：多阶段审批链（skill §3 的 "stages" 形态）。
 *
 * 这是本项目里**最长的异步流程**：用户点「发布」→ 提交审批 → 管理员审批
 * → 后端构建静态包 → 上线。全程可能跨几分钟到几小时，用户关掉页面就完全
 * 失去进展感知。
 *
 * 映射（skill §3 三问）：
 * - 是什么：Globe glyph（在发布一个站点）
 * - 一眼要看什么：当前阶段序号（StepProgress 的 2/4）
 * - 展开看什么：站点名 + 当前阶段的人话 + 四段进度条
 *
 * `alert` 只用在两处用户必须知道的转折：审批通过（要开始真正构建）、
 * 上线成功 / 失败。常规阶段推进不 alert（skill §2 明确要求）。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { GlobeGlyph } from '@/components/islandcn/glyphs';
import { BottomBar, ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  ExpandedTitle,
  TitleStack,
} from '@/components/islandcn/island-text';
import { islandAccent, islandInk } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useSiteDeployStore } from '@/features/island/deployStore';
import type { DeployStatus } from '@/services/websiteService';

const ACCENT = islandAccent.green;

/** 四个阶段的人话措辞与序号（0-based 用于算比例）。 */
const STAGES: Record<string, { label: string; index: number; note: string }> = {
  pending: { label: '待审批', index: 0, note: '等待管理员审批' },
  approved: { label: '已批准', index: 1, note: '已批准，排队构建' },
  deploying: { label: '构建中', index: 2, note: '正在打包静态站点' },
  deployed: { label: '已上线', index: 3, note: '站点已可访问' },
  failed: { label: '失败', index: 3, note: '构建失败' },
  rejected: { label: '已拒绝', index: 3, note: '管理员拒绝' },
};

const TOTAL = 4;

export const SiteDeployIsland: React.FC = () => {
  const job = useSiteDeployStore((s) => s.job);
  if (!job) return null;
  return <SiteDeployActivity slug={job.slug} status={job.status} />;
};

const SiteDeployActivity: React.FC<{ slug: string; status: DeployStatus }> = ({
  slug,
  status,
}) => {
  const stage = STAGES[status] ?? STAGES.pending;
  const step = stage.index + 1;
  const isError = status === 'failed' || status === 'rejected';

  useActivity(
    () => ({
      id: 'site-deploy',
      label: `网站 ${slug} ${stage.label}`,
      // 只在两个转折点抢注意力：审批通过、构建失败
      alert: status === 'approved' || isError,
      compact: {
        leading: <Glyph icon={GlobeGlyph} color={isError ? islandAccent.red : ACCENT} />,
        trailing: (
          <CompactText>
            {step}/{TOTAL}
          </CompactText>
        ),
      },
      expanded: {
        leading: (
          <SensorRow
            glyph={
              <Glyph
                icon={GlobeGlyph}
                color={isError ? islandAccent.red : ACCENT}
                size={18}
              />
            }
          >
            <ContextLabel>发布</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={6}>
            <TitleStack
              title={<ExpandedTitle>{slug}</ExpandedTitle>}
              subtitle={
                <ExpandedSubtitle color={islandInk.secondary}>{stage.note}</ExpandedSubtitle>
              }
            />
            <BottomBar>
              <StageBar step={step} error={isError} />
            </BottomBar>
          </ExpandedBottom>
        ),
      },
    }),
    [slug, status, step, stage.label, stage.note, isError],
  );

  return null;
};

/** 四段式阶段条：已完成的段填色，当前段高亮，其余留灰。 */
const StageBar: React.FC<{ step: number; error: boolean }> = ({ step, error }) => (
  <div className="flex w-full gap-[3px]">
    {Array.from({ length: TOTAL }, (_, i) => (
      <div
        key={i}
        className="h-[5px] flex-1 rounded-full"
        style={{
          background:
            i < step
              ? error
                ? islandAccent.red
                : ACCENT
              : islandInk.track,
        }}
      />
    ))}
  </div>
);
