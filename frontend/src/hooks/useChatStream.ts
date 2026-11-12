import { useState, useRef, useCallback, useEffect } from 'react';
import { Message, Session, Attachment, Artifact } from '../types';
import {
  sendMessageStream,
  generateTitle,
  submitApprovalDecision,
  submitUserDecision,
  submitApiApproval,
  AgentSessionState,
  AgentPptArtifact,
  AgentWebsiteArtifact,
  AgentSheetArtifact,
  AgentDocumentArtifact,
  AgentRunStatus,
  UserInputRequest,
  ApiApprovalRequest,
} from '../services/agentService';
import { AgentProfile } from '../services/agentProfileService';
import { uploadFiles } from '../services/fileService';
import { MODE_SYSTEM_PROMPTS } from '../constants/modePrompts';
import { UserDecision, normalizeDecision } from '../components/chat/DecisionPanel';
import { useChatStore } from '../stores/chatStore';
import { pptMessageArtifact, websiteMessageArtifact } from '../lib/artifactSnapshots';
import { toast } from 'sonner';
import { syncTextBlocks, syncReasoningBlocks, syncToolBlocks } from '../lib/messageBlocks';

// ---------------------------------------------------------------------------
// extracted helpers
// ---------------------------------------------------------------------------

function buildAttachments(files: File[], collectedUrls?: string[]): Attachment[] {
  return files.map((file) => {
    const url = file.type.startsWith('image/') ? URL.createObjectURL(file) : '';
    if (url && collectedUrls) collectedUrls.push(url);
    return { name: file.name, type: file.type, url };
  });
}

/** 本轮「停止」后收尾会话消息：拒绝悬挂审批 + 给空气泡补占位文字。
 *
 * 为什么需要补占位：agent 是多轮工具循环，停止发生在循环中间时，最后一条
 * assistant 往往只有过渡 content（'\n\n' 之类）或干脆为空、只剩 tool_calls。
 * 工具链折叠后气泡里就没有任何文字 —— 用户看到的是「停完之后一片空白」。
 * 有思考内容的气泡不用补（思考本身就是可见内容）。
 */
export function markStoppedTurn(messages: Message[]): Message[] {
  const next = messages.map((message) =>
    message.toolCalls?.some((t) => t.status === 'approval_required')
      ? {
          ...message,
          toolCalls: message.toolCalls.map((t) =>
            t.status === 'approval_required'
              ? {
                  ...t,
                  status: 'rejected' as const,
                  result: t.result ?? '生成已被用户停止，审批请求自动取消。',
                }
              : t
          ),
        }
      : message
  );

  // 找到本轮最后一条模型消息；只有它是「空泡」时才补占位
  for (let i = next.length - 1; i >= 0; i -= 1) {
    const message = next[i];
    if (message.role === 'user') break; // 本轮还没产出任何模型消息
    if (message.role !== 'model') continue;
    const hasText = Boolean(message.text?.trim());
    const hasReasoning = Boolean(message.reasoningText?.trim());
    const hasArtifacts =
      (message.a2uiMessages?.length ?? 0) > 0 || (message.chartMessages?.length ?? 0) > 0;
    if (!hasText && !hasReasoning && !hasArtifacts) {
      next[i] = { ...message, text: '（已停止）' };
    }
    break;
  }
  return next;
}

async function prepareUploadedFiles(
  files: File[],
  onStatus: (label: string) => void,
): Promise<{ filename: string; file_path: string }[]> {
  onStatus('正在上传文件');
  const results = await uploadFiles(files);
  return results.map((r) => ({
    filename: r.filename,
    file_path: r.file_path,
  }));
}

interface UseChatStreamDeps {
  sessions: Session[];
  currentSessionId: string | null;
  currentSession: Session | null;
  chatMode: 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'office';
  /** 会话级审批模式 */
  approvalMode: 'ask' | 'auto' | 'full';
  /** 计划模式 */
  planMode: boolean;
  selectedAgentProfileId: number | null;
  selectedAgent: AgentProfile | null;
  setSessions: React.Dispatch<React.SetStateAction<Session[]>>;
  setCurrentSessionId: React.Dispatch<React.SetStateAction<string | null>>;
  applySessionState: (sessionId: string, state: AgentSessionState) => void;
  setArtifact: (artifact: Artifact | null) => void;
  setInputValue: (value: string) => void;
  onUserInputRequired?: (input: UserInputRequest) => void;
  onApiApprovalRequired?: (approval: ApiApprovalRequest) => void;
}

/**
 * 按事件到达顺序维护消息的有序内容块。
 * 正文与思考各自续写自己的块；若中间夹了工具调用，则自动开新块。
 * 每个块存该块的累计全文，因此块内文本始终自洽。
 */
function mergeOrderedBlocks(
  message: Message,
  delta: { fullText: string } | null,
  reasoning: string | null,
): { blocks?: Message['blocks'] } {
  if (!delta && reasoning == null) return {};
  let blocks = message.blocks || [];
  // message.text / reasoningText 是上一轮的累计全文，其长度即"已消费字符数"，
  // 传进去让块只保存本次新增的增量，避免 ReAct 多轮重复渲染全量文本
  if (delta) blocks = syncTextBlocks(blocks, delta.fullText, (message.text || '').length);
  if (reasoning != null) {
    blocks = syncReasoningBlocks(blocks, reasoning, (message.reasoningText || '').length);
  }
  return { blocks };
}

