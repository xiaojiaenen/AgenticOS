import type { Session } from '../types';
import type { AgentSessionListItem } from '../services/agentService';

/** 本地缓存最多保留的会话数（与 useChatSessions 的持久化上限一致） */
export const MAX_SESSIONS = 24;

/**
 * 后端 session 列表项 → 前端 Session 纯转换。
 * messages 置空：消息在选中会话时按需加载（loadSessionMessages）。
 *
 * 标题取自后端 `title`（首条用户消息摘录）。注意：后端的 `summary` 字段是
 * wuwei 上下文压缩摘要，正常运行为空，不能当标题用；早期版本拿它兜底导致
 * 刷新后标题统一变成智能体名（如"通用助手"）。
 */
export function convertBackendSession(s: AgentSessionListItem): Session {
  return {
    id: s.session_id,
    title: s.title || s.summary || '新对话',
    messages: [],
    createdAt: s.created_at ? new Date(s.created_at).getTime() : Date.now(),
    updatedAt: s.updated_at ? new Date(s.updated_at).getTime() : Date.now(),
    summary: s.summary,
    messageCount: s.message_count,
    mode: (s.metadata?.response_mode as Session['mode']) || undefined,
    agentProfileId: (s.metadata?.agent_profile_id as number) ?? undefined,
  };

}

/**
 * 把本地（localStorage 缓存或内存中的）会话信息合并进后端转换结果。
 *
 * - `keepMessagesOnly: true`：仅当本地会话有消息时才覆盖 messages/title/mode/agentProfileId
 *   （loadFromBackend 的缓存合并、refreshSessions 的 prev 合并用这个语义）
 * - `keepMessagesOnly: false`：只要本地存在该会话就覆盖 title/mode/agentProfileId，
 *   messages 仅在本地非空时保留（loadFromBackend 的 prev 合并用这个语义）
 */
export function mergeLocalIntoConverted(
  converted: Session[],
  local: Session[],
  { keepMessagesOnly = false }: { keepMessagesOnly?: boolean } = {},
): Session[] {
  const localMap = new Map(local.map(s => [s.id, s]));
  return converted.map((s) => {
    const existing = localMap.get(s.id);
    if (!existing) return s;
    if (keepMessagesOnly && existing.messages.length === 0) return s;
    const hasMessages = existing.messages.length > 0;
    // 标题以后端为准（首条用户消息摘录）；本地仅在后端还没有真实标题时兜底，
    // 否则旧缓存里的错误标题（如智能体名）会一直粘住
    const backendTitle = s.title && s.title !== '新对话' ? s.title : '';
    return {
      ...s,
      messages: hasMessages ? existing.messages : s.messages,
      title: backendTitle || existing.title || s.title,
      mode: existing.mode || s.mode,
      agentProfileId: existing.agentProfileId ?? s.agentProfileId,
    };
  });
}

/**
 * 后端列表 + 本地未同步会话（尚未到达后端的新建会话）→ 最终会话列表：
 * 本地独有的会话前置保留，整体截断到 MAX_SESSIONS。
 */
export function reconcileBackendWithLocal(converted: Session[], prev: Session[]): Session[] {
  const backendIds = new Set(converted.map(s => s.id));
  const result = [...converted];
  for (const s of prev) {
    if (!backendIds.has(s.id)) {
      result.unshift(s);
    }
  }
  return result.slice(0, MAX_SESSIONS);
}
