import { Message, ToolCall } from '../types';

type AgentServiceOptions = {
  sessionId: string;
  systemPrompt?: string;
  onDelta?: (delta: string, fullText: string) => void;
  onToolCalls?: (toolCalls: ToolCall[]) => void;
  onSessionState?: (state: AgentSessionState) => void;
  signal?: AbortSignal;
};

type StreamResult = {
  sessionId: string;
  text: string;
  toolCalls?: ToolCall[];
  finishReason: string;
  sessionState?: AgentSessionState;
};

type AgentToolCall = {
  id?: string;
  function?: {
    name?: string;
    arguments?: Record<string, unknown>;
  };
};

type AgentToolResult = {
  tool_call_id?: string;
  name?: string;
  status?: ToolCall['status'];
  result?: string;
};

export type AgentSessionState = {
  session_id: string;
  summary?: string | null;
  context_compressed?: boolean;
  storage?: string;
  last_usage?: Record<string, number> | null;
  last_latency_ms?: number | null;
  last_llm_calls?: number | null;
  message_count?: number;
  pending_approvals?: AgentApproval[];
};

export type AgentApproval = {
  approval_id: string;
  session_id: string;
  tool_call_id?: string;
  tool_name: string;
  arguments?: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected';
  reason?: string | null;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const AGENT_STREAM_ENDPOINT = `${API_BASE_URL}/api/v1/agent/stream`;
const AGENT_ENDPOINT = `${API_BASE_URL}/api/v1/agent`;

function parseSseEvent(block: string): { event: string; data: unknown } | null {
  const lines = block
    .split('\n')
    .map((line) => line.trimEnd())
    .filter(Boolean);

  if (lines.length === 0) {
    return null;
  }

  let event = 'message';
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
      continue;
    }

    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event,
    data: JSON.parse(dataLines.join('\n')),
  };
}

function mapToolCalls(toolCalls: AgentToolCall[]): ToolCall[] {
  return toolCalls.map((toolCall) => ({
    id: toolCall.id,
    name: toolCall.function?.name || '工具调用',
    status: 'pending',
    arguments: toolCall.function?.arguments,
    result: toolCall.function?.arguments ? JSON.stringify(toolCall.function.arguments, null, 2) : undefined,
  }));
}

function mergeToolCalls(current: ToolCall[], updates: ToolCall[]): ToolCall[] {
  const merged = [...current];

  for (const update of updates) {
    const targetIndex = merged.findIndex(
      (item) => (update.id && item.id === update.id) || (!update.id && item.name === update.name),
    );

    if (targetIndex === -1) {
      merged.push(update);
      continue;
    }

    merged[targetIndex] = {
      ...merged[targetIndex],
      ...update,
    };
  }

  return merged;
}

function createTitleFromText(text: string): string {
  const compact = text
    .replace(/[`#>*_\-\n]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!compact) {
    return '新对话';
  }

  return compact.length > 18 ? `${compact.slice(0, 18)}...` : compact;
}

export async function sendMessageStream(message: string, options: AgentServiceOptions): Promise<StreamResult> {
  const response = await fetch(AGENT_STREAM_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      message,
      session_id: options.sessionId,
      system_prompt: options.systemPrompt,
    }),
    signal: options.signal,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '后端服务请求失败。');
  }

  if (!response.body) {
    throw new Error('当前环境不支持流式响应。');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let sessionId = options.sessionId;
  let text = '';
  let toolCalls: ToolCall[] = [];
  let finishReason = 'completed';
  let sessionState: AgentSessionState | undefined;

  while (true) {
    const { value, done } = await reader.read();

    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const rawEvent of events) {
      const parsed = parseSseEvent(rawEvent);
      if (!parsed) {
        continue;
      }

      const payload = parsed.data as Record<string, any>;

      if (parsed.event === 'session' && typeof payload.session_id === 'string') {
        sessionId = payload.session_id;
        sessionState = payload as AgentSessionState;
        options.onSessionState?.(sessionState);
      }

      if (parsed.event === 'delta') {
        const delta = typeof payload.content === 'string' ? payload.content : '';
        text += delta;
        options.onDelta?.(delta, text);
      }

      if (parsed.event === 'tool_calls' && Array.isArray(payload.tool_calls)) {
        toolCalls = mergeToolCalls(toolCalls, mapToolCalls(payload.tool_calls));
        options.onToolCalls?.(toolCalls);
      }

      if (parsed.event === 'tool_results' && Array.isArray(payload.tool_calls)) {
        const updates = (payload.tool_calls as AgentToolResult[]).map((toolCall) => ({
          id: toolCall.tool_call_id,
          name: toolCall.name || '工具调用',
          status: toolCall.status || 'success',
          result: toolCall.result,
        })) as ToolCall[];
        toolCalls = mergeToolCalls(toolCalls, updates);
        options.onToolCalls?.(toolCalls);
      }

      if (parsed.event === 'approval_required') {
        const approval = payload as AgentApproval;
        toolCalls = mergeToolCalls(toolCalls, [
          {
            id: approval.tool_call_id,
            name: approval.tool_name || '工具调用',
            status: 'approval_required',
            approvalId: approval.approval_id,
            arguments: approval.arguments,
            result: approval.arguments ? JSON.stringify(approval.arguments, null, 2) : undefined,
          },
        ]);
        options.onToolCalls?.(toolCalls);
      }

      if (parsed.event === 'error') {
        throw new Error(typeof payload.message === 'string' ? payload.message : '智能体流式响应失败。');
      }

      if (parsed.event === 'done') {
        finishReason = typeof payload.finish_reason === 'string' ? payload.finish_reason : 'stop';
        sessionState = payload as AgentSessionState;
        options.onSessionState?.(sessionState);
      }
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseEvent(buffer);
    if (parsed?.event === 'done') {
      const payload = parsed.data as Record<string, any>;
      finishReason = typeof payload.finish_reason === 'string' ? payload.finish_reason : finishReason;
    }
  }

  return {
    sessionId,
    text,
    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
    finishReason,
    sessionState,
  };
}

export async function submitApprovalDecision(
  approvalId: string,
  status: 'approved' | 'rejected',
  reason?: string,
): Promise<AgentApproval> {
  const response = await fetch(`${AGENT_ENDPOINT}/approvals/${approvalId}/decision`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status, reason}),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '审批提交失败。');
  }

  return response.json();
}

export async function getAgentSessionState(sessionId: string): Promise<AgentSessionState> {
  const response = await fetch(`${AGENT_ENDPOINT}/sessions/${sessionId}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '会话状态读取失败。');
  }
  return response.json();
}

export async function generateTitle(history: Message[]): Promise<string> {
  const firstUserMessage = history.find((item) => item.role === 'user')?.text ?? '';
  const lastAssistantMessage = [...history].reverse().find((item) => item.role === 'model')?.text ?? '';
  return createTitleFromText(firstUserMessage || lastAssistantMessage);
}
