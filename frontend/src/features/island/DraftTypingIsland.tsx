/**
 * 「正在输入」岛。
 *
 * 用户在输入框里打字时，原本岛上是一片黑（没有任何活动）—— 而现在有了这个岛，
 * 输入框有草稿、且当前没有 AI 在跑的时候，胶囊会亮起一个笔尖 + 字数，
 * 让"我在写"这件事也有反馈。
 *
 * 为什么只显示字数而不是原文：胶囊空间只有 ~72px（15pt 下 4 个汉字），
 * 草稿可能很长；而且内容本身就在输入框里，岛只需要表达"在写、写了多少"。
 *
 * 为什么在运行中不显示：AI 跑起来时岛上已经有 `agent-run` 活动（优先级更高），
 * 而且用户此时大概率没在打字。用 priority 让运行态覆盖输入态，避免"两个活动
 * 抢一个胶囊"的视觉混乱。
 *
 * 数据源：`chatStore.inputValue`（ChatMainArea 已经把输入框绑到它上面），
 * 是真实的用户草稿，不是演示数据。
 */
import * as React from 'react';

import { Glyph } from '@/components/islandcn/glyph';
import { PencilGlyph } from '@/components/islandcn/glyphs';
import { ExpandedBottom, SensorRow } from '@/components/islandcn/island-layout';
import {
  CompactText,
  ContextLabel,
  ExpandedSubtitle,
  ExpandedValue,
  NumberText,
} from '@/components/islandcn/island-text';
import { islandAccent, islandInk } from '@/components/islandcn/theme';
import { useActivity } from '@/components/islandcn/use-activity';
import { useChatStore } from '@/stores/chatStore';

const ACCENT = islandAccent.blue;

/** 草稿少于这个长度不算"在写"（避免单个字符就点亮胶囊）。 */
const MIN_CHARS = 2;

export const DraftTypingIsland: React.FC = () => {
  const inputValue = useChatStore((s) => s.inputValue);
  const phase = useChatStore((s) => s.runStatus.phase);

  // AI 在跑的时候不抢胶囊（运行岛 priority 更高，这里直接不挂更干净：
  // 高优先级活动会顶掉它，但频繁挂/卸会触发多余的转场动画）
  const running = phase !== 'idle' && phase !== 'done' && phase !== 'error';

  const trimmed = inputValue.trim();
  if (running || trimmed.length < MIN_CHARS) return null;
  return <TypingActivity chars={trimmed.length} />;
};

const TypingActivity: React.FC<{ chars: number }> = ({ chars }) => {
  useActivity(
    () => ({
      id: 'draft-typing',
      group: 'draft',
      // 输入态不该抢注意力：优先级低于所有任务类活动
      priority: -1,
      label: `正在输入，已写 ${chars} 字`,
      compact: {
        leading: <Glyph icon={PencilGlyph} color={ACCENT} />,
        // "输入 12 字"=70.1px 在 72px 内；三位数会超，封顶 99
        trailing: <CompactText>{`输入 ${Math.min(99, chars)} 字`}</CompactText>,
      },
      minimal: <Glyph icon={PencilGlyph} color={ACCENT} />,
      expanded: {
        leading: (
          <SensorRow glyph={<Glyph icon={PencilGlyph} color={ACCENT} size={18} />}>
            <ContextLabel>正在输入</ContextLabel>
          </SensorRow>
        ),
        bottom: (
          <ExpandedBottom gap={4}>
            <ExpandedValue>
              <NumberText value={chars} />
              <span style={{ fontSize: 15 }}>字</span>
            </ExpandedValue>
            <ExpandedSubtitle color={islandInk.secondary}>
              草稿还没发送 · 按回车开始对话
            </ExpandedSubtitle>
          </ExpandedBottom>
        ),
      },
    }),
    [chars],
  );

  return null;
};
