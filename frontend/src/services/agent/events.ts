import {
  AgentToolCall, AgentToolResult, AgentToolError,
  AgentServiceOptions, StreamState,
  AgentSessionState, AgentRunStatus, AgentPptArtifact,
  AgentWebsiteArtifact, AgentSheetArtifact, AgentDocumentArtifact,
  AgentApproval,
  UserInputRequest, ApiApprovalRequest,
  mapToolCalls, mapToolResults, mapToolError, mergeToolCalls,
  normalizeAgentError,
} from './shared';
import { ToolCall } from '../../types';
import { ApiError } from '../apiClient';
import { unwrapChartMessage as normalizeChartMessage } from '../backendMessageMapper';

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

