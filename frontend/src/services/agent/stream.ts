import { fetchEventSource } from '@microsoft/fetch-event-source';
import { authHeaders } from '../authService';
import { ApiError } from '../apiClient';
import {
  AGENT_STREAM_ENDPOINT,
  AgentServiceOptions, StreamResult, StreamState,
  normalizeAgentError,
} from './shared';
import { applyAgentEvent } from './events';

/**
 * 推断流的收尾原因（供单测直接喂各种来源组合，不必真拉 SSE）。
 *
 * 三种「无正常 done」来源必须区分开，不能被一句 `aborted || text` 混淆：
 * 1. 收到 SSE error 事件 → 'error'（服务端明确报错，绝不能因已有正文被判成中断）；
 * 2. 调用方 signal.aborted → 'interrupted'（用户点停止 / 主动取消）；
 * 3. 连接静默结束、无 done 无 error 也无正文 → 'error'（异常收尾）；
 *    有正文但无 done → 流被中途掐断（网络断开），'interrupted' 保留已生成内容。
 */
export function resolveFinishReason(
  state: Pick<StreamState, 'finishReason' | 'text' | 'errorEventReceived'>,
  signalAborted: boolean,
  errorEventLocal: boolean,
): string {
  if (state.finishReason) return state.finishReason;
  if (errorEventLocal || state.errorEventReceived) return 'error';
  if (signalAborted) return 'interrupted';
  return state.text ? 'interrupted' : 'error';
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
  // 收到过服务端 error 事件：用于把「服务端报错」与「用户点停止」区分开。
  // 两者都会让 signal.aborted 为真，只靠 signal 无法分辨。
  let errorEventReceived = false;
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
        // 视觉风格（仅 ppt 模式有意义）：与配色主题正交，管形状/留白/纹理。
        // 不传时后端注入 18 种风格目录让模型自己挑。
        visual_style: options.visualStyle || undefined,
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
        if (msg.event === 'error') {
          // **不要在这里 controller.abort()。**
          //
          // 曾经这里先 abort 再抛错，本意是「先关连接再抛，避免泄漏」。
          // 但 abort 会把 signal.aborted 置为 true，而下面 catch 里的判定是
          // 「signal.aborted → 用户主动停止，静默吞掉」，于是**真正的服务端
          // 错误（429 限流 / 超时 / 上游 500）全部被当成用户点了停止**，
          // 界面上一个提示都没有，只剩一只空气泡。
          //
          // 连接泄漏由 fetchEventSource 的 finally 与调用方的 abort 兜住，
          // 不需要在这里额外 abort。
          errorEventReceived = true;
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
    // 服务端发过 error 事件 → 这是我们主动中止的流，不是用户点停止。
    // applyAgentEvent 在收到 error 时会抛 ApiError，必须原样透出去，
    // 否则真实错误（429 / 超时 / 上游 500）会被下面的 AbortError 分支吞掉。
    if (errorEventReceived) {
      throw err instanceof Error ? err : new Error(String(err));
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

  state.finishReason = resolveFinishReason(state, options.signal?.aborted === true, errorEventReceived);

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

