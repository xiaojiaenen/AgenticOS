/**
 * 后端消息 → 前端消息的纯映射。
 *
 * 从 agentService.getSessionMessages 抽出来独立成模块：这段逻辑是
 * "会话刷新/重载后能看到什么"的唯一入口，必须是可单测的纯函数 ——
 * 之前内联在请求函数里，历史加载的回归（如图表刷新后消失）只能靠
 * 手工点页面才能发现。
 */
import type { Message } from '../types';

/** 后端消息原始格式 */
export type BackendMessage = {
  role: string;
  content: string;
  tool_calls?: Array<{ id?: string; name: string; arguments?: Record<string, unknown> }>;
  tool_call_id?: string;
  name?: string;
  metadata?: Record<string, unknown>;
};

/**
 * 数据图表消息的落库/下发格式（chart_events.push_chart 的产物）：
 * ``{version, chart: {title, option}}``。前端 chartMessages 类型是
 * ``{title?, option}``，这里统一解包，并兼容已是扁平结构的旧数据。
 *
 * 为什么导出：SSE 实时路径（agentService 的 chart 事件）和会话恢复路径
 * （mapBackendMessages）拿到的是**同一份后端格式**，解包必须只有这一处 ——
 * 只修一边就会出现「实时是空白卡片、刷新后反而正常」这种互相矛盾的现场。
 */
export function unwrapChartMessage(item: unknown): { title?: string; option: unknown } | null {
  if (!item || typeof item !== 'object') return null;
  const wrapped = item as { chart?: { title?: string; option?: unknown }; title?: string; option?: unknown };
  if (wrapped.chart && typeof wrapped.chart === 'object') {
    return { title: wrapped.chart.title, option: wrapped.chart.option };
  }
  if ('option' in wrapped) return { title: wrapped.title, option: wrapped.option };
  return null;
}

export function mapBackendMessages(raw: BackendMessage[]): Message[] {
  const messages: Message[] = [];
  // 按 tool_call_id 分组 tool 消息
  const toolResultsMap = new Map<string, BackendMessage[]>();

  for (const msg of raw) {
    if (msg.role === 'tool' && msg.tool_call_id) {
      const existing = toolResultsMap.get(msg.tool_call_id) || [];
      existing.push(msg);
      toolResultsMap.set(msg.tool_call_id, existing);
    }
  }

  for (const msg of raw) {
    if (msg.role === 'system') continue; // 跳过 system prompt
    if (msg.role === 'tool') continue;   // tool 结果合并到 assistant 的 toolCalls 中

    if (msg.role === 'user') {
      messages.push({
        id: `backend-${messages.length}`,
        role: 'user',
        text: msg.content || '',
      });
    } else if (msg.role === 'assistant') {
      const toolCalls: import('../types').ToolCall[] | undefined = msg.tool_calls?.map((tc) => {
        const resultMsg = toolResultsMap.get(tc.id || '');
        return {
          id: tc.id,
          name: tc.name,
          status: 'success' as const,
          arguments: tc.arguments,
          result: resultMsg?.map(r => r.content).join('\n') || undefined,
        };
      });
      const metadata = (msg as { metadata?: Record<string, unknown> }).metadata;

      // A2UI 界面消息随助手消息持久化在 metadata.a2ui 里（后端落库时挂上的）。
      // 取回来才能重载会话后继续看到界面 —— 之前只在内存里，刷新即失。
      const a2uiRaw = metadata?.a2ui;
      const a2uiMessages = Array.isArray(a2uiRaw)
        ? (a2uiRaw as import('../types').A2uiMessagePayload[])
        : undefined;

      // 图表走独立通道：metadata.chart 里是 {version, chart:{title,option}} 序列。
      // 之前这里只恢复了 A2UI，图表刷新后消失（用户看到的"图表不见了"的
      // 第二种形态 —— 出图了，但刷新一次就没了）。
      const chartRaw = metadata?.chart;
      const chartMessages = Array.isArray(chartRaw)
        ? chartRaw
            .map(unwrapChartMessage)
            .filter((c): c is { title?: string; option: unknown } => c !== null)
        : undefined;

      messages.push({
        id: `backend-${messages.length}`,
        role: 'model',
        text: msg.content || '',
        toolCalls: toolCalls && toolCalls.length > 0 ? toolCalls : undefined,
        a2uiMessages,
        chartMessages: chartMessages && chartMessages.length > 0 ? chartMessages : undefined,
      });
    }
  }
  return messages;
}
