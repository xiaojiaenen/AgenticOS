/**
 * 消息有序内容块的维护逻辑（纯函数）。
 *
 * 后端 SSE 事件到达顺序即真实因果顺序，本模块把"文本 / 工具 / 思考"
 * 按到达顺序组织成 `Message.blocks`，渲染层据此按序展示，而不是把三类
 * 内容折叠进三个独立字段。
 *
 * 设计要点：
 * - 每个 text/reasoning 块存**该块自己的累计全文**（不是增量片段），
 *   这样即使块被后续事件打断，块内文本也始终自洽；
 * - 判定"续写同一块 vs 开新块"的规则：新内容以旧内容结尾 → 同块续写；
 *   否则（中间夹了工具调用等）→ 开新块。
 * - 旧消息（无 blocks）用 {@link blocksFromLegacy} 回退生成。
 */
import type { MessageBlock, ToolCall } from '../types';

type AnyBlock = MessageBlock;

function lastBlockOfKind(blocks: AnyBlock[], kind: 'text' | 'reasoning'): AnyBlock | undefined {
  for (let i = blocks.length - 1; i >= 0; i -= 1) {
    if (blocks[i].kind === kind) return blocks[i];
  }
  return undefined;
}

/**
 * 合并一次正文更新。
 * @param blocks 当前块序列
 * @param fullText 本次事件的累计全文
 * @param prevFullText 上一次的累计全文（用于判断是否续写同一块）
 */
export function syncTextBlocks(
  blocks: AnyBlock[],
  fullText: string,
  prevFullText: string,
): AnyBlock[] {
  if (!fullText) return blocks;
  // 续写同一块：新文本以旧文本结尾
  if (prevFullText && fullText.startsWith(prevFullText) && fullText.length > prevFullText.length) {
    const target = lastBlockOfKind(blocks, 'text');
    if (target && target.kind === 'text' && target === blocks[blocks.length - 1]) {
      const next = blocks.slice(0, -1);
      next.push({ kind: 'text', text: fullText });
      return next;
    }
  }
  // 开新块：追加到末尾
  return [...blocks, { kind: 'text', text: fullText }];
}

/** 合并一次思考内容更新（规则同正文）。 */
export function syncReasoningBlocks(
  blocks: AnyBlock[],
  fullReasoning: string,
  prevReasoning: string,
): AnyBlock[] {
  if (!fullReasoning) return blocks;
  if (
    prevReasoning &&
    fullReasoning.startsWith(prevReasoning) &&
    fullReasoning.length > prevReasoning.length
  ) {
    const target = lastBlockOfKind(blocks, 'reasoning');
    if (target && target.kind === 'reasoning' && target === blocks[blocks.length - 1]) {
      const next = blocks.slice(0, -1);
      next.push({ kind: 'reasoning', text: fullReasoning });
      return next;
    }
  }
  return [...blocks, { kind: 'reasoning', text: fullReasoning }];
}

/**
 * 合并工具调用：为**新出现**的调用追加 tool 块（已存在的保持原位）。
 * toolCallId 缺失时用 `${name}#${index}` 兜底，保证 key 稳定唯一。
 */
export function syncToolBlocks(
  blocks: AnyBlock[],
  toolCalls: ToolCall[],
  prevToolCalls: ToolCall[],
): AnyBlock[] {
  const seen = new Set(
    blocks.filter((b): b is Extract<AnyBlock, { kind: 'tool' }> => b.kind === 'tool').map((b) => b.toolCallId),
  );
  const next = [...blocks];
  toolCalls.forEach((call, index) => {
    const id = call.id || `${call.name}#${index}`;
    if (seen.has(id)) return;
    seen.add(id);
    next.push({ kind: 'tool', toolCallId: id });
  });
  return next;
}

export function toolCallIdOf(call: ToolCall, index: number): string {
  return call.id || `${call.name}#${index}`;
}

/**
 * 从旧式三桶消息回退生成块序列：
 * 思考 → 工具（逐个）→ 正文。
 */
export function blocksFromLegacy(input: {
  reasoningText?: string;
  toolCalls?: ToolCall[];
  text: string;
}): AnyBlock[] {
  const blocks: AnyBlock[] = [];
  if (input.reasoningText) blocks.push({ kind: 'reasoning', text: input.reasoningText });
  (input.toolCalls || []).forEach((call, index) => {
    blocks.push({ kind: 'tool', toolCallId: toolCallIdOf(call, index) });
  });
  if (input.text) blocks.push({ kind: 'text', text: input.text });
  return blocks;
}

/** 供渲染层使用：有 blocks 用 blocks，否则回退三桶。 */
export function resolveBlocks(message: {
  blocks?: MessageBlock[];
  reasoningText?: string;
  toolCalls?: ToolCall[];
  text: string;
}): AnyBlock[] {
  if (message.blocks && message.blocks.length > 0) return message.blocks;
  return blocksFromLegacy(message);
}