/**
 * 上下文压缩提醒岛。
 *
 * 背景：对话超过阈值后，后端 ContextCompressionMiddleware 会把更早的对话
 * 总结成摘要（保留要点、丢掉细节）。用户往往在几轮之后才发现"它忘了前面
 * 说的"——这个岛把压缩发生的那一刻变成一次 alert 提示，并展示真实的
 * 摘要预览，让"为什么忘了"有据可查。
 *
 * 数据是真实的：`session.contextCompressed` / `session.summary` 由后端随
 * 每轮结束的会话状态回传（useChatStream 已存入 session）。
 *
 * alert 依据（skill §2）：压缩是用户必须知道的转折——模型对早期细节的
 * 记忆变了。常规完成不 alert，这个和失败同级。
 *
 * 翻转检测的细节：只在「当前会话」的 contextCompressed 从 false 变 true
 * 时提醒一次；切换会话时重置基线，避免加载一个本就压缩过的旧会话时误报。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { MessageGlyph } from '@/components/islandcn/glyphs';
import { SensorRow } from '@/components/islandcn/island-layout';
import {
  ContextLabel,
  ExpandedSubtitle,
  ExpandedTitle,
  TitleStack,
} from '@/components/islandcn/island-text';
import { islandAccent, islandInk } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useChatStore } from '@/stores/chatStore';

const ACCENT = islandAccent.purple;

export const ContextCompressedIsland: React.FC = () => {
  const sessionId = useChatStore((s) => s.currentSessionId);
  const session = useChatStore((s) => s.sessions.find((x) => x.id === s.currentSessionId));
  const compressed = session?.contextCompressed ?? false;
  const summary = session?.summary ?? null;

  const [armed, setArmed] = React.useState(false);
  // 基线：上一个观察到的压缩状态。切会话时重置为当前值（旧会话可能本就压缩过）。
  const baselineRef = React.useRef<boolean>(compressed);

  React.useEffect(() => {
    baselineRef.current = compressed;
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    const flipped = baselineRef.current === false && compressed === true;
    baselineRef.current = compressed;
    if (!flipped) return;
    setArmed(true);
    const timer = window.setTimeout(() => setArmed(false), 6000);
    return () => window.clearTimeout(timer);
  }, [compressed, sessionId]);

  if (!armed) return null;
  return <CompressedActivity summary={summary} />;
};

const CompressedActivity: React.FC<{ summary: string | null }> = ({ summary }) => {
  // 摘要原文可能很长，展开视图取首行预览（ExpandedSubtitle 自带超宽省略）
  const preview = (summary ?? '').split('\n').find((line) => line.trim()) ?? '更早的对话已总结为要点';
  const snippet = preview.length > 90 ? `${preview.slice(0, 90)}…` : preview;

  useActivity(
    () => ({
      id: 'context-compressed',
      group: 'context',
      label: '上下文已压缩，更早的对话已总结为要点',
      alert: true,
      compact: {
        leading: <Glyph icon={MessageGlyph} color={ACCENT} />,
      },
      minimal: <Glyph icon={MessageGlyph} color={ACCENT} />,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={MessageGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>上下文压缩</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottomLike>
            <TitleStack
              title={<ExpandedTitle>上下文已压缩</ExpandedTitle>}
              subtitle={
                <ExpandedSubtitle color={islandInk.secondary}>{snippet}</ExpandedSubtitle>
              }
            />
            <ExpandedSubtitle color={islandInk.tertiary}>
              要点已保留，更早的细节不在模型记忆里
            </ExpandedSubtitle>
          </ExpandedBottomLike>
        ),
      },
    }),
    [snippet],
  );

  return null;
};

/** 简单纵向排布（与 ExpandedBottom 同款列布局，但不需要内嵌进度条）。 */
const ExpandedBottomLike: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ display: 'grid', gap: 4, minWidth: 0 }}>{children}</div>
);
