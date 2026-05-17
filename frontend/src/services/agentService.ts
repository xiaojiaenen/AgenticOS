import { Message, ToolCall } from '../types';
import { authHeaders } from './authService';

type AgentServiceOptions = {
  sessionId: string;
  systemPrompt?: string;
  responseMode?: 'general' | 'ppt' | 'ppt-svg' | 'website';
  agentProfileId?: number | null;
  onDelta?: (delta: string, fullText: string) => void;
  onReasoningDelta?: (delta: string, fullText: string) => void;
  onToolCalls?: (toolCalls: ToolCall[]) => void;
  onSessionState?: (state: AgentSessionState) => void;
  onRunStatus?: (status: AgentRunStatus) => void;
  onPptArtifact?: (artifact: AgentPptArtifact) => void;
  signal?: AbortSignal;
};

type StreamResult = {
  sessionId: string;
  text: string;
  reasoningText?: string;
  toolCalls?: ToolCall[];
  finishReason: string;
  sessionState?: AgentSessionState;
  pptArtifact?: AgentPptArtifact;
};

type AgentToolCall = {
  id?: string;
  function?: {
    name?: string;
    arguments?: Record<string, unknown>;
  };
  side_effect?: boolean;
  requires_approval?: boolean;
};

type AgentToolResult = {
  tool_call_id?: string;
  name?: string;
  status?: ToolCall['status'];
  result?: string;
  error_type?: string;
  tool_executed?: boolean;
  retryable?: boolean;
  attempts?: number;
  instruction?: string;
};

