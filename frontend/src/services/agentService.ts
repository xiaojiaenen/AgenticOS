import { Message, ToolCall } from '../types';
import { authHeaders } from './authService';
import { apiFetch, ApiError } from './apiClient';
import { mapBackendMessages, unwrapChartMessage as normalizeChartMessage } from './backendMessageMapper';
import { fetchEventSource } from '@microsoft/fetch-event-source';

type AgentServiceOptions = {
  sessionId: string;
  systemPrompt?: string;
  responseMode?: 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'office';
  agentProfileId?: number | null;
  /** 会话级审批模式：ask 逐次确认 / auto 只读自动放行 / full 全放行（仅管理员） */
  approvalMode?: 'ask' | 'auto' | 'full';
  /** 计划模式：只允许只读工具，先产出计划再执行 */
  planMode?: boolean;
  files?: { filename: string; file_path: string }[];
  /** 运行预算（后端随流事件透出，用于"第 N/M 步"提示） */
  onBudget?: (budget: { step?: number; maxSteps?: number }) => void;
  onDelta?: (delta: string, fullText: string) => void;
  onReasoningDelta?: (delta: string, fullText: string) => void;
  onToolCalls?: (toolCalls: ToolCall[]) => void;
  onSessionState?: (state: AgentSessionState) => void;
  onRunStatus?: (status: AgentRunStatus) => void;
  onPptArtifact?: (artifact: AgentPptArtifact) => void;
  onWebsiteArtifact?: (artifact: AgentWebsiteArtifact) => void;
  onSheetArtifact?: (artifact: AgentSheetArtifact) => void;
  onDocumentArtifact?: (artifact: AgentDocumentArtifact) => void;
  /** A2UI 声明式界面消息（render_ui / render_form 生成） */
  onA2uiMessages?: (messages: Record<string, unknown>[]) => void;
  /** 数据图表消息（render_chart 生成，ECharts option，与 A2UI 无关） */
  onChartMessages?: (
    charts: Array<{ title?: string; option: unknown }>,
  ) => void;
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
  sheetArtifact?: AgentSheetArtifact;
  documentArtifact?: AgentDocumentArtifact;
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

export type AgentDocumentArtifact = {
  type: 'document';
  artifact_id: string;
  session_id: string;
  title: string;
  /** Univer 的 IDocumentData 原始 JSON */
  snapshot: Record<string, unknown>;
  char_count: number;
  version?: number;
};

export type AgentSheetArtifact = {
  type: 'spreadsheet';
  artifact_id: string;
  session_id: string;
  title: string;
  /** Univer 的 IWorkbookData 原始 JSON */
  snapshot: Record<string, unknown>;
  sheet_names: string[];
  sheet_count: number;
  version?: number;
};

export type AgentWebsiteArtifact = {
  type: 'website';
  artifact_id: string;
  session_id: string;
  title: string;
  project_slug: string;
  stack: string;
  file_count: number;
  /** 带签名的静态预览 URL（后端签发；缺失时退回 preview_html 内联） */
  preview_url?: string | null;
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

/**导出仅供单元测试：HTTP 非 2xx / SSE error 的文案归一化。*/
export function normalizeAgentError(message?: string, errorType?: string): string {
  let text = stripHtml(message || '');
  // FastAPI 的 HTTPException 返回 {"detail": "..."} 包装 —— 先解出人话，
  // 否则 403/429/500 这类端点级错误会把整段 JSON 原样展示给用户。
  if (text.trimStart().startsWith('{')) {
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed.detail === 'string' && parsed.detail) text = parsed.detail;
    } catch {
      // 不是合法 JSON（多半是 SSE error 事件的纯文本）—— 保持原文
    }
  }
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
  sheetArtifact?: AgentSheetArtifact;
  documentArtifact?: AgentDocumentArtifact;
  /** A2UI 消息序列（累积，按协议顺序应用） */
  a2uiMessages?: Record<string, unknown>[];
  chartMessages?: Array<{ title?: string; option: unknown }>;
};

/**
 * 单个 SSE 事件分发（协议与旧手写实现完全一致）。
 * error 事件直接抛出，由 fetchEventSource 的 onerror 透传给调用方。
 *
 * 导出：分发协议本身是纯函数（只改 state / 触发回调），SSE 通道的
 * 回归测试直接喂事件即可，不必拉起 fetchEventSource。
 */
