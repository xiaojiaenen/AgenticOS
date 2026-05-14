import { useState, useRef, useCallback } from 'react';
import { Message, Session, Attachment, Artifact } from '../types';
import {
  sendMessageStream,
  generateTitle,
  submitApprovalDecision,
  AgentSessionState,
  AgentPptArtifact,
  AgentRunStatus,
} from '../services/agentService';
import { AgentProfile } from '../services/agentProfileService';
import { MODE_SYSTEM_PROMPTS } from '../constants/modePrompts';

interface UseChatStreamDeps {
  sessions: Session[];
  currentSessionId: string | null;
  currentSession: Session | null;
  chatMode: 'general' | 'ppt' | 'website';
  selectedAgentProfileId: number | null;
  selectedAgent: AgentProfile | null;
  setSessions: React.Dispatch<React.SetStateAction<Session[]>>;
  setCurrentSessionId: React.Dispatch<React.SetStateAction<string | null>>;
  applySessionState: (sessionId: string, state: AgentSessionState) => void;
  setArtifact: React.Dispatch<React.SetStateAction<Artifact | null>>;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
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
}: UseChatStreamDeps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<{
    phase: 'idle' | 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'done' | 'error';
    label: string;
  }>({ phase: 'idle', label: '已就绪' });

  const abortControllerRef = useRef<AbortController | null>(null);

  // 自动收起错误提示
  // 注意：这个 effect 在 hook 中无法使用，需要在调用方处理
  // 我们返回 error 和 setError，由调用方管理

  const handleStopGeneration = useCallback(() => {
    abortControllerRef.current?.abort();
    setRunStatus({ phase: 'done', label: '正在停止请求' });
  }, []);

  const handleApprovalDecision = useCallback(
    async (approvalId: string, status: 'approved' | 'rejected') => {
      const optimisticStatus = status === 'approved' ? 'approved' : 'rejected';
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
                        ? '审批已通过，等待工具执行。'
                        : '审批已拒绝，工具不会执行。',
                  }
                : tool,
            ),
          })),
        })),
      );

      try {
        await submitApprovalDecision(
          approvalId,
          status,
          status === 'approved' ? 'approved from AgenticOS UI' : 'rejected from AgenticOS UI',
        );
      } catch (err) {
        console.error('Approval error:', err);
        setError('审批提交失败，请检查后端服务。');
      }
    },
    [setSessions],
  );

  const handleSend = useCallback(
    async (text: string, files?: File[]) => {
      if ((!text.trim() && (!files || files.length === 0)) || isLoading) return;

      const currentText = text.trim();
      let userMessage: Message | null = null;
      let targetId: string | null = null;
      let assistantMessageId: string | null = null;
      let hasStreamedContent = false;
      let hasAssistantActivity = false;
      let receivedPptArtifact: AgentPptArtifact | undefined;
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      try {
        const attachments: Attachment[] = (files || []).map((file) => ({
          name: file.name,
          type: file.type,
          url: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
        }));

        userMessage = {
          id: Date.now().toString(),
          role: 'user',
          text: currentText,
          attachments: attachments.length > 0 ? attachments : undefined,
        };

        const history = sessions.find((s) => s.id === currentSessionId)?.messages || [];
        targetId = currentSessionId || userMessage.id;
        assistantMessageId = `${userMessage.id}-assistant`;
        const outboundMessage =
          attachments.length > 0
            ? `${currentText}\n\n附带文件：${attachments.map((item) => item.name).join('、')}\n说明：当前后端暂不支持直接解析附件内容，请结合文件名理解需求。`
            : currentText;

        if (attachments.length > 0) {
          setError('当前后端暂不支持直接解析附件内容，本次仅向模型发送文本和文件名。');
        }

        queueMicrotask(() => {
          setIsLoading(true);
          setRunStatus({
            phase: chatMode === 'ppt' ? 'generating_ppt' : 'thinking',
            label: chatMode === 'ppt' ? '正在生成 PPT 内容与版式' : '大模型正在思考',
          });
          setInputValue('');
          setSessions((prev) => {
            const assistantMessage: Message = {
              id: assistantMessageId!,
              role: 'model',
              text: '',
              pptArtifact: chatMode === 'ppt' ? { status: 'generating' } : undefined,
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

        const response = await sendMessageStream(outboundMessage, {
          sessionId: targetId,
          systemPrompt:
            currentSession || selectedAgentProfileId ? undefined : MODE_SYSTEM_PROMPTS[chatMode],
          responseMode: chatMode,
          agentProfileId: selectedAgentProfileId,
          signal: abortController.signal,
          onSessionState: (state) => {
            applySessionState(targetId!, state);
          },
          onRunStatus: (status: AgentRunStatus) => {
            setRunStatus({ phase: status.phase, label: status.label });
          },
          onPptArtifact: (pptArtifact) => {
            receivedPptArtifact = pptArtifact;
            const nextArtifact: Artifact = {
              language: 'ppt',
              artifactId: pptArtifact.artifact_id,
              html: pptArtifact.html,
              title: pptArtifact.title,
              slideCount: pptArtifact.slide_count,
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
              prev.phase === 'generating_ppt' || prev.phase === 'rendering_ppt'
                ? prev
                : { phase: 'streaming', label: '大模型正在输出' },
            );
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? chatMode === 'ppt'
                            ? {
                                ...message,
                                text: fullText,
                                pptArtifact:
                                  message.pptArtifact?.status === 'ready'
                                    ? message.pptArtifact
                                    : { status: 'generating' },
                              }
                            : { ...message, text: fullText }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
          },
          onReasoningDelta: (_, fullReasoning) => {
            hasAssistantActivity = true;
            setSessions((prev) =>
              prev.map((session) =>
                session.id === targetId
                  ? {
                      ...session,
                      updatedAt: Date.now(),
                      messages: session.messages.map((message) =>
                        message.id === assistantMessageId
                          ? { ...message, reasoningText: fullReasoning }
                          : message,
                      ),
                    }
                  : session,
              ),
            );
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
        });

        const pptArtifact = response.pptArtifact || receivedPptArtifact;

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
                          reasoningText: response.reasoningText ?? message.reasoningText,
                          toolCalls: response.toolCalls,
                          pptArtifact: pptArtifact
                            ? {
                                status: 'ready',
                                artifactId: pptArtifact.artifact_id,
                                title: pptArtifact.title,
                                slideCount: pptArtifact.slide_count,
                                html: pptArtifact.html,
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
            language: 'ppt',
            artifactId: pptArtifact.artifact_id,
            html: pptArtifact.html,
            title: pptArtifact.title,
            slideCount: pptArtifact.slide_count,
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
        setIsLoading(false);
      }
    },
    [
      sessions,
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
    ],
  );

  return {
    isLoading,
    error,
    setError,
    runStatus,
    setRunStatus,
    abortControllerRef,
    handleSend,
    handleStopGeneration,
    handleApprovalDecision,
  };
}
