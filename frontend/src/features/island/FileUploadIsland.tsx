/**
 * 文件上传岛。
 *
 * 真实的长时间等待：内网环境传一个几十 MB 的附件要几十秒，期间唯一反馈
 * 是输入框下的一行小字（用户滚上去就看不见），岛补上全局可见的进度。
 *
 * 进度是**真实字节**：uploadFile 走 XHR 的 upload.onprogress（fetch 没有
 * 上行进度事件），多个文件并行上传时显示聚合比例。
 *
 * 映射（skill §3 三问）：
 * - 是什么：UploadGlyph（云上传）
 * - 一眼要看什么：聚合百分比（数字在动 = 在传）
 * - 展开看什么：文件数 + 已传/总大小（MB）+ 确定进度条
 *
 * 不 alert：常规进度不该抢注意力；完成由 AgentRunIsland 接棒（上传完
 * 立刻进入模型运行）。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { UploadGlyph } from '@/components/islandcn/glyphs';
import { BottomBar, ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  ExpandedValue,
  NumberText,
} from '@/components/islandcn/island-text';
import { LinearProgress } from '@/components/islandcn/linear-progress';
import { islandAccent, islandInk, islandMono } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useFileUploadStore } from '@/features/island/uploadStore';

const ACCENT = islandAccent.blue;

const mb = (bytes: number) => `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

export const FileUploadIsland: React.FC = () => {
  const files = useFileUploadStore((s) => s.files);
  if (!files || files.length === 0) return null;
  return <UploadActivity files={files} />;
};

const UploadActivity: React.FC<{ files: { name: string; total: number; loaded: number }[] }> = ({
  files,
}) => {
  const totalBytes = files.reduce((sum, f) => sum + f.total, 0);
  const loadedBytes = files.reduce((sum, f) => sum + f.loaded, 0);
  // 聚合进度：clamp 防止除零/溢出（store 里 total 至少为 1，这里是双保险）
  const fraction = totalBytes > 0 ? Math.min(1, loadedBytes / totalBytes) : 0;
  const percent = Math.round(fraction * 100);

  useActivity(
    () => ({
      id: 'file-upload',
      label: `正在上传 ${files.length} 个文件，${percent}%`,
      compact: {
        leading: <Glyph icon={UploadGlyph} color={ACCENT} />,
        // "上传 63%"=67.9px 在 72px 内；"上传 100%"=74.1px 会被裁，
        // 所以封顶 99%（传完这一瞬间立刻切到运行岛，不需要显示 100）
        trailing: <CompactText>{`上传 ${Math.min(99, percent)}%`}</CompactText>,
      },
      minimal: <CompactText>{`上传 ${Math.min(99, percent)}%`}</CompactText>,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={UploadGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>上传文件</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={6}>
            <ExpandedValue>
              <NumberText value={percent} />
              <span style={{ fontFamily: islandMono }}>%</span>
            </ExpandedValue>
            <ExpandedSubtitle color={islandInk.secondary}>
              {files.length} 个文件 ·{' '}
              <span style={{ fontFamily: islandMono }}>
                {mb(loadedBytes)} / {mb(totalBytes)}
              </span>
            </ExpandedSubtitle>
            <BottomBar>
              <LinearProgress value={fraction} color={ACCENT} height={5} />
            </BottomBar>
          </ExpandedBottom>
        ),
      },
    }),
    [files, percent, fraction, loadedBytes, totalBytes],
  );

  return null;
};