export function applyAgentEvent(
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
    // 运行预算随流透出
    if (typeof payload.step === 'number' || typeof payload.max_steps === 'number') {
      options.onBudget?.({
        step: typeof payload.step === 'number' ? payload.step : undefined,
        maxSteps: typeof payload.max_steps === 'number' ? payload.max_steps : undefined,
      });
    }
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

  if (event === 'chart') {
    // 数据图表是独立通道：ECharts option 不是 A2UI 组件树，
    // 混进 MessageProcessor 会被 zod 拒绝（Invalid v0.9 message）。
    //
    // 后端下发的每条消息是 {version, chart:{title, option}} 包裹格式，
    // 必须解包成 {title, option} 再存 —— 之前漏了解包，ChartMessage 拿到的
    // title/option 全是 undefined，实时渲染出来就是一张空白卡片
    // （而刷新恢复路径做过解包，症状成了"实时空白、刷新反而正常"）。
    const incoming = (Array.isArray(payload.messages) ? payload.messages : [])
      .map(normalizeChartMessage)
      .filter((c): c is { title?: string; option: unknown } => c !== null);
    if (incoming.length > 0) {
      state.chartMessages = [...(state.chartMessages ?? []), ...incoming];
      options.onChartMessages?.(state.chartMessages);
    }
    return;
  }

  if (event === 'a2ui') {
    // 界面消息是**累积**的：智能体可能先发 createSurface，再分批补组件。
    // 前端保留整条序列交给 MessageProcessor 顺序消费，不做增量合并 ——
    // 协议本身就是按序应用的，交给它处理比我们猜状态可靠。
    const incoming = Array.isArray(payload.messages) ? payload.messages : [];
    if (incoming.length > 0) {
      state.a2uiMessages = [...(state.a2uiMessages ?? []), ...incoming];
      options.onA2uiMessages?.(state.a2uiMessages);
    }
    return;
  }

  if (event === 'artifact_ready') {
    console.log('[probe] artifact_ready type=', (payload as Record<string, unknown>).type);
    const artifactPayload = payload as Record<string, unknown>;
    if (artifactPayload.type === 'website') {
      state.websiteArtifact = artifactPayload as unknown as AgentWebsiteArtifact;
      options.onWebsiteArtifact?.(state.websiteArtifact);
    } else if (artifactPayload.type === 'spreadsheet') {
      state.sheetArtifact = artifactPayload as unknown as AgentSheetArtifact;
      options.onSheetArtifact?.(state.sheetArtifact);
    } else if (artifactPayload.type === 'document') {
      state.documentArtifact = artifactPayload as unknown as AgentDocumentArtifact;
      options.onDocumentArtifact?.(state.documentArtifact);
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
    // 对齐 apiClient 的错误类型：message 为归一化后的用户可读信息，detail 保留原始负载
    throw new ApiError(
      0,
      payload.message ?? payload,
      normalizeAgentError(
        typeof payload.message === 'string' ? payload.message : undefined,
        typeof payload.error_type === 'string' ? payload.error_type : undefined,
      ),
    );
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
        // 不传时后端按 auto 处理：只读工具自动放行，写操作仍逐次确认
        approval_mode: options.approvalMode || 'auto',
        plan_mode: options.planMode || false,
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
          // 非 2xx：保留 HTTP status，归一化 message（与 apiFetch 的 ApiError 语义一致）
          throw new ApiError(response.status, detail, normalizeAgentError(detail, String(response.status)));
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
        if (msg.event !== 'reasoning_delta' && msg.event !== 'delta') {
          console.log('[probe] SSE event:', msg.event);
        }
        if (msg.event === 'error') {
          // 先关闭底层连接再抛出，避免连接泄漏
          controller.abort();
        }
        if (msg.event === 'artifact_ready') console.log('[probe] SSE 收到 artifact_ready, event=', msg.event, 'data.type=', (payload as Record<string, unknown>).type);
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
    sheetArtifact: state.sheetArtifact,
    documentArtifact: state.documentArtifact,
  };
}

export async function submitApprovalDecision(
  approvalId: string,
  status: 'approved' | 'rejected',
  reason?: string,
  modifiedArguments?: Record<string, unknown>,
): Promise<AgentApproval> {
  return apiFetch<AgentApproval>(
    `${AGENT_ENDPOINT}/approvals/${approvalId}/decision`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 用户在预览面板里改过内容/模板时，把改后的工具参数一起回传；
      // 后端批准执行时用它们替换原始参数。
      body: JSON.stringify({
        status,
        reason,
        ...(modifiedArguments ? { modified_arguments: modifiedArguments } : {}),
      }),
    },
    '审批提交失败',
  );
}

/** 邮件模板预览：切换模板时不经 AI，后端纯函数重渲染，毫秒级返回。 */
export type EmailTemplateChoice = { id: string; label: string };
export type EmailTemplatePreview = {
  html: string;
  is_html: boolean;
  template: string;
  needs_ai: boolean;
};

