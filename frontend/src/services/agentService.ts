import { Message, ToolCall } from '../types';
import { authHeaders } from './authService';
import { apiFetch } from './apiClient';
import { fetchEventSource } from '@microsoft/fetch-event-source';

type AgentServiceOptions = {
  sessionId: string;
  systemPrompt?: string;
  responseMode?: 'general' | 'ppt' | 'website' | 'email' | 'bigdata';
  agentProfileId?: number | null;
  files?: { filename: string; file_path: string }[];
  onDelta?: (delta: string, fullText: string) => void;
  onReasoningDelta?: (delta: string, fullText: string) => void;
  onToolCalls?: (toolCalls: ToolCall[]) => void;
  onSessionState?: (state: AgentSessionState) => void;
  onRunStatus?: (status: AgentRunStatus) => void;
  onPptArtifact?: (artifact: AgentPptArtifact) => void;
  onWebsiteArtifact?: (artifact: AgentWebsiteArtifact) => void;
  onUserDecision?: (decision: unknown) => void;
  onUserInputRequired?: (input: UserInputRequest) => void;
  onApiApprovalRequired?: (approval: ApiApprovalRequest) => void;
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
  websiteArtifact?: AgentWebsiteArtifact;
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
  phase: 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'rendering_website' | 'done';
  label: string;
};

export type AgentPptArtifact = {
  artifact_id: string;
  session_id: string;
  title: string;
  slide_count: number;
  html: string;
  theme?: string;
};

export type AgentWebsiteArtifact = {
  type: 'website';
  artifact_id: string;
  session_id: string;
  title: string;
  project_slug: string;
  stack: string;
  file_count: number;
  preview_html: string;
};

export type UserInputField = {
  key: string;
  label: string;
  type: 'text' | 'password';
  required: boolean;
  description?: string;
};

export type UserInputRequest = {
  session_id: string;
  tool_call_id: string;
  api_name: string;
  api_display_name: string;
  system_name: string;
  fields: UserInputField[];
  message: string;
};