export function useChatStream({
  sessions,
  currentSessionId,
  currentSession,
  chatMode,
  approvalMode,
  planMode,
  selectedAgentProfileId,
  selectedAgent,
  setSessions,
  setCurrentSessionId,
  applySessionState,
  setArtifact,
  setInputValue,
  onUserInputRequired,
  onApiApprovalRequired,
}: UseChatStreamDeps) {
  // isLoading 按会话隔离：记录正在加载的会话 ID
  const [loadingSessionId, setLoadingSessionId] = useState<string | null>(null);
  // error / pendingDecisions / runStatus 已迁入 zustand chatStore（R3-2），
  // setter 保持 React dispatch 契约，本 hook 内部逻辑不变
  const error = useChatStore((s) => s.streamError);
  const setError = useChatStore((s) => s.setStreamError);
  const pendingDecisions = useChatStore((s) => s.pendingDecisions);
  const setPendingDecisions = useChatStore((s) => s.setPendingDecisions);
  const runStatus = useChatStore((s) => s.runStatus);
  const setRunStatus = useChatStore((s) => s.setRunStatus);

  // 按会话管理 AbortController：**切换会话不能 abort 正在跑的那一轮**。
  // 之前是单个 ref，切到别的会话就把上一轮的流掐断 —— 后端收到
  // CancelledError，整轮 LLM 生成作废，用户切回来只剩半截回复。
  // 只有「停止」按钮与组件卸载才允许 abort。
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  // 把「正在流式」的会话集合投影到全局 store：侧栏呼吸点 / 浏览器标题等
  // 环境感知 UI 消费。ref 负责同步读写（事件回调里要即时），store 只做投影。
  const setActiveStreamIds = useChatStore((s) => s.setActiveStreamIds);
  const activeStreamIds = useChatStore((s) => s.activeStreamIds);
  const syncActiveStreams = () => setActiveStreamIds(new Set(activeStreamSessionIdsRef.current));
  // 当前活跃流对应的会话 ID 集合（含后端重命名后的 ID）
  const activeStreamSessionIdsRef = useRef<Set<string>>(new Set());
  // 最新 sessions 引用：handleSend 内部经 ref 读取，避免因依赖 sessions 在流式期间每帧重建回调
  const sessionsRef = useRef(sessions);
  useEffect(() => {
    sessionsRef.current = sessions;
  }, [sessions]);
  // 本轮创建的附件 blob URL：预览（消息气泡内的 <img>）直接使用该 URL，
  // 因此不在流结束后立即 revoke（消息在整个页面生命周期内展示，提前 revoke 会导致切回会话后图片失效），
  // 统一在卸载时释放，避免页面长期使用过程中的泄漏
  const attachmentUrlsRef = useRef<string[]>([]);

  // ── 流式 Delta 批量更新：合并高频 token 到每帧一次 setSessions ──
  const latestDeltaRef = useRef<{ fullText: string; isPpt: boolean } | null>(null);
  const latestReasoningRef = useRef<string | null>(null);
  const deltaFlushRaf = useRef<number | null>(null);

  // A2UI 提交排队：界面在流式过程中就能点，此时不能并发起新 run
  // （同会话后端有锁，两条流还会互相覆盖同一条助手消息）。
  // 这里先存下动作、停掉当前流，等 isLoading 落下后由下方 effect 真正发出。
  const pendingA2uiRef = useRef<Array<{ text: string; files?: File[] }>>([]);
  const handleSendRef = useRef<
    ((text: string, files?: File[], source?: 'composer' | 'a2ui') => Promise<boolean>) | null
  >(null);
  /** 当前是否处于流式状态（供 handleSend 的守卫读取，避免闭包读到旧值）。 */
  const isLoadingRef = useRef(false);

  // Cleanup rAF + 撤销本轮创建的附件 blob URL + abort 未完成请求 on unmount
  useEffect(() => () => {
    if (deltaFlushRaf.current != null) cancelAnimationFrame(deltaFlushRaf.current);
    // 组件真正卸载才断开所有流（切会话不在此列）
    for (const controller of abortControllersRef.current.values()) controller.abort();
    abortControllersRef.current.clear();
    for (const url of attachmentUrlsRef.current) {
      URL.revokeObjectURL(url);
    }
    attachmentUrlsRef.current = [];
  }, []);

  // 切换会话：**不打断任何正在运行的流**。
  //
  // 旧实现切走会话就 abort 上一轮的流，导致「原本正在运行的会话一切换就停」
  // —— 后端因此收到 CancelledError，整轮生成作废。现在后台流继续读、继续
  // 写 session 缓存，切回该会话时直接看到完整结果。
  // 这里只把「当前展示的 loading 指示」跟随会话：若正在跑的会话不是当前
  // 会话，界面上的 loading 归当前会话（它自己有没有流由 isLoading 计算）。
  useEffect(() => {
    const active = activeStreamSessionIdsRef.current;
    setLoadingSessionId((prev) => {
      // 当前会话自己就在跑 → 保持
      if (currentSessionId !== null && active.has(currentSessionId)) return prev;
      // 其它会话在后台跑：不把它的 loading 显示到当前会话上
      if (prev !== null && !active.has(prev)) return prev;
      return null;
    });
  }, [currentSessionId]);

  // isLoading：按会话隔离 — 仅当前会话处于加载中时为 true
  const isLoading =
    loadingSessionId !== null &&
    (currentSessionId === null || currentSessionId === loadingSessionId || activeStreamSessionIdsRef.current.has(currentSessionId));

  // handleSend 会闭包捕获 isLoading，而排队 flush 用的可能是**上一帧**的
  // handleSend（effect 执行顺序早于 ref 更新 effect）。上一帧 isLoading 还是
  // true，排队的动作会被守卫再丢一次 —— 所以守卫读 ref，不读闭包。
  isLoadingRef.current = isLoading;

  // A2UI 排队动作的落地时机：等本轮流真正结束（isLoading 落下）再发。
  // 直接并发会撞上后端同会话的锁，而且两条流的 setSessions 会互相覆盖。
  useEffect(() => {
    if (isLoading) return;
    const queued = pendingA2uiRef.current.splice(0);
    if (queued.length === 0) return;
    // 只发最新一条：连点提交多次时，用户意图是「最后一次提交」。
    const last = queued[queued.length - 1];
    void handleSendRef.current?.(last.text, last.files, 'composer');
  }, [isLoading]);
  const handleStopGeneration = useCallback(() => {
    // 停止按钮只 abort **当前会话**的请求，不影响其它会话后台进行的流
    const stopKey = currentSessionId ?? loadingSessionId;
    if (stopKey) {
      abortControllersRef.current.get(stopKey)?.abort();
      abortControllersRef.current.delete(stopKey);
    }
    // 只清理当前会话的活跃标记（含后端重命名前后的 ID），不影响其他会话正在进行的流
    if (loadingSessionId) {
      activeStreamSessionIdsRef.current.delete(loadingSessionId);
      syncActiveStreams();
    }
    if (currentSessionId) {
      activeStreamSessionIdsRef.current.delete(currentSessionId);
      syncActiveStreams();
    }
    // 停在本轮待审批状态时，把悬挂的审批请求标记为已拒绝：
    // 否则运行已终止，审批面板却一直挂在消息上（点了也没有响应）。
    const stopSessionId = currentSessionId ?? loadingSessionId;
    if (stopSessionId) {
      setSessions((prev) =>
        prev.map((session) =>
          session.id === stopSessionId
            ? {
                ...session,
                messages: markStoppedTurn(session.messages),
              }
            : session
        )
      );
    }
    setLoadingSessionId(null);
    setRunStatus({ phase: 'done', label: '正在停止请求' });
  }, [loadingSessionId, currentSessionId]);

  const handleApprovalDecision = useCallback(
    async (
      approvalId: string,
      status: 'approved' | 'rejected',
      isApiApproval?: boolean,
      allowAll?: boolean,
      modifiedArguments?: Record<string, unknown>,
    ) => {
      const optimisticStatus = status === 'approved' ? 'approved' : 'rejected';
      const rollbackResult =
        '审批提交失败，已恢复待审批状态。请重试或检查后端服务。';

      // 乐观更新
      setSessions((prev) =>
        prev.map((session) => ({
          ...session,
          messages: session.messages.map((message) => ({
            ...message,
            toolCalls: message.toolCalls?.map((tool) =>
              tool.approvalId === approvalId
                ? {
                    ...tool,
                    status: optimisticStatus,
                    result:
                      status === 'approved'
                        ? allowAll
                          ? '已全部允许，本次会话不再询问。'
                          : '审批已通过，等待工具执行。'
                        : '审批已拒绝，工具不会执行。',
                  }
                : tool,
            ),
          })),
        })),
      );

      try {
        if (isApiApproval) {
          if (!currentSessionId) throw new Error('缺少会话 ID');
          await submitApiApproval(currentSessionId, status === 'approved', allowAll);
        } else {
          await submitApprovalDecision(
            approvalId,
            status,
            status === 'approved' ? 'approved from AgenticOS UI' : 'rejected from AgenticOS UI',
            modifiedArguments,
          );
        }
      } catch (err) {
        console.error('Approval error:', err);
        // 失败回滚：恢复 approval_required，保留审批面板
        setSessions((prev) =>
          prev.map((session) => ({
            ...session,
            messages: session.messages.map((message) => ({
              ...message,
              toolCalls: message.toolCalls?.map((tool) =>
                tool.approvalId === approvalId
                  ? {
                      ...tool,
                      status: 'approval_required' as const,
                      result: rollbackResult,
                    }
                  : tool,
              ),
            })),
          })),
        );
        setError('审批提交失败，请检查后端服务。');
      }
    },
    [setSessions, currentSessionId],
  );

  const handleSend = useCallback(
    /**
     * 发送一条用户消息。
     *
     * ``source`` 用于区分来源：
     * - ``composer``（默认）：输入框发送。流式进行中时直接忽略（防重复提交）。
     * - ``a2ui``：A2UI 界面上的按钮/表单提交。
     *
     * 为什么 A2UI 必须绕开 isLoading 守卫：界面是在**本轮流式过程中**
     * 推给前端的（tool_end 之后立刻下发，让用户先看到界面）。
     * 用户在这个窗口里填表、点提交时 isLoading 还是 true ——
     * 之前统一走 composer 路径，被守卫静默 return false，
     * 表现就是「点了提交按钮完全没反应」，连报错都没有。
     */
    async (
      text: string,
      files?: File[],
      source: 'composer' | 'a2ui' = 'composer',
    ): Promise<boolean> => {
      if (!text.trim() && (!files || files.length === 0)) return false;
      const streaming = isLoadingRef.current;
      if (source === 'composer' && streaming) return false;
      if (source === 'a2ui' && streaming) {
        // A2UI 界面是在**本轮流式过程中**下发的（tool_end 后立刻推送，
        // 让用户先看到界面）。用户在这个窗口里填完点提交时 isLoading 仍为 true。
        //
        // 不能像 composer 那样直接 return false（那是「点了完全没反应」的根因），
        // 也不能立刻并发发起新 run：后端同一会话持有锁，新 run 会排队到超时，
        // 而且两条流的 setSessions 会互相覆盖同一条助手消息。
        //
        // 做法：停掉当前这一轮（用户已经看到界面了，继续流没意义），
        // 把这条动作排进 pending，等 isLoading 落下后由 flush effect 发出。
        pendingA2uiRef.current.push({ text: text.trim(), files });
        const a2uiKey = currentSessionId ?? loadingSessionId;
        if (a2uiKey) {
          abortControllersRef.current.get(a2uiKey)?.abort();
          abortControllersRef.current.delete(a2uiKey);
          activeStreamSessionIdsRef.current.delete(a2uiKey);
          syncActiveStreams();
        }
        return true;
      }

      // 清除待处理的决策（用户开始新输入时）
      setPendingDecisions([]);

      const currentText = text.trim();
      let userMessage: Message | null = null;
      let targetId: string | null = null;
      let assistantMessageId: string | null = null;
      let hasStreamedContent = false;
      let hasAssistantActivity = false;
      let receivedPptArtifact: AgentPptArtifact | undefined;
      let receivedWebsiteArtifact: AgentWebsiteArtifact | undefined;
      let receivedSheetArtifact: AgentSheetArtifact | undefined;
      let receivedDocumentArtifact: AgentDocumentArtifact | undefined;
      const abortController = new AbortController();
      // 先按请求会话登记（targetId 可能在流中被后端重命名，见下方 rename 处理）
      const initialStreamKey = currentSessionId ?? `pending-${Date.now()}`;
      abortControllersRef.current.set(initialStreamKey, abortController);

      try {
        const attachments = files ? buildAttachments(files, attachmentUrlsRef.current) : [];
        const uploadedFiles = files && files.length > 0
          ? await prepareUploadedFiles(files, (label) => setRunStatus({ phase: 'thinking', label }))
          : [];

        // id 保留可解析的时间戳前缀（ChatMessage 用 parseInt(message.id) 推时间戳，
        // parseInt 在 '-' 处截断；backend-N 前缀判断不受影响），随机后缀避免同毫秒碰撞
        userMessage = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          role: 'user',
          text: currentText,
          attachments: attachments.length > 0 ? attachments : undefined,
        };

        const history = sessionsRef.current.find((s) => s.id === currentSessionId)?.messages || [];
        targetId = currentSessionId || userMessage.id;
        assistantMessageId = `${userMessage.id}-assistant`;

        queueMicrotask(() => {
          setLoadingSessionId(targetId);
          const isPpt = chatMode === 'ppt';
          const isWebsite = chatMode === 'website';
          setRunStatus({
            phase: isPpt ? 'generating_ppt' : 'thinking',
            label: isPpt ? '正在生成 PPT 内容与版式' : '大模型正在思考',
          });
          setInputValue('');
          setSessions((prev) => {
            const assistantMessage: Message = {
              id: assistantMessageId!,
              role: 'model',
              text: '',
              // 显式带时间：ChatMessage 不再从 id 里抠（历史消息 id 是
              // "backend-0"，抠出来是 NaN，刷新后时间会整块消失）
              createdAt: new Date().toISOString(),
              pptArtifact: isPpt ? { status: 'generating', mode: 'ppt' as const } : undefined,
              websiteArtifact: isWebsite ? { status: 'generating' } : undefined,
            };

            if (!currentSessionId) {
              const newSession: Session = {
                id: targetId!,
                title: currentText.slice(0, 20) + (currentText.length > 20 ? '...' : ''),
                messages: [userMessage!, assistantMessage],
                updatedAt: Date.now(),
                mode: chatMode,
                agentProfileId: selectedAgentProfileId,
                agentName: selectedAgent?.name,
              };
              return [newSession, ...prev];
            }
            return prev.map((s) =>
              s.id === currentSessionId
                ? { ...s, messages: [...s.messages, userMessage!, assistantMessage], updatedAt: Date.now() }
                : s,
            );
          });

          if (!currentSessionId) {
            setCurrentSessionId(targetId);
          }
        });

        await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

        // 注册活跃流会话（含可能的后端重命名）
        if (targetId) {
          activeStreamSessionIdsRef.current.add(targetId);
          syncActiveStreams();
        }

        const stateSessionIdForInput = () => targetId ?? currentSessionId ?? null;
        const response = await sendMessageStream(currentText, {
          sessionId: targetId,
          systemPrompt:
            currentSession || selectedAgentProfileId ? undefined : MODE_SYSTEM_PROMPTS[chatMode],
          responseMode: chatMode,
          agentProfileId: selectedAgentProfileId,
          approvalMode,
          planMode,
          files: uploadedFiles.length > 0 ? uploadedFiles : undefined,
          signal: abortController.signal,
          onSessionState: (state) => {
            applySessionState(targetId!, state);
            // 后端可能重命名 session_id：登记到活跃集合，并把 abort controller
            // 的 key 同步到新 ID —— 否则「停止」按新 ID 找不到 controller，
            // 切会话后的按会话 abort 也会失效。
            if (state.session_id) {
              activeStreamSessionIdsRef.current.add(state.session_id);
              syncActiveStreams();
              if (!abortControllersRef.current.has(state.session_id)) {
                abortControllersRef.current.set(state.session_id, abortController);
              }
            }
          },
          onRunStatus: (status: AgentRunStatus) => {
            const labelMap: Record<string, string> = {
              thinking: '思考中...',
              streaming: '正在回复...',
              generating_ppt: '正在生成 PPT...',
              rendering_ppt: '正在渲染预览...',
              rendering_website: '正在渲染网站...',
              done: '已完成',
              error: '出错了',
            };
            setRunStatus({ phase: status.phase, label: labelMap[status.phase] || status.label });
          },
          onPptArtifact: (pptArtifact) => {
            receivedPptArtifact = pptArtifact;
            const pptLanguage = 'ppt' as const;
            const nextArtifact: Artifact = {
              language: pptLanguage,
              artifactId: pptArtifact.artifact_id,
              html: pptArtifact.html,
              title: pptArtifact.title,
              slideCount: pptArtifact.slide_count,
              theme: pptArtifact.theme,
            };
            setArtifact(nextArtifact);
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? {
                              ...message,
                              // 消息快照映射统一走 artifactSnapshots（与回源挂载同一份）
                              pptArtifact: pptMessageArtifact(pptArtifact),
                            }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          // A2UI 声明式界面：累积消息序列写进这条助手消息。
          // 每条 a2ui 事件都可能只带一部分消息（先 createSurface 再补组件），
          // 所以按序追加，交给渲染器的 MessageProcessor 顺序消费。
          onChartMessages: (charts) => {
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? { ...message, chartMessages: charts }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          onA2uiMessages: (messages) => {
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? { ...message, a2uiMessages: messages }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          onDocumentArtifact: (docArtifact) => {
            if (docArtifact.session_id && docArtifact.session_id !== targetId) return;
            receivedDocumentArtifact = docArtifact;
            setArtifact({
              language: 'document',
              artifactId: docArtifact.artifact_id,
              title: docArtifact.title,
              snapshot: docArtifact.snapshot,
              charCount: docArtifact.char_count ?? 0,
              version: docArtifact.version,
            });
          },
          onSheetArtifact: (wsArtifact) => {
            if (wsArtifact.session_id && wsArtifact.session_id !== targetId) return;
            receivedSheetArtifact = wsArtifact;
            setArtifact({
              language: 'spreadsheet',
              artifactId: wsArtifact.artifact_id,
              title: wsArtifact.title,
              snapshot: wsArtifact.snapshot,
              sheetNames: wsArtifact.sheet_names ?? [],
              sheetCount: wsArtifact.sheet_count ?? 0,
              // 必须带上 version：版本条依赖 currentReference 变化来重新拉列表，
              // 缺了它同一会话里出新版本也不会刷新
              version: wsArtifact.version,
            });
          },
          onWebsiteArtifact: (wsArtifact) => {
            if (wsArtifact.session_id && wsArtifact.session_id !== targetId) return;
            receivedWebsiteArtifact = wsArtifact;
            // 刻意**不**把 wsArtifact.preview_url 带进 artifact：预览令牌只有
            // 15 分钟 TTL，存进内存后用户切走再切回（或点「重新打开产物」）
            // 时早已过期，iframe 会直接渲染 403 错误页。首帧走 preview_html
            // 内联 srcDoc（自包含、永不过期）；带签名的实时 URL 只在两个入口
            // 现用现签：「刷新」/会话恢复（GET /sessions/{id}/artifacts 每次都
            // 签新 token）和「重新打开产物」按钮（ChatMainArea 会先调
            // issueWebsitePreviewUrl 现签再打开）。切勿把这里的旧 token 复用进
            // 内存态 artifact。
            const nextArtifact: Artifact = {
              language: 'website',
              artifactId: wsArtifact.artifact_id,
              html: wsArtifact.preview_html,
              title: wsArtifact.title,
              projectSlug: wsArtifact.project_slug,
              stack: wsArtifact.stack,
              fileCount: wsArtifact.file_count,
            };
            setArtifact(nextArtifact);
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? {
                              ...message,
                              // 流式路径不落 previewUrl（令牌 15 分钟 TTL，见上）；
                              // 快照映射统一走 artifactSnapshots（与回源挂载同一份）
                              websiteArtifact: websiteMessageArtifact(wsArtifact),
                            }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          onBudget: (budget) => {
            setRunStatus((prev) =>
              prev.step === budget.step && prev.maxSteps === budget.maxSteps
                ? prev
                : { ...prev, step: budget.step, maxSteps: budget.maxSteps },
            );
          },
          onDelta: (_, fullText) => {
            hasStreamedContent = true;
            hasAssistantActivity = true;
            setRunStatus((prev) =>
              prev.phase === 'generating_ppt' || prev.phase === 'rendering_ppt' || prev.phase === 'rendering_website'
                ? prev
                : { phase: 'streaming', label: '大模型正在输出' },
            );
            // 批量更新：存储最新值，rAF 合并到每帧一次 setSessions
            latestDeltaRef.current = { fullText, isPpt: chatMode === 'ppt' };
            if (deltaFlushRaf.current == null) {
              deltaFlushRaf.current = requestAnimationFrame(() => {
                deltaFlushRaf.current = null;
                const delta = latestDeltaRef.current;
                const reasoning = latestReasoningRef.current;
                if (!delta && !reasoning) return;
                setSessions((prev) =>
                  prev.map((session) =>
                    session.id === targetId
                      ? {
                          ...session,
                          updatedAt: Date.now(),
                          messages: session.messages.map((message) =>
                            message.id === assistantMessageId
                              ? {
                                  ...message,
                                  ...(delta ? { text: delta.fullText } : {}),
                                  ...(mergeOrderedBlocks(message, delta, reasoning)),
                                  ...(delta?.isPpt ? {
                                    pptArtifact:
                                      message.pptArtifact?.status === 'ready' || receivedPptArtifact
                                        ? (message.pptArtifact?.status === 'ready' ? message.pptArtifact : { status: 'ready' as const, artifactId: receivedPptArtifact!.artifact_id })
                                        : { status: 'generating' as const },
                                  } : {}),
                                  ...(reasoning != null ? { reasoningText: reasoning } : {}),
                                }
                              : message,
                          ),
                        }
                      : session,
                  ),
                );
                latestDeltaRef.current = null;
                latestReasoningRef.current = null;
              });
            }
          },
          onReasoningDelta: (_, fullReasoning) => {
            hasAssistantActivity = true;
            // 批量更新：存储最新 reasoning，与 delta 共享同一个 rAF flush
            latestReasoningRef.current = fullReasoning;
            if (deltaFlushRaf.current == null) {
              deltaFlushRaf.current = requestAnimationFrame(() => {
                deltaFlushRaf.current = null;
                const delta = latestDeltaRef.current;
                const reasoning = latestReasoningRef.current;
                if (!delta && !reasoning) return;
                setSessions((prev) =>
                  prev.map((session) =>
                    session.id === targetId
                      ? {
                          ...session,
                          updatedAt: Date.now(),
                          messages: session.messages.map((message) =>
                            message.id === assistantMessageId
                              ? {
                                  ...message,
                                  ...(delta ? { text: delta.fullText } : {}),
                                  ...(mergeOrderedBlocks(message, delta, reasoning)),
                                  ...(delta?.isPpt ? {
                                    pptArtifact:
                                      message.pptArtifact?.status === 'ready' || receivedPptArtifact
                                        ? (message.pptArtifact?.status === 'ready' ? message.pptArtifact : { status: 'ready' as const, artifactId: receivedPptArtifact!.artifact_id })
                                        : { status: 'generating' as const },
                                  } : {}),
                                  ...(reasoning != null ? { reasoningText: reasoning } : {}),
                                }
                              : message,
                          ),
                        }
                      : session,
                  ),
                );
                latestDeltaRef.current = null;
                latestReasoningRef.current = null;
              });
            }
          },
          onToolCalls: (toolCalls) => {
            hasAssistantActivity = true;
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? {
                              ...message,
                              toolCalls,
                              blocks: syncToolBlocks(
                                message.blocks || [],
                                toolCalls,
                                message.toolCalls || [],
                              ),
                            }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          onUserDecision: (decision: unknown) => {
            const d = normalizeDecision(decision);
            if (!d) return;
            setPendingDecisions((prev) => {
              // 避免重复添加
              if (prev.some((item) => item.decision_id === d.decision_id)) return prev;
              return [...prev, d];
            });
          },
          onUserInputRequired: (input) => {
            // 带上来源会话：后台流（用户已切走）触发的人工输入必须只在
            // 它自己的会话里显示/提交，否则会提交到用户当前所在的错误会话。
            const base = input as unknown as UserInputRequest;
            const tagged: UserInputRequest = {
              ...base,
              // 后端已带 session_id 时优先用它；否则用本流的目标会话兜底
              session_id: base.session_id || stateSessionIdForInput() || '',
            };
            onUserInputRequired?.(tagged);
          },
          onApiApprovalRequired: (approval) => {
            onApiApprovalRequired?.(approval as unknown as ApiApprovalRequest);
          },
        });

        // 截断提示
        if (response.finishReason === 'length') {
          toast.warning('回复被截断：输出达到 token 上限，内容可能不完整。可以发送「继续」接续，或精简需求后重试。', {
            duration: 8000,
          });
        }

        const pptArtifact = response.pptArtifact || receivedPptArtifact;
        const websiteArtifact = response.websiteArtifact || receivedWebsiteArtifact;
        const sheetArtifact = response.sheetArtifact || receivedSheetArtifact;
        const documentArtifact = response.documentArtifact || receivedDocumentArtifact;

        setSessions((prev) =>
          prev.map((session) =>
            session.id === targetId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map((message) =>
                    message.id === assistantMessageId
                      ? {
                          ...message,
                          text: response.text,
                          toolCalls: response.toolCalls,
                          pptArtifact: pptArtifact
                            ? {
                                status: 'ready',
                                artifactId: pptArtifact.artifact_id,
                                title: pptArtifact.title,
                                slideCount: pptArtifact.slide_count,
                                html: pptArtifact.html,
                                theme: pptArtifact.theme,
                              }
                            : undefined,
                          websiteArtifact: websiteArtifact
                            ? {
                                status: 'ready',
                                artifactId: websiteArtifact.artifact_id,
                                title: websiteArtifact.title,
                                projectSlug: websiteArtifact.project_slug,
                                stack: websiteArtifact.stack,
                                html: websiteArtifact.preview_html,
                              }
                            : undefined,
                          // 表格 / 文档也必须回写到消息上：面板收起后
                          // ChatMainArea 靠这个字段判断「有没有可重新打开的
                          // 产物」。只 setArtifact 不写消息的话，一收起就
                          // 再也找不到入口了（用户报的正是这个）。
                          // snapshot 体量大，这里只记引用，重开时回源。
                          sheetArtifact: sheetArtifact
                            ? {
                                status: 'ready',
                                artifactId: sheetArtifact.artifact_id,
                                title: sheetArtifact.title,
                                sheetNames: sheetArtifact.sheet_names ?? [],
                                sheetCount: sheetArtifact.sheet_count ?? 0,
                              }
                            : undefined,
                          documentArtifact: documentArtifact
                            ? {
                                status: 'ready',
                                artifactId: documentArtifact.artifact_id,
                                title: documentArtifact.title,
                                charCount: documentArtifact.char_count ?? 0,
                              }
                            : undefined,
                        }
                      : message,
                  ),
                  summary: response.sessionState?.summary ?? session.summary,
                  contextCompressed:
                    response.sessionState?.context_compressed ?? session.contextCompressed,
                  storage: response.sessionState?.storage ?? session.storage,
                  lastUsage: response.sessionState?.last_usage ?? session.lastUsage,
                  latencyMs: response.sessionState?.last_latency_ms ?? session.latencyMs,
                  llmCalls: response.sessionState?.last_llm_calls ?? session.llmCalls,
                }
              : session,
          ),
        );

        const htmlMatch = /```html\n([\s\S]*?)\n```/.exec(response.text);
        const svgMatch = /```svg\n([\s\S]*?)\n```/.exec(response.text);
        if (documentArtifact)
          setArtifact({
            language: 'document',
            artifactId: documentArtifact.artifact_id,
            title: documentArtifact.title,
            snapshot: documentArtifact.snapshot,
            charCount: documentArtifact.char_count ?? 0,
            version: documentArtifact.version,
          });
        else if (sheetArtifact)
          setArtifact({
            language: 'spreadsheet',
            artifactId: sheetArtifact.artifact_id,
            title: sheetArtifact.title,
            snapshot: sheetArtifact.snapshot,
            sheetNames: sheetArtifact.sheet_names ?? [],
            sheetCount: sheetArtifact.sheet_count ?? 0,
            version: sheetArtifact.version,
          });
        else if (pptArtifact)
          setArtifact({
            language: 'ppt' as const,
            artifactId: pptArtifact.artifact_id,
            html: pptArtifact.html,
            title: pptArtifact.title,
            slideCount: pptArtifact.slide_count,
            theme: pptArtifact.theme,
          });
        else if (websiteArtifact)
          setArtifact({
            language: 'website',
            artifactId: websiteArtifact.artifact_id,
            html: websiteArtifact.preview_html,
            title: websiteArtifact.title,
            projectSlug: websiteArtifact.project_slug,
            stack: websiteArtifact.stack,
            fileCount: websiteArtifact.file_count,
          });
        else if (htmlMatch) setArtifact({ code: htmlMatch[1], language: 'html' });
        else if (svgMatch) setArtifact({ code: svgMatch[1], language: 'svg' });

        setRunStatus({ phase: 'done', label: '本轮回复已完成' });

        if (history.length === 0 || (history.length + 2) % 4 === 0) {
          generateTitle([
            ...history,
            userMessage,
            {
              id: assistantMessageId,
              role: 'model',
              text: response.text,
              toolCalls: response.toolCalls,
            },
          ])
            .then((title) => {
              setSessions((prev) =>
                prev.map((s) => (s.id === targetId ? { ...s, title } : s)),
              );
            })
            .catch((err) => {
              // 标题生成失败不影响主流程，仅记录
              console.warn('Generate title failed:', err);
            });
        }
        return true;
      } catch (err) {
        if (
          abortController.signal.aborted ||
          (err instanceof DOMException && err.name === 'AbortError')
        ) {
          if (targetId && assistantMessageId) {
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? {
                              ...message,
                              text: message.text.trim()
                                ? `${message.text.trimEnd()}\n\n已停止请求。`
                                : '已停止请求。',
                            }
                          : message,
                      ),
                    }
                  : session,
              ),
            );

            // 中断时保留已有的 artifact（PPT / Website）
            const currentSession = sessionsRef.current.find(s => s.id === targetId);
            const currentMessage = currentSession?.messages.find(m => m.id === assistantMessageId);
            if (currentMessage?.pptArtifact?.status === 'ready' && currentMessage.pptArtifact.html) {
              setArtifact({
                language: 'ppt',
                artifactId: currentMessage.pptArtifact.artifactId,
                html: currentMessage.pptArtifact.html,
                title: currentMessage.pptArtifact.title || '',
                slideCount: currentMessage.pptArtifact.slideCount || 0,
                theme: currentMessage.pptArtifact.theme,
              });
            } else if (currentMessage?.websiteArtifact?.status === 'ready' && currentMessage.websiteArtifact.html) {
              setArtifact({
                language: 'website',
                artifactId: currentMessage.websiteArtifact.artifactId || '',
                html: currentMessage.websiteArtifact.html,
                title: currentMessage.websiteArtifact.title || '',
                projectSlug: currentMessage.websiteArtifact.projectSlug || '',
              });
            }
          }
          setRunStatus({ phase: 'done', label: '已停止请求' });
          return true; // 用户主动停止：消息已入列，附件可清理
        }
        console.error('Send error:', err);
        if (targetId && assistantMessageId) {
          setSessions((prev) =>
            prev.map((session) =>
              session.id === targetId
                ? {
                    ...session,
                    messages: session.messages.filter(
                      (message) =>
                        hasStreamedContent || hasAssistantActivity || message.id !== assistantMessageId,
                    ),
                  }
                : session,
            ),
          );
        }
        setError(err instanceof Error ? err.message : '发送消息失败，请检查后端服务或网络连接。');
        setRunStatus({ phase: 'error', label: '本轮回复失败' });
        return false; // 失败：让调用方保留用户输入（如未上传成功的附件）
      } finally {
        // 按 controller 值清理（会话可能已被后端重命名，key 不一定是发起时那个）
        for (const [key, controller] of abortControllersRef.current) {
          if (controller === abortController) abortControllersRef.current.delete(key);
        }
        if (targetId) {
          activeStreamSessionIdsRef.current.delete(targetId);
          syncActiveStreams();
        }
        setLoadingSessionId((prev) => (prev === targetId || prev === null ? null : prev));
      }
    },
    [
      // sessions 经 sessionsRef 读取（流式期间每帧 setSessions，依赖会导致本回调每帧换引用）
      currentSessionId,
      currentSession,
      chatMode,
      approvalMode,
      selectedAgentProfileId,
      selectedAgent,
      isLoading,
      setSessions,
      setCurrentSessionId,
      applySessionState,
      setArtifact,
      setInputValue,
      onUserInputRequired,
      onApiApprovalRequired,
      loadingSessionId,
      setActiveStreamIds,
    ],
  );

  // 供排队 effect 调用（effect 不能直接依赖 handleSend：它是每轮重建的 callback，
  // 依赖它会让 effect 在流式期间反复触发）
  useEffect(() => {
    handleSendRef.current = handleSend;
  }, [handleSend]);

  const handleDecisionMade = useCallback(
    async (decisionId: string, answer: string) => {
      // 乐观移除已回答的决策；先捕获原对象，失败时回滚放回面板供重试
      let removedDecision: UserDecision | undefined;
      setPendingDecisions((prev) => {
        removedDecision = prev.find((d) => d.decision_id === decisionId);
        return prev.filter((d) => d.decision_id !== decisionId);
      });
      // 调用 API 解析决策（后端工具正在阻塞等待）
      try {
        await submitUserDecision(decisionId, answer);
      } catch (err) {
        console.error('Decision submit error:', err);
        if (removedDecision) {
          setPendingDecisions((prev) =>
            prev.some((d) => d.decision_id === decisionId) ? prev : [...prev, removedDecision as UserDecision],
          );
        }
        setError('决策提交失败，请重试或检查后端服务。');
      }
    },
    [setError],
  );

  return {
    isLoading,
    error,
    setError,
    runStatus,
    setRunStatus,
    abortControllersRef,
    pendingDecisions,
    handleSend,
    handleStopGeneration,
    handleApprovalDecision,
    handleDecisionMade,
    /** 正在流式运行的会话集合（侧栏呼吸点等环境感知 UI 消费） */
    activeStreamIds,
  };
}
