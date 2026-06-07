import { useState, useRef, useCallback } from 'react';
import { Message, Session, Attachment, Artifact } from '../types';
import {
  sendMessageStream,
  generateTitle,
  submitApprovalDecision,
  submitUserDecision,
  AgentSessionState,
  AgentPptArtifact,
  AgentWebsiteArtifact,
  AgentRunStatus,
} from '../services/agentService';
import { AgentProfile } from '../services/agentProfileService';
import { uploadFiles } from '../services/fileService';
import { MODE_SYSTEM_PROMPTS } from '../constants/modePrompts';
import { UserDecision, normalizeDecision } from '../components/chat/DecisionPanel';
import { toast } from '../components/ui/Toast';

// ---------------------------------------------------------------------------
// extracted helpers
// ---------------------------------------------------------------------------

function buildAttachments(files: File[]): Attachment[] {
  return files.map((file) => ({
    name: file.name,
    type: file.type,
    url: file.type.startsWith('image/') ? URL.createObjectURL(file) : '',
  }));
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
  const [pendingDecisions, setPendingDecisions] = useState<UserDecision[]>([]);
  const [runStatus, setRunStatus] = useState<{
    phase: 'idle' | 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'rendering_website' | 'ppt_fixing' | 'done' | 'error';
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
        const attachments = files ? buildAttachments(files) : [];
        const uploadedFiles = files && files.length > 0
          ? await prepareUploadedFiles(files, (label) => setRunStatus({ phase: 'thinking', label }))
          : [];

        userMessage = {
          id: Date.now().toString(),
          role: 'user',
          text: currentText,
          attachments: attachments.length > 0 ? attachments : undefined,
        };

        const history = sessions.find((s) => s.id === currentSessionId)?.messages || [];
        targetId = currentSessionId || userMessage.id;
        assistantMessageId = `${userMessage.id}-assistant`;

        queueMicrotask(() => {
          setIsLoading(true);
          setRunStatus({
            phase: (chatMode === 'ppt') ? 'generating_ppt' : 'thinking',
            label: (chatMode === 'ppt') ? '正在生成 PPT 内容与版式' : '大模型正在思考',
          });
          setInputValue('');
          setSessions((prev) => {
            const assistantMessage: Message = {
              id: assistantMessageId!,
              role: 'model',
              text: '',
              pptArtifact: (chatMode === 'ppt') ? { status: 'generating', mode: 'ppt' as const } : undefined,
              websiteArtifact: (chatMode === 'website') ? { status: 'generating' } : undefined,
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
          },
          onRunStatus: (status: AgentRunStatus) => {
            const labelMap: Record<string, string> = {
              thinking: '思考中...',
              streaming: '正在回复...',
              generating_ppt: '正在生成 PPT...',
              rendering_ppt: '正在渲染预览...',
              rendering_website: '正在渲染网站...',
              ppt_fixing: 'PPT 需要修复，正在自动处理...',
              done: '已完成',
              error: '出错了',
            };
            setRunStatus({ phase: status.phase, label: labelMap[status.phase] || status.label });

            // 当收到 ppt_fixing phase 时，自动发送修复请求
            if (status.phase === 'ppt_fixing') {
              console.log('[PPT] ppt_fixing detected, will auto-send fix request');
              // 延迟500ms后自动发送修复请求，让前端有时间更新状态
              setTimeout(() => {
                handleSend('请修复PPT问题并重新生成', true);
              }, 500);
            }
          },
          onPptArtifact: (pptArtifact) => {
            console.log('[PPT] onPptArtifact received:', pptArtifact.artifact_id, 'html length:', pptArtifact.html?.length);
            receivedPptArtifact = pptArtifact;
            const pptLanguage = 'ppt' as const;
            const nextArtifact: Artifact = {
              language: pptLanguage,
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
                                mode: pptLanguage,
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
                                  message.pptArtifact?.status === 'ready' || receivedPptArtifact
                                    ? (message.pptArtifact?.status === 'ready' ? message.pptArtifact : { status: 'ready' as const, artifactId: receivedPptArtifact!.artifact_id })
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
          onUserDecision: (decision: unknown) => {
            const d = normalizeDecision(decision);
            if (!d) return;
            setPendingDecisions((prev) => {
              // 避免重复添加
              if (prev.some((item) => item.decision_id === d.decision_id)) return prev;
              return [...prev, d];
            });
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