export type ApiApprovalRequest = {
  type: string;
  api_name: string;
  api_display_name: string;
  system_name: string;
  method: string;
  path: string;
  message: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const AGENT_STREAM_ENDPOINT = `${API_BASE_URL}/api/v1/agent/stream`;
const AGENT_ENDPOINT = `${API_BASE_URL}/api/v1/agent`;

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

type StreamState = {
  sessionId: string;
  text: string;
  reasoningText: string;
  toolCalls: ToolCall[];
  finishReason: string | null;
  sessionState?: AgentSessionState;
  pptArtifact?: AgentPptArtifact;
  websiteArtifact?: AgentWebsiteArtifact;
};

/**
 * 单个 SSE 事件分发（协议与旧手写实现完全一致）。
 * error 事件直接抛出，由 fetchEventSource 的 onerror 透传给调用方。
 */
function applyAgentEvent(
  event: string,
  raw: unknown,
  options: AgentServiceOptions,
  state: StreamState,
): void {
  const payload = raw as Record<string, unknown>;

  if (event === 'session' && typeof payload.session_id === 'string') {
    state.sessionId = payload.session_id;
    state.sessionState = payload as unknown as AgentSessionState;
    options.onSessionState?.(state.sessionState);
    return;
  }

  if (event === 'delta') {
    const delta = typeof payload.content === 'string' ? payload.content : '';
    state.text += delta;
    options.onDelta?.(delta, state.text);
    return;
  }

  if (event === 'reasoning_delta') {
    const delta = typeof payload.content === 'string' ? payload.content : '';
    state.reasoningText += delta;
    options.onReasoningDelta?.(delta, state.reasoningText);
    return;
  }

  if (event === 'run_status') {
    options.onRunStatus?.(payload as unknown as AgentRunStatus);
    return;
  }

  if (event === 'artifact_ready') {
    const artifactPayload = payload as Record<string, unknown>;
    if (artifactPayload.type === 'website') {
      state.websiteArtifact = artifactPayload as unknown as AgentWebsiteArtifact;
      options.onWebsiteArtifact?.(state.websiteArtifact);
    } else {
      state.pptArtifact = payload as unknown as AgentPptArtifact;
      options.onPptArtifact?.(state.pptArtifact);
    }
    return;
  }

  if (event === 'tool_calls' && Array.isArray(payload.tool_calls)) {
    state.toolCalls = mergeToolCalls(state.toolCalls, mapToolCalls(payload.tool_calls as AgentToolCall[]));
    options.onToolCalls?.(state.toolCalls);
    return;
  }

  if (event === 'tool_results' && Array.isArray(payload.tool_calls)) {
    state.toolCalls = mergeToolCalls(state.toolCalls, mapToolResults(payload.tool_calls as AgentToolResult[]));
    options.onToolCalls?.(state.toolCalls);
    return;
  }

  if (event === 'tool_error') {
    state.toolCalls = mergeToolCalls(state.toolCalls, [mapToolError(payload as AgentToolError)]);
    options.onToolCalls?.(state.toolCalls);
    return;
  }

  if (event === 'user_input_required') {
    options.onUserInputRequired?.(payload as unknown as UserInputRequest);
    return;
  }

  if (event === 'approval_required') {
    const approval = payload as unknown as AgentApproval;
    state.toolCalls = mergeToolCalls(state.toolCalls, [
      {
        id: approval.tool_call_id,
        name: approval.tool_name || '工具调用',
        status: 'approval_required',
        approvalId: approval.approval_id,
        arguments: approval.arguments,
        result: approval.arguments ? JSON.stringify(approval.arguments, null, 2) : undefined,
      },
    ]);
    options.onToolCalls?.(state.toolCalls);
    return;
  }

  if (event === 'api_approval_required') {
    // 复用工具审批 UI：将 API 审批转为工具审批格式
    const apiApproval = payload as ApiApprovalRequest;
    const fakeApprovalId = `api_${Date.now()}`;
    state.toolCalls = mergeToolCalls(state.toolCalls, [
      {
        id: fakeApprovalId,
        name: `${apiApproval.system_name} → ${apiApproval.api_display_name}`,
        status: 'approval_required',
        approvalId: fakeApprovalId,
        arguments: { method: apiApproval.method, path: apiApproval.path },
        result: apiApproval.message,
        isApiApproval: true as const,
      } as ToolCall,
    ]);
    options.onToolCalls?.(state.toolCalls);
    return;
  }

  if (event === 'user_decision') {
    options.onUserDecision?.(payload);
    return;
  }

  if (event === 'error') {
    throw new Error(normalizeAgentError(
      typeof payload.message === 'string' ? payload.message : undefined,
      typeof payload.error_type === 'string' ? payload.error_type : undefined,
    ));
  }

  if (event === 'done') {
    state.finishReason = typeof payload.finish_reason === 'string' ? payload.finish_reason : 'stop';
    state.sessionState = payload as unknown as AgentSessionState;
    options.onSessionState?.(state.sessionState);
  }
}

export async function sendMessageStream(message: string, options: AgentServiceOptions): Promise<StreamResult> {
  const state: StreamState = {
    sessionId: options.sessionId,
    text: '',
    reasoningText: '',
    toolCalls: [],
    finishReason: null,
  };

  const controller = new AbortController();
  const abort = () => controller.abort();
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener('abort', abort, { once: true });
  }

  // 心跳超时：库本身无空闲超时，用 timer 包一层 —— 连接建立即计时，
  // 每收到一个消息重置；超过 60 秒无数据则主动 abort 并报错。
  const STREAM_IDLE_TIMEOUT_MS = 60_000;
  let idleTimer: ReturnType<typeof setTimeout> | null = null;
  let idleTimedOut = false;
  const bumpIdle = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => {
      idleTimedOut = true;
      controller.abort();
    }, STREAM_IDLE_TIMEOUT_MS);
  };

  try {
    await fetchEventSource(AGENT_STREAM_ENDPOINT, {
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
        files: options.files?.length ? options.files : undefined,
      }),
      signal: controller.signal,
      // 页面切后台保持连接（默认行为是 hidden 时断开重连，会打断流式输出）
      openWhenHidden: true,
      // 非 2xx 响应：读取错误详情并归一化（与旧实现一致）
      fetch: async (url, init) => {
        bumpIdle();
        const response = await fetch(url, init);
        if (!response.ok) {
          const detail = await response.text().catch(() => '');
          throw new Error(normalizeAgentError(detail, String(response.status)));
        }
        return response;
      },
      onmessage(msg) {
        bumpIdle();
        let payload: unknown;
        try {
          payload = JSON.parse(msg.data);
        } catch (err) {
          // 单个坏块不应杀死整条流：跳过即可
          console.warn('Failed to parse SSE event payload:', err, String(msg.data).slice(0, 200));
          return;
        }
        if (msg.event === 'error') {
          // 先关闭底层连接再抛出，避免连接泄漏
          controller.abort();
        }
        applyAgentEvent(msg.event, payload, options, state);
      },
      // 不重试：错误直接抛出，保持旧实现 fail-fast 语义
      onerror(err) {
        throw err;
      },
    });
  } catch (err) {
    if (idleTimedOut) {
      throw new Error('流式响应超时：超过 60 秒未收到服务器数据，请检查网络后重试。');
    }
    // 调用方主动中断：不抛错，走下方 interrupted 兜底
    if (err instanceof Error && err.name === 'AbortError' && !idleTimedOut) {
      // swallowed
    } else {
      throw err;
    }
  } finally {
    if (idleTimer) clearTimeout(idleTimer);
    options.signal?.removeEventListener('abort', abort);
  }

  // 无 done：客户端主动中断 → interrupted；否则视为异常结束
  if (!state.finishReason) {
    state.finishReason = options.signal?.aborted || state.text ? 'interrupted' : 'error';
  }

  return {
    sessionId: state.sessionId,
    text: state.text,
    reasoningText: state.reasoningText || undefined,
    toolCalls: state.toolCalls.length > 0 ? state.toolCalls : undefined,
    finishReason: state.finishReason,
    sessionState: state.sessionState,
    pptArtifact: state.pptArtifact,
    websiteArtifact: state.websiteArtifact,
  };
}

