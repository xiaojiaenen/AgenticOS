import React, { useMemo } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { ChatMessage } from './ChatMessage';
import { ChatSuggestions } from './ChatSuggestions';
import { Artifact, Message } from '../../types';
import { getStoredUser } from '../../services/authService';

// 超过该阈值的消息列表启用 react-virtuoso 虚拟化：长会话逐条渲染
// ReactMarkdown 成本高；短列表走原路径，避免虚拟化带来的行为差异
const VIRTUALIZE_THRESHOLD = 50;

// 虚拟化模式的合成尾项：承载打字指示器与 messagesEndRef
const FOOTER_ITEM = { id: '__messages_footer__' } as unknown as Message;

const sanitizedCache = new WeakMap<Message, Message>();

function sanitizeForNonAdmin(message: Message): Message {
  if (sanitizedCache.has(message)) return sanitizedCache.get(message)!;
  const sanitized: Message = {
    ...message,
    reasoningText: undefined,
    // 保留工具名称和状态，隐藏参数和结果
    toolCalls: message.toolCalls?.map((tc) => ({
      id: tc.id,
      name: tc.name,
      status: tc.status,
      // 不暴露参数、结果、approvalId 等细节
    })),
  };
  sanitizedCache.set(message, sanitized);
  return sanitized;
}

interface MessagesListProps {
  currentSession: { messages: Message[] } | undefined;
  isLoading: boolean;
  wideLayout?: boolean;
  searchQuery: string;
  activeMatchId: string | null;
  onSend: (text: string) => void;
  onSuggestionClick: (text: string) => void;
  onOpenArtifact: (artifact: Artifact) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  /** 虚拟化模式下的滚动容器（ChatMainArea 的 scrollRef 绑定节点） */
  scrollParent?: HTMLDivElement | null;
  /** 虚拟化模式下暴露 Virtuoso 句柄，供搜索跳转 scrollToIndex 回退 */
  virtuosoRef?: React.MutableRefObject<VirtuosoHandle | null>;
}

export const MessagesList = React.memo<MessagesListProps>(({
  currentSession,
  isLoading,
  wideLayout = false,
  searchQuery,
  activeMatchId,
  onSend,
  onSuggestionClick,
  onOpenArtifact,
  messagesEndRef,
  scrollParent,
  virtuosoRef,
}) => {
  const isAdmin = getStoredUser()?.role === 'admin';
  const messages = currentSession?.messages;
  const displayMessages = useMemo(() => {
    if (isAdmin || !messages) return messages;
    return messages.map((message) => sanitizeForNonAdmin(message));
  }, [messages, isAdmin]);

  if (!currentSession || !messages) {
    return <ChatSuggestions onSelect={onSuggestionClick} />;
  }

  const lastMessage = messages[messages.length - 1];
  const showTyping = isLoading && !(lastMessage?.role === 'model');
  const streamingMessageId = isLoading && lastMessage?.role === 'model' ? lastMessage.id : null;

  const renderMessage = (message: Message, idx: number) => (
    <ChatMessage
      message={message}
      index={idx}
      isStreaming={message.id === streamingMessageId}
      wideLayout={wideLayout}
      isAdmin={isAdmin}
      searchQuery={searchQuery}
      activeMatchId={activeMatchId}
      onOpenArtifact={onOpenArtifact}
      onA2uiAction={handleA2uiAction}
    />
  );

  /**
   * A2UI 交互组件被点击时，把 action 转成一条用户消息交给智能体。
   *
   * 不新增后端接口：action 的本质是「用户点了什么」，用自然语言描述
   * 交给模型最直接 —— 它手里有上下文，能自己决定下一步（查数据、
   * 重新渲染、或只是确认）。之前这个回调根本没传，所以点按钮毫无反应。
   */
  const handleA2uiAction = (action: Record<string, unknown>) => {
    // 实测结构（Playwright 抓的真实 payload）：
    //   {name, surfaceId, sourceComponentId, timestamp, context}
    // name 在顶层 —— 之前按 {event:{name}} 解析，所以永远取不到动作名。
    const raw = action as {
      name?: unknown;
      surfaceId?: unknown;
      sourceComponentId?: unknown;
      context?: unknown;
      dataModel?: unknown;
    };
    const name = typeof raw.name === 'string' ? raw.name : '';
    const surface = typeof raw.surfaceId === 'string' ? raw.surfaceId : '';
    const source = typeof raw.sourceComponentId === 'string' ? raw.sourceComponentId : '';
    const data = (raw.context ?? raw.dataModel) as Record<string, unknown> | undefined;

    const parts: string[] = [];
    if (name) {
      parts.push(`我点击了界面上的「${name}」按钮`);
    } else {
      parts.push('我点击了界面上的一个按钮');
    }
    if (surface) parts.push(`（界面 ${surface}${source ? ` / ${source}` : ''}）`);

    // 附带当前表单/绑定值，让智能体知道用户此刻填了什么
    if (data && typeof data === 'object' && Object.keys(data).length > 0) {
      parts.push(`当前数据：${JSON.stringify(data)}`);
    }
    onSend(parts.join(''));
  };

  const footer = (
    <>
      {showTyping && (
        <div role="status" aria-live="polite" aria-label="AI 正在输入">
          <ChatMessage isTyping={true} index={messages.length} wideLayout={wideLayout} />
        </div>
      )}
      <div ref={messagesEndRef} />
    </>
  );

  // 长会话：虚拟化渲染（customScrollParent 挂在外层滚动容器上，
  // Chat.tsx 的 scrollToBottom 仍直接滚动该容器，行为不变）。
  // 打字指示器/end 标记作为合成尾项渲染，避免 components.Footer 内联
  // 组件在流式期间每帧重挂载。
  if (scrollParent && virtuosoRef && messages.length > VIRTUALIZE_THRESHOLD) {
    const base = displayMessages ?? messages;
    const items = [...base, FOOTER_ITEM];
    return (
      <Virtuoso
        ref={(v) => { virtuosoRef.current = v; }}
        customScrollParent={scrollParent}
        data={items}
        computeItemKey={(_, message) => message.id}
        initialTopMostItemIndex={items.length - 1}
        increaseViewportBy={{ top: 800, bottom: 1200 }}
        itemContent={(idx, message) => (
          message.id === FOOTER_ITEM.id
            ? <div className="pt-1 pb-4">{footer}</div>
            : <div className="pb-5">{renderMessage(message, idx)}</div>
        )}
      />
    );
  }

  return (
    <div className="space-y-5 pb-4">
      {(displayMessages ?? messages).map((message, idx) => (
        <React.Fragment key={message.id}>
          {renderMessage(message, idx)}
        </React.Fragment>
      ))}
      {footer}
    </div>
  );
});
