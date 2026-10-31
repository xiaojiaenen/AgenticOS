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
  onSend: (text: string, files?: File[], source?: 'composer' | 'a2ui') => void;
  /** A2UI 数据变化（表单输入等），上抛给会话层做跟随刷新 */
  onA2uiDataChange?: (data: Record<string, unknown>, surfaceId?: string) => void;
  /**
   * 读取 A2UI 表单**当前**数据（点击提交时随动作回传）。
   *
   * 为什么要 getter 而不是 state：表单值在用户每次输入后变化，
   * 但组件不该为每个按键重渲染整个消息列表。宿主用 ref 存最新值，
   * 点击时再取一次即可。
   */
  getA2uiData?: () => Record<string, unknown>;
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
  onA2uiDataChange,
  getA2uiData,
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
      onA2uiDataChange={onA2uiDataChange}
    />
  );

  /**
   * A2UI 交互组件被点击时，把 action 转成一条用户消息交给智能体。
   *
   * 不新增后端接口：action 的本质是「用户点了什么」，用自然语言描述
   * 交给模型最直接 —— 它手里有上下文，能自己决定下一步（查数据、
   * 重新渲染、或只是确认）。之前这个回调根本没传，所以点按钮毫无反应。
   *
   * 关键补充：**必须带上表单当前值**。
   * A2UI 的 `action.event.context` 只有在组件里显式写了 context 绑定才有值；
   * render_form 生成的提交按钮没有写，所以 payload.context 恒为空对象 ——
   * 用户填的姓名/级别根本没回传，智能体只能回「你点了提交」。
   * 真实数据在 DataModel 里（ChatMainArea 已经订阅并存在 a2uiDataRef），
   * 这里把它合进动作描述，智能体才拿得到用户输入。
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
    // 优先用 A2UI 自己解出的 context（组件写了绑定时才有）；
    // 否则退回宿主订阅到的整份表单数据（getA2uiData → ChatMainArea 的 ref）。
    const fromAction = (raw.context ?? raw.dataModel) as Record<string, unknown> | undefined;
    const fromForm = getA2uiData?.() ?? {};
    const data: Record<string, unknown> = {};
    for (const src of [fromForm, fromAction]) {
      if (!src || typeof src !== 'object') continue;
      for (const [k, v] of Object.entries(src)) {
        if (k === '__surface') continue;
        if (v === undefined || v === null || v === '') continue;
        data[k] = v;
      }
    }

    const parts: string[] = [];
    if (name) {
      parts.push(`我点击了界面上的「${name}」按钮`);
    } else {
      parts.push('我点击了界面上的一个按钮');
    }
    if (surface) parts.push(`（界面 ${surface}${source ? ` / ${source}` : ''}）`);

    // 附带当前表单/绑定值，让智能体知道用户此刻填了什么
    if (Object.keys(data).length > 0) {
      parts.push(`当前数据：${JSON.stringify(data)}`);
    } else if (name) {
      // 明确告知"没有数据"，避免智能体误以为拿到了空表单
      parts.push('（表单当前没有填写任何内容）');
    }
    // source='a2ui'：绕开输入框的 isLoading 守卫。
    // A2UI 界面是在本轮流式过程中下发的，用户填完点提交时那一轮还没结束，
    // 按 composer 路径会被静默丢弃（表现就是「点提交没反应」）。
    onSend(parts.join(''), undefined, 'a2ui');
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