export async function submitApprovalDecision(
  approvalId: string,
  status: 'approved' | 'rejected',
  reason?: string,
): Promise<AgentApproval> {
  return apiFetch<AgentApproval>(
    `${AGENT_ENDPOINT}/approvals/${approvalId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, reason }),
    },
    '审批提交失败',
  );
}

export async function submitUserDecision(
  decisionId: string,
  answer: string,
): Promise<{ ok: boolean; decision_id: string; answer: string }> {
  return apiFetch<{ ok: boolean; decision_id: string; answer: string }>(
    `${AGENT_ENDPOINT}/decisions/${decisionId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    },
    '决策提交失败',
  );
}

export async function getAgentSessionState(sessionId: string): Promise<AgentSessionState> {
  return apiFetch<AgentSessionState>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}`,
    {},
    '会话状态读取失败',
  );
}

/** 后端消息原始格式 */
type BackendMessage = {
  role: string;
  content: string;
  tool_calls?: Array<{ id?: string; name: string; arguments?: Record<string, unknown> }>;
  tool_call_id?: string;
  name?: string;
};

/** 会话最新制品信息（用于会话重新打开时恢复预览面板） */
export type SessionArtifacts = {
  ppt_artifact: {
    artifact_id: string;
    session_id: string;
    title: string;
    slide_count: number;
    html: string;
    theme?: string;
  } | null;
  website_artifact: AgentWebsiteArtifact | null;
};

/** 从后端加载会话关联的最新制品（PPT/网站） */
export async function getSessionArtifacts(sessionId: string): Promise<SessionArtifacts> {
  return apiFetch<SessionArtifacts>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/artifacts`,
    {},
    '加载会话制品失败',
  );
}

/** 按 artifactId 获取 PPT 预览 HTML（用于懒加载） */
export async function getPptPreviewHtml(artifactId: string): Promise<string> {
  return apiFetch<string>(
    `${AGENT_ENDPOINT}/ppt/preview/${artifactId}`,
    { responseType: 'text' },
    '加载 PPT 预览失败',
  );
}

/** 从后端加载会话的完整消息历史 */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  const raw = await apiFetch<BackendMessage[]>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/messages`,
    {},
    '加载消息历史失败',
  );
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
      messages.push({
        id: `backend-${messages.length}`,
        role: 'model',
        text: msg.content || '',
        toolCalls: toolCalls && toolCalls.length > 0 ? toolCalls : undefined,
      });
    }
  }
  return messages;
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
  return apiFetch<AgentSessionListItem[]>(`${AGENT_ENDPOINT}/sessions`, {}, '获取会话列表失败');
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch<void>(`${AGENT_ENDPOINT}/sessions/${sessionId}`, { method: 'DELETE' }, '删除会话失败');
}

export async function submitUserInput(sessionId: string, apiName: string, values: Record<string, string>): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/user-input`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_name: apiName, values }),
    },
    '提交用户输入失败',
  );
}

export async function submitApiApproval(sessionId: string, approved: boolean, allowAll?: boolean): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/api-approval`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved, allow_all: allowAll }),
    },
    '提交审批决定失败',
  );
}

export async function exportPptx(artifactId: string): Promise<Blob> {
  return apiFetch<Blob>(
    `${AGENT_ENDPOINT}/ppt/export`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ artifact_id: artifactId }),
      responseType: 'blob',
      timeoutMs: 120_000, // PPT 导出耗时较长
    },
    'PPT 导出失败',
  );
}

// PPT 主题相关 API
export type PptTheme = {
  name: string;
  primary_color: string;
  bg_color: string;
  text_color: string;
};

export async function listPptThemes(): Promise<PptTheme[]> {
  return apiFetch<PptTheme[]>(`${AGENT_ENDPOINT}/ppt/themes`, {}, '获取主题列表失败');
}

export async function rethemePpt(artifactId: string, theme: string): Promise<AgentPptArtifact & { theme: string }> {
  return apiFetch<AgentPptArtifact & { theme: string }>(
    `${AGENT_ENDPOINT}/ppt/${artifactId}/retheme`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme }),
    },
    '主题切换失败',
  );
}
