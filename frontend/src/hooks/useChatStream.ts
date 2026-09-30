// @ts-nocheck
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
  AgentRunStatus,
  UserInputRequest,
  ApiApprovalRequest,
} from '../services/agentService';
import { AgentProfile } from '../services/agentProfileService';
import { uploadFiles } from '../services/fileService';
import { MODE_SYSTEM_PROMPTS } from '../constants/modePrompts';
import { UserDecision, normalizeDecision } from '../components/chat/DecisionPanel';
import { toast } from '../components/ui/Toast';

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
  chatMode: 'general' | 'ppt' | 'website' | 'email' | 'bigdata';
  selectedAgentProfileId: number | null;
  selectedAgent: AgentProfile | null;
  setSessions: React.Dispatch<React.SetStateAction<Session[]>>;
  setCurrentSessionId: React.Dispatch<React.SetStateAction<string | null>>;
  applySessionState: (sessionId: string, state: AgentSessionState) => void;
  setArtifact: React.Dispatch<React.SetStateAction<Artifact | null>>;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
  onUserInputRequired?: (input: UserInputRequest) => void;
  onApiApprovalRequired?: (approval: ApiApprovalRequest) => void;
}

export function useChatStream({
  sessions,
  currentSessionId,
  currentSession,
  chatMode,
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
  const [error, setError] = useState<string | null>(null);
  const [pendingDecisions, setPendingDecisions] = useState<UserDecision[]>([]);
  const [runStatus, setRunStatus] = useState<{
    phase: 'idle' | 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'rendering_website' | 'done' | 'error';
    label: string;
  }>({ phase: 'idle', label: '已就绪' });

  const abortControllerRef = useRef<AbortController | null>(null);
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

  // Cleanup rAF + 撤销本轮创建的附件 blob URL + abort 未完成请求 on unmount
  useEffect(() => () => {
    if (deltaFlushRaf.current != null) cancelAnimationFrame(deltaFlushRaf.current);
    abortControllerRef.current?.abort();
    for (const url of attachmentUrlsRef.current) {
      URL.revokeObjectURL(url);
    }
    attachmentUrlsRef.current = [];
  }, []);

  // 切换会话时：abort 旧 AbortController，并重置非当前会话的 isLoading
  useEffect(() => {
    const active = activeStreamSessionIdsRef.current;
    const hasActiveForCurrent = currentSessionId !== null && active.has(currentSessionId);
    if (abortControllerRef.current && currentSessionId !== null && !hasActiveForCurrent && active.size > 0) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    // 切到无关会话时重置 loading
    setLoadingSessionId((prev) => {
      if (prev && currentSessionId !== null && prev !== currentSessionId && !active.has(currentSessionId)) {
        return null;
      }
      return prev;
    });
  }, [currentSessionId]);

  // isLoading：按会话隔离 — 仅当前会话处于加载中时为 true
  const isLoading =
    loadingSessionId !== null &&
    (currentSessionId === null || currentSessionId === loadingSessionId || activeStreamSessionIdsRef.current.has(currentSessionId));

  const handleStopGeneration = useCallback(() => {
    // 停止按钮真正 abort 当前请求
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    // 只清理当前会话的活跃标记（含后端重命名前后的 ID），不影响其他会话正在进行的流
    if (loadingSessionId) {
      activeStreamSessionIdsRef.current.delete(loadingSessionId);
    }
    if (currentSessionId) {
      activeStreamSessionIdsRef.current.delete(currentSessionId);
    }
    setLoadingSessionId(null);
    setRunStatus({ phase: 'done', label: '正在停止请求' });
  }, [loadingSessionId, currentSessionId]);

  const handleApprovalDecision = useCallback(
    async (approvalId: string, status: 'approved' | 'rejected', isApiApproval?: boolean, allowAll?: boolean) => {
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
    async (text: string, files?: File[]) => {
      if ((!text.trim() && (!files || files.length === 0)) || isLoading) return;

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
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

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
                ? { ...s, messages: [...s.messages, userMessage, assistantMessage], updatedAt: Date.now() }
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
        }

        const response = await sendMessageStream(currentText, {
          sessionId: targetId,
          systemPrompt:
            currentSession || selectedAgentProfileId ? undefined : MODE_SYSTEM_PROMPTS[chatMode],
          responseMode: chatMode,
          agentProfileId: selectedAgentProfileId,
          files: uploadedFiles.length > 0 ? uploadedFiles : undefined,
          signal: abortController.signal,
          onSessionState: (state) => {
            applySessionState(targetId!, state);
            // 后端可能重命名 session_id，登记到活跃集合，避免误 abort
            if (state.session_id) {
              activeStreamSessionIdsRef.current.add(state.session_id);
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
                              pptArtifact: {
                                status: 'ready',
                                artifactId: pptArtifact.artifact_id,
                                title: pptArtifact.title,
                                slideCount: pptArtifact.slide_count,
                                html: pptArtifact.html,
                                mode: pptLanguage,
                                theme: pptArtifact.theme,
                              },
                            }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          onWebsiteArtifact: (wsArtifact) => {
            if (wsArtifact.session_id && wsArtifact.session_id !== targetId) return;
            receivedWebsiteArtifact = wsArtifact;
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
                              websiteArtifact: {
                                status: 'ready',
                                artifactId: wsArtifact.artifact_id,
                                title: wsArtifact.title,
                                projectSlug: wsArtifact.project_slug,
                                stack: wsArtifact.stack,
                                html: wsArtifact.preview_html,
                              },
                            }
                          : message,
                      ),
                    }
                  : session,
              ),
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
                          ? { ...message, toolCalls }
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
            onUserInputRequired?.(input as unknown as UserInputRequest);
          },
          onApiApprovalRequired: (approval) => {
            onApiApprovalRequired?.(approval as unknown as ApiApprovalRequest);
          },
        });

        // 截断提示
        if (response.finishReason === 'length') {
          toast('回复被截断：输出达到 token 上限，内容可能不完整。可以发送「继续」接续，或精简需求后重试。', {
            variant: 'warning',
            duration: 8000,
          });
        }

        const pptArtifact = response.pptArtifact || receivedPptArtifact;
        const websiteArtifact = response.websiteArtifact || receivedWebsiteArtifact;

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
        if (pptArtifact)
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
          ]).then((title) => {
            setSessions((prev) =>
              prev.map((s) => (s.id === targetId ? { ...s, title } : s)),
            );
          });
        }
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
          return;
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
      } finally {
        if (abortControllerRef.current === abortController) {
          abortControllerRef.current = null;
        }
        if (targetId) {
          activeStreamSessionIdsRef.current.delete(targetId);
        }
        setLoadingSessionId((prev) => (prev === targetId || prev === null ? null : prev));
      }
    },
    [
      // sessions 经 sessionsRef 读取（流式期间每帧 setSessions，依赖会导致本回调每帧换引用）
      currentSessionId,
      currentSession,
      chatMode,
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
    ],
  );

  const handleDecisionMade = useCallback(
    async (decisionId: string, answer: string) => {
      // 移除已回答的决策
      setPendingDecisions((prev) => prev.filter((d) => d.decision_id !== decisionId));
      // 调用 API 解析决策（后端工具正在阻塞等待）
      try {
        await submitUserDecision(decisionId, answer);
      } catch (err) {
        console.error('Decision submit error:', err);
        setError('决策提交失败，请检查后端服务。');
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
    abortControllerRef,
    pendingDecisions,
    handleSend,
    handleStopGeneration,
    handleApprovalDecision,
    handleDecisionMade,
  };
}