type AgentToolError = {
  tool_call_id?: string;
  tool_name?: string;
  message?: string;
  error_type?: string;
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

export type AgentRunStatus = {
  session_id: string;
  phase: 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'done';
  label: string;
};

export type AgentPptArtifact = {
  artifact_id: string;
  session_id: string;
  title: string;
  slide_count: number;
  html: string;
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

function stripHtml(text: string): string {
  return text.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
}

function normalizeAgentError(message?: string, errorType?: string): string {
  const text = stripHtml(message || '');
  const lower = text.toLowerCase();
  if (text.includes('Insufficient Balance') || lower.includes('insufficient balance') || text.includes('402')) {
    return '模型服务余额不足，请联系管理员充值或切换可用模型。';
  }
  if (errorType === 'rate_limit_error' || lower.includes('rate limit')) {
    return '模型服务请求过于频繁，请稍后再试。';
  }
  if (lower.includes('api key')) {
    return '模型服务密钥配置异常，请联系管理员检查配置。';
  }
  return text || '智能体流式响应失败。';
}

function mapToolCalls(toolCalls: AgentToolCall[]): ToolCall[] {
  return toolCalls.map((toolCall) => ({
    id: toolCall.id,
    name: toolCall.function?.name || 'tool_call',
    status: 'pending',
    arguments: toolCall.function?.arguments,
    result: toolCall.function?.arguments ? JSON.stringify(toolCall.function.arguments, null, 2) : undefined,
    sideEffect: toolCall.side_effect,
    requiresApproval: toolCall.requires_approval,
  }));
}

function mapToolResults(toolCalls: AgentToolResult[]): ToolCall[] {
  return toolCalls.map((toolCall) => ({
    id: toolCall.tool_call_id,
    name: toolCall.name || 'tool_call',
    status: toolCall.status || 'success',
    ...(toolCall.result !== undefined ? { result: toolCall.result } : {}),
    ...(toolCall.error_type ? { errorType: toolCall.error_type } : {}),
    ...(toolCall.tool_executed !== undefined ? { toolExecuted: toolCall.tool_executed } : {}),
    ...(toolCall.retryable !== undefined ? { retryable: toolCall.retryable } : {}),
    ...(toolCall.attempts !== undefined ? { attempts: toolCall.attempts } : {}),
    ...(toolCall.instruction ? { instruction: toolCall.instruction } : {}),
  }));
}

function mapToolError(toolError: AgentToolError): ToolCall {
  return {
    id: toolError.tool_call_id,
    name: toolError.tool_name || 'tool_call',
    status: 'error',
    ...(toolError.message ? { reason: toolError.message, result: toolError.message } : {}),
    ...(toolError.error_type ? { errorType: toolError.error_type } : {}),
  };
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
      ...authHeaders(),
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({
      message,
      session_id: options.sessionId,
      system_prompt: options.systemPrompt,
      agent_profile_id: options.agentProfileId || undefined,
      response_mode: options.responseMode || 'general',
    }),
    signal: options.signal,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(normalizeAgentError(detail, String(response.status)));
  }

  if (!response.body) {
    throw new Error('当前环境不支持流式响应。');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let sessionId = options.sessionId;
  let text = '';
  let reasoningText = '';
  let toolCalls: ToolCall[] = [];
  let finishReason = 'completed';
  let sessionState: AgentSessionState | undefined;
  let pptArtifact: AgentPptArtifact | undefined;

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

      if (parsed.event === 'reasoning_delta') {
        const delta = typeof payload.content === 'string' ? payload.content : '';
        reasoningText += delta;
        options.onReasoningDelta?.(delta, reasoningText);
      }

      if (parsed.event === 'run_status') {
        options.onRunStatus?.(payload as AgentRunStatus);
      }

      if (parsed.event === 'artifact_ready') {
        pptArtifact = payload as AgentPptArtifact;
        options.onPptArtifact?.(pptArtifact);
      }

      if (parsed.event === 'tool_calls' && Array.isArray(payload.tool_calls)) {
        toolCalls = mergeToolCalls(toolCalls, mapToolCalls(payload.tool_calls));
        options.onToolCalls?.(toolCalls);
      }

      if (parsed.event === 'tool_results' && Array.isArray(payload.tool_calls)) {
        toolCalls = mergeToolCalls(toolCalls, mapToolResults(payload.tool_calls as AgentToolResult[]));
        options.onToolCalls?.(toolCalls);
      }

      if (parsed.event === 'tool_error') {
        toolCalls = mergeToolCalls(toolCalls, [mapToolError(payload as AgentToolError)]);
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
        throw new Error(normalizeAgentError(
          typeof payload.message === 'string' ? payload.message : undefined,
          typeof payload.error_type === 'string' ? payload.error_type : undefined,
        ));
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
    if (parsed) {
      const payload = parsed.data as Record<string, any>;
      if (parsed.event === 'delta') {
        const delta = typeof payload.content === 'string' ? payload.content : '';
        text += delta;
      } else if (parsed.event === 'reasoning_delta') {
        const delta = typeof payload.content === 'string' ? payload.content : '';
        reasoningText += delta;
      } else if (parsed.event === 'done') {
        finishReason = typeof payload.finish_reason === 'string' ? payload.finish_reason : finishReason;
        sessionState = payload as AgentSessionState;
      } else if (parsed.event === 'tool_results' && Array.isArray(payload.tool_calls)) {
        toolCalls = mergeToolCalls(toolCalls, mapToolResults(payload.tool_calls as AgentToolResult[]));
      } else if (parsed.event === 'tool_calls' && Array.isArray(payload.tool_calls)) {
        toolCalls = mergeToolCalls(toolCalls, mapToolCalls(payload.tool_calls));
      }
    }
  }

  return {
    sessionId,
    text,
    reasoningText: reasoningText || undefined,
    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
    finishReason,
    sessionState,
    pptArtifact,
  };
}

export async function submitApprovalDecision(
  approvalId: string,
  status: 'approved' | 'rejected',
  reason?: string,
): Promise<AgentApproval> {
  const response = await fetch(`${AGENT_ENDPOINT}/approvals/${approvalId}/decision`, {
    method: 'POST',
    headers: {...authHeaders(), 'Content-Type': 'application/json'},
    body: JSON.stringify({status, reason}),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '审批提交失败。');
  }

  return response.json();
}

export async function getAgentSessionState(sessionId: string): Promise<AgentSessionState> {
  const response = await fetch(`${AGENT_ENDPOINT}/sessions/${sessionId}`, {
    headers: authHeaders(),
  });
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

export type AgentSessionListItem = {
  session_id: string;
  summary?: string | null;
  metadata?: Record<string, unknown>;
  message_count: number;
  created_at?: string;
  updated_at?: string;
};

export async function listSessions(): Promise<AgentSessionListItem[]> {
  const response = await fetch(`${AGENT_ENDPOINT}/sessions`, {
    headers: authHeaders(),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '获取会话列表失败。');
  }
  return response.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${AGENT_ENDPOINT}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '删除会话失败。');
  }
}

export async function exportPptx(artifactId: string): Promise<Blob> {
  const response = await fetch(
    `${AGENT_ENDPOINT}/ppt/export`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(),
      },
      body: JSON.stringify({ artifact_id: artifactId }),
    },
  );
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'PPT 导出失败。');
  }
  return response.blob();
}