export async function listEmailTemplates(): Promise<EmailTemplateChoice[]> {
  return apiFetch<EmailTemplateChoice[]>(
    '/api/v1/email/templates',
    {},
    '加载邮件模板失败',
  );
}

export async function previewEmailTemplate(payload: {
  template: string;
  subject: string;
  body: string;
  button_label?: string;
  button_url?: string;
  signer?: string;
}): Promise<EmailTemplatePreview> {
  return apiFetch<EmailTemplatePreview>(
    '/api/v1/email/templates/preview',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    '邮件模板预览失败',
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

/** 后端消息原始格式（映射逻辑见 backendMessageMapper.ts） */
type BackendMessage = import('./backendMessageMapper').BackendMessage;

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
  sheet_artifact: AgentSheetArtifact | null;
  document_artifact: AgentDocumentArtifact | null;
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

export type PolishPromptResult = {
  polished: string;
  original: string;
  changed: boolean;
};

/**
 * 提示词润色：分析用户意图后改写为更可执行的长提示词。
 * 传入 signal 可在用户点「取消润色」时中断请求。
 */
export async function polishPrompt(
  text: string,
  signal?: AbortSignal,
): Promise<PolishPromptResult> {
  return apiFetch<PolishPromptResult>(
    `${AGENT_ENDPOINT}/polish-prompt`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      // 润色要过一次 LLM，放宽默认超时
      timeoutMs: 90_000,
      ...(signal ? { signal } : {}),
    },
    '提示词润色失败',
  );
}

export type ArtifactKind = 'ppt' | 'website' | 'sheet' | 'document';

export type ArtifactVersion = {
  kind: ArtifactKind;
  version: number;
  /** ppt 为 artifact_id；website / sheet 为版本号 "v{n}" */
  reference: string;
  title?: string;
  created_at?: string | null;
  slide_count?: number;
};

/** 列出会话的全部产物版本（PPT 每轮一条记录 + 网站每轮快照） */
export async function listSessionVersions(sessionId: string): Promise<{ versions: ArtifactVersion[] }> {
  return apiFetch<{ versions: ArtifactVersion[] }>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/versions`,
    {},
    '加载历史版本失败',
  );
}

/** 加载指定版本的产物，用于"回看历史版本" */
export async function loadArtifactVersion(
  sessionId: string,
  kind: ArtifactKind,
  reference: string,
): Promise<{
  ppt_artifact?: { artifact_id: string; title: string; slide_count: number; html: string; theme?: string };
  website_artifact?: {
    artifact_id: string;
    title: string;
    project_slug: string;
    stack?: string;
    preview_html: string;
  };
  sheet_artifact?: AgentSheetArtifact;
  document_artifact?: AgentDocumentArtifact;
}> {
  return apiFetch(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/versions/${kind}/${encodeURIComponent(reference)}`,
    {},
    '加载该版本失败',
  );
}

/** 从后端加载会话的完整消息历史 */
export async function getSessionMessages(sessionId: string): Promise<Message[]> {
  const raw = await apiFetch<BackendMessage[]>(
    `${AGENT_ENDPOINT}/sessions/${sessionId}/messages`,
    {},
    '加载消息历史失败',
  );
  return mapBackendMessages(raw);
}

export async function generateTitle(history: Message[]): Promise<string> {
  const firstUserMessage = history.find((item) => item.role === 'user')?.text ?? '';
  const lastAssistantMessage = [...history].reverse().find((item) => item.role === 'model')?.text ?? '';
  return createTitleFromText(firstUserMessage || lastAssistantMessage);
}

export type AgentSessionListItem = {
  session_id: string;
  summary?: string | null;
  /** 会话展示标题（首条用户消息摘录）；summary 是上下文压缩摘要，不能当标题用 */
  title?: string | null;
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

/** 保存用户对文档产物的修改。 */
export async function saveDocumentSnapshot(
  sessionId: string,
  directory: string,
  snapshot: Record<string, unknown>,
): Promise<void> {
  await apiFetch<{ ok: boolean }>(
    `${AGENT_ENDPOINT}/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(directory)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot }),
    },
    '保存文档失败',
  );
}

/** 保存用户对表格产物的修改（编辑器里点「保存」时调用）。 */
export async function saveSheetSnapshot(
  sessionId: string,
  directory: string,
  snapshot: Record<string, unknown>,
): Promise<void> {
  await apiFetch<{ ok: boolean }>(
    `${AGENT_ENDPOINT}/sessions/${encodeURIComponent(sessionId)}/sheets/${encodeURIComponent(directory)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snapshot }),
    },
    '保存表格失败',
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
