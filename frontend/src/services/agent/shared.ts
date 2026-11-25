import { ToolCall } from '../../types';

export type AgentServiceOptions = {
  sessionId: string;
  systemPrompt?: string;
  responseMode?: 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'office';
  /** PPT 视觉风格 id（与配色主题正交；仅 ppt 模式生效） */
  visualStyle?: string;
  agentProfileId?: number | null;
  /** 会话级审批模式：ask 逐次确认 / auto 只读自动放行 / full 全放行（仅管理员） */
  approvalMode?: 'ask' | 'auto' | 'full';
  /** 计划模式：只允许只读工具，先产出计划再执行 */
  planMode?: boolean;
  files?: { filename: string; file_path: string; rel_path?: string | null }[];
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

export type StreamResult = {
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

export type AgentToolCall = {
  id?: string;
  function?: {
    name?: string;
    arguments?: Record<string, unknown>;
  };
  side_effect?: boolean;
  requires_approval?: boolean;
};

export type AgentToolResult = {
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

export type AgentToolError = {
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

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
export const AGENT_STREAM_ENDPOINT = `${API_BASE_URL}/api/v1/agent/stream`;
export const AGENT_ENDPOINT = `${API_BASE_URL}/api/v1/agent`;

export function stripHtml(text: string): string {
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
    // 日额度用尽与「请求太频繁」的处理完全不同：前者等一会儿没用，
    // 必须等额度重置或换模型/充值。内网实测踩过 —— 用户反复重试一整天
    // 都是同一句「请稍后再试」，看不出真正原因。
    if (lower.includes('per day') || lower.includes('per-day') || lower.includes('daily')) {
      return '模型服务的每日免费额度已用完。请明天再试，或联系管理员更换模型 / 充值。';
    }
    return '模型服务请求过于频繁，请稍后再试。';
  }
  if (lower.includes('timeout') || lower.includes('timed out')) {
    return '模型响应超时。可能是任务过大或上游服务繁忙，请重试或换个更简单的问法。';
  }
  if (lower.includes('api key')) {
    return '模型服务密钥配置异常，请联系管理员检查配置。';
  }
  return text || '智能体流式响应失败。';
}

export function mapToolCalls(toolCalls: AgentToolCall[]): ToolCall[] {
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

export function mapToolResults(toolCalls: AgentToolResult[]): ToolCall[] {
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

export function mapToolError(toolError: AgentToolError): ToolCall {
  return {
    id: toolError.tool_call_id,
    name: toolError.tool_name || 'tool_call',
    status: 'error',
    ...(toolError.message ? { reason: toolError.message, result: toolError.message } : {}),
    ...(toolError.error_type ? { errorType: toolError.error_type } : {}),
  };
}


export function mergeToolCalls(current: ToolCall[], updates: ToolCall[]): ToolCall[] {
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

export function createTitleFromText(text: string): string {
  const compact = text
    .replace(/[`#>*_\-\n]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!compact) {
    return '新对话';
  }

  return compact.length > 18 ? `${compact.slice(0, 18)}...` : compact;
}

export type StreamState = {
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
  /** A2UI 消息序列（累积，按协议顺序应用） */
  a2uiMessages?: Record<string, unknown>[];
  chartMessages?: Array<{ title?: string; option: unknown }>;
};
