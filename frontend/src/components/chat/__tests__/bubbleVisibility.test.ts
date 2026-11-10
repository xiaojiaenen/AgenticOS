/**
 * 回归：气泡可见性判据。
 *
 * 这里锁住两次互相打脸的回归 —— 都是「修 A 弄坏 B」，且症状只在特定
 * 时序下出现，手点很难覆盖。
 *
 * 1. **空气泡**：原条件末尾 `|| (!hasPptArtifact && !hasWebsiteArtifact)`
 *    恒真 → 停止后每条空 assistant 都画一只空泡。
 * 2. **工具不显示**：去掉上述条件后，正文为空的 assistant 不画气泡 ——
 *    但 `LiveToolCall` / `OrderedAssistantContent` 都挂在气泡**内部**。
 *    网站/PPT 智能体「先调工具、后出文字」，流式早期正文为空，
 *    工具调用完全不可见，直到模型吐字才「突然」冒出来。
 */
import { describe, expect, it } from 'vitest';
import { shouldRenderBubbleFor } from '../ChatMessage';

const base = {
  isTyping: false,
  isUser: false,
  hasVisibleText: false,
  hasReasoning: false,
  isStreaming: false,
  hasToolCalls: false,
};

describe('shouldRenderBubbleFor', () => {
  it('流式中 + 有工具调用 + 无正文 → 画（工具卡片在气泡内，不画就看不见）', () => {
    expect(
      shouldRenderBubbleFor({ ...base, isStreaming: true, hasToolCalls: true }),
    ).toBe(true);
  });

  it('停止后 + 有工具调用 + 无正文 → 不画（避免空气泡回归）', () => {
    expect(
      shouldRenderBubbleFor({ ...base, isStreaming: false, hasToolCalls: true }),
    ).toBe(false);
  });

  it('完全空的消息 → 不画', () => {
    expect(shouldRenderBubbleFor(base)).toBe(false);
  });

  it('有正文 → 画', () => {
    expect(shouldRenderBubbleFor({ ...base, hasVisibleText: true })).toBe(true);
  });

  it('有思考无正文 → 画（思考是可见内容）', () => {
    expect(shouldRenderBubbleFor({ ...base, hasReasoning: true })).toBe(true);
  });

  it('用户消息 → 画（哪怕内容为空）', () => {
    expect(shouldRenderBubbleFor({ ...base, isUser: true })).toBe(true);
  });

  it('打字指示器 → 画', () => {
    expect(shouldRenderBubbleFor({ ...base, isTyping: true })).toBe(true);
  });

  it('流式中但没有任何工具调用 → 不画（等第一段文字）', () => {
    expect(shouldRenderBubbleFor({ ...base, isStreaming: true })).toBe(false);
  });
});
