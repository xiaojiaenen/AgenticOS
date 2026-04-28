import React, { useState, useEffect, useRef } from 'react';
import { flushSync } from 'react-dom';
import { motion, AnimatePresence, useScroll, useTransform } from 'motion/react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from '../components/chat/Sidebar';
import { ChatInput, ChatInputHandle } from '../components/chat/ChatInput';
import { ChatTimeline } from '../components/chat/ChatTimeline';
import { ChatSearch } from '../components/chat/ChatSearch';
import { MessagesList } from '../components/chat/MessagesList';
import { ArtifactPanel } from '../components/chat/ArtifactPanel';
import { DragOverlay } from '../components/chat/DragOverlay';
import { PendingApprovalPanel } from '../components/chat/PendingApprovalPanel';
import { PptArtifactPanel } from '../components/ppt/PptArtifactPanel';
import { useChatSearch } from '../hooks/useChatSearch';
import { Artifact, Message, Session, Attachment } from '../types';
import { sendMessageStream, generateTitle, submitApprovalDecision, AgentSessionState, AgentPptArtifact, AgentRunStatus } from '../services/agentService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';
import { RandomMascot } from '../components/ui/RandomMascot';
import { AlertCircleIcon, MascotCool, ChevronDownIcon } from '../components/ui/AnimatedIcons';
import { cn } from '../lib/utils';

const MODE_SYSTEM_PROMPTS: Record<'general' | 'ppt' | 'website', string> = {
  general: '你是 AgenticOS 的通用智能助理，请优先给出准确、清晰、可执行的回答。',
  ppt: `你是 AgenticOS 的演示文稿设计助手。请先理解用户的受众、目标和材料，再生成结构化 PPT deck。

输出要求：
1. 必须返回一个 fenced code block，语言名固定为 pptdeck。
2. code block 内必须是合法 JSON，不要写注释。
3. JSON schema:
{
  "title": "演示文稿标题",
  "subtitle": "一句副标题",
  "author": "可选作者",
  "theme": "executive | product | minimal",
  "slides": [
    {
      "type": "cover | section | bullets | imageText | comparison | timeline | stats | chart | quote | closing",
      "eyebrow": "可选短标签",
      "title": "页面标题",
      "subtitle": "可选副标题",
      "body": "可选正文，控制在 60 字以内",
      "items": ["每页 3-5 个短要点，每个 12-22 字"],
      "leftTitle": "对比页左栏标题",
      "rightTitle": "对比页右栏标题",
      "leftItems": ["左栏要点"],
      "rightItems": ["右栏要点"],
      "stats": [{"value": "3x", "label": "效率提升", "caption": "可选说明"}],
      "chart": {"type": "bar | line | donut", "labels": ["A", "B", "C"], "values": [35, 62, 88], "unit": "%"},
      "timeline": [{"label": "01", "title": "阶段标题", "body": "可选说明"}],
      "quote": "引用页金句",
      "author": "引用来源"
    }
  ]
}
4. 内容要比普通大纲更丰满：默认生成 8-12 页，并至少包含 1 页 chart、1 页 stats、1 页 comparison、1 页 timeline。
5. 每页必须有明确结论，不要只有标题；不要连续 2 页使用同一种 type。
6. 如果没有真实数据，可以生成“示意数据”，但要在说明里标注为示意。
7. 在 code block 后，用 2-3 句话说明设计思路。用户界面会隐藏 code block，所以说明要自然，不要提 JSON。`,
  website: '你是 AgenticOS 的网站与前端助手，请优先提供页面结构、交互说明和可运行代码。',
};

export const Chat = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const initialMessage = location.state?.initialMessage as string | undefined;

  const [sessions, setSessions] = useState<Session[]>(() => {
    const saved = localStorage.getItem('chat_sessions');
    return saved ? JSON.parse(saved) : [];
  });
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [chatMode, setChatMode] = useState<'general' | 'ppt' | 'website'>((location.state as any)?.mode || 'general');
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>((location.state as any)?.agentProfileId || null);
  const currentSession = sessions.find(s => s.id === currentSessionId);
  const selectedAgent = agentProfiles.find(agent => agent.id === selectedAgentProfileId) || null;

  const {
    searchQuery, setSearchQuery, showSearch, setShowSearch,
    searchCurrentIndex, searchMatches, nextMatch, prevMatch, activeMatchId
  } = useChatSearch(currentSession);

  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [error, setError] = useState<string | null>(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [runStatus, setRunStatus] = useState<{phase: 'idle' | 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'done' | 'error'; label: string}>({
    phase: 'idle',
    label: '已就绪',
  });
  const [isSidebarHiddenByArtifact, setIsSidebarHiddenByArtifact] = useState(false);
  const [visibleSessionsCount, setVisibleSessionsCount] = useState(10);
  const [isDragging, setIsDragging] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<ChatInputHandle>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const currentSessionMessages = currentSession?.messages ?? [];
  const isStreamingResponse = isLoading && currentSessionMessages[currentSessionMessages.length - 1]?.role === 'model';
  const isWideConversation = !artifact && !isMobile;
  const pendingApprovals = React.useMemo(
    () => currentSessionMessages.flatMap(message => message.toolCalls || []).filter(tool => tool.status === 'approval_required' && tool.approvalId),
    [currentSessionMessages],
  );

  // 处理会话切换时的模式同步
  useEffect(() => {
    if (currentSessionId && currentSession?.mode) {
      setChatMode(currentSession.mode);
      setSelectedAgentProfileId(currentSession.agentProfileId ?? null);
    }
  }, [currentSessionId, currentSession?.mode, currentSession?.agentProfileId]);

  useEffect(() => {
    getMyAgents()
      .then((response) => {
        setAgentProfiles(response.items);
        const initialProfileId = (location.state as any)?.agentProfileId;
        if (initialProfileId) {
          const initialProfile = response.items.find((item) => item.id === initialProfileId);
          if (initialProfile) {
            setChatMode(initialProfile.response_mode);
            setSelectedAgentProfileId(initialProfile.id);
          }
        }
      })
      .catch((err) => console.error('Load agents error:', err));
  }, []);

  // 处理窗口尺寸变化
  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (!mobile) setIsSidebarOpen(true);
      else setIsSidebarOpen(false);
    };
    window.addEventListener('resize', handleResize);
    handleResize();
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 将会话持久化到本地
  useEffect(() => {
    localStorage.setItem('chat_sessions', JSON.stringify(sessions));
  }, [sessions]);

  const scrollToBottom = React.useCallback((behavior: ScrollBehavior = 'smooth') => {
    if (!scrollRef.current) return;
    scrollRef.current.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior,
    });
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    if (isUserScrolledUp && !isStreamingResponse) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      scrollToBottom(isStreamingResponse ? 'auto' : 'smooth');
    });

    return () => window.cancelAnimationFrame(frame);
  }, [sessions, currentSessionId, isLoading, isUserScrolledUp, isStreamingResponse, scrollToBottom]);

  // 检测用户是否手动向上滚动
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    const isScrolledUp = distanceFromBottom > 120;
    setIsUserScrolledUp(isScrolledUp);
  };

  const handleJumpToBottom = () => {
    setIsUserScrolledUp(false);
    scrollToBottom('smooth');
  };

  // 自动收起错误提示
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  // 处理首页带过来的首条消息
  useEffect(() => {
    if (initialMessage && !currentSessionId) {
      handleSend(initialMessage);
      window.history.replaceState({}, document.title);
    }
  }, [initialMessage]);

  // 在打开制品面板时自动收起侧边栏
  useEffect(() => {
    if (artifact && isSidebarOpen && !isMobile) {
      setIsSidebarOpen(false);
      setIsSidebarHiddenByArtifact(true);
    } else if (!artifact && isSidebarHiddenByArtifact && !isMobile) {
      setIsSidebarOpen(true);
      setIsSidebarHiddenByArtifact(false);
    }
  }, [artifact, isMobile]);


  const { scrollYProgress } = useScroll({ container: scrollRef });
  const borderColor = useTransform(scrollYProgress, [0, 0.2, 1], ['rgba(255,255,255,0.7)', 'rgba(255,255,255,1)', 'rgba(56,189,248,0.4)']);

  const visibleSessions = sessions.slice(0, visibleSessionsCount);
  const hasMoreSessions = sessions.length > visibleSessionsCount;

  const loadMoreSessions = () => {
    if (isLoading) return;
    setVisibleSessionsCount(prev => prev + 10);
  };

  const handleLogout = () => {
    navigate('/login');
  };

  const createNewChat = React.useCallback(() => {
    setCurrentSessionId(null);
    setChatMode('general');
    setSelectedAgentProfileId(null);
    setArtifact(null);
    setRunStatus({ phase: 'idle', label: '已就绪' });
    if (isMobile) setIsSidebarOpen(false);
  }, [isMobile]);

  const deleteSession = React.useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.id !== id));
    setCurrentSessionId(prev => (prev === id ? null : prev));
  }, []);

  const applySessionState = React.useCallback((targetId: string, state: AgentSessionState) => {
    setSessions(prev => prev.map(session => (
      session.id === targetId || session.id === state.session_id
        ? {
            ...session,
            id: state.session_id || session.id,
            summary: state.summary ?? session.summary,
            contextCompressed: state.context_compressed ?? session.contextCompressed,
            storage: state.storage ?? session.storage,
            lastUsage: state.last_usage ?? session.lastUsage,
            latencyMs: state.last_latency_ms ?? session.latencyMs,
            llmCalls: state.last_llm_calls ?? session.llmCalls,
          }
        : session
    )));
    if (targetId !== state.session_id && state.session_id) {
      setCurrentSessionId(prev => (prev === targetId ? state.session_id : prev));
    }
  }, []);

  const handleApprovalDecision = React.useCallback(async (approvalId: string, status: 'approved' | 'rejected') => {
    const optimisticStatus = status === 'approved' ? 'approved' : 'rejected';
    setSessions(prev => prev.map(session => ({
      ...session,
      messages: session.messages.map(message => ({
        ...message,
        toolCalls: message.toolCalls?.map(tool => (
          tool.approvalId === approvalId
            ? {
                ...tool,
                status: optimisticStatus,
                result: status === 'approved' ? '审批已通过，等待工具执行。' : '审批已拒绝，工具不会执行。',
              }
            : tool
        )),
      })),
    })));

    try {
      await submitApprovalDecision(approvalId, status, status === 'approved' ? 'approved from AgenticOS UI' : 'rejected from AgenticOS UI');
    } catch (err) {
      console.error('Approval error:', err);
      setError('审批提交失败，请检查后端服务。');
    }
  }, []);

  const handleOpenArtifact = React.useCallback((nextArtifact: Artifact) => {
    setArtifact(nextArtifact);
  }, []);

  const handleStopGeneration = React.useCallback(() => {
    abortControllerRef.current?.abort();
    setRunStatus({ phase: 'done', label: '正在停止请求' });
  }, []);

  const handleSend = React.useCallback(async (text: string, files?: File[]) => {
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

      const history = sessions.find(s => s.id === currentSessionId)?.messages || [];
      targetId = currentSessionId || userMessage.id;
      assistantMessageId = `${userMessage.id}-assistant`;
      const outboundMessage = attachments.length > 0
        ? `${currentText}\n\n附带文件：${attachments.map(item => item.name).join('、')}\n说明：当前后端暂不支持直接解析附件内容，请结合文件名理解需求。`
        : currentText;

      if (attachments.length > 0) {
        setError('当前后端暂不支持直接解析附件内容，本次仅向模型发送文本和文件名。');
      }

      // 先同步写入用户消息和一个模型占位，让界面立刻响应，再发起后端请求。
      flushSync(() => {
        setIsLoading(true);
        setRunStatus({
          phase: chatMode === 'ppt' ? 'generating_ppt' : 'thinking',
          label: chatMode === 'ppt' ? '正在生成 PPT 内容与版式' : '大模型正在思考',
        });
        setInputValue('');
        setSessions(prev => {
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
          return prev.map(s => s.id === currentSessionId ? { ...s, messages: [...s.messages, userMessage, assistantMessage], updatedAt: Date.now() } : s);
        });

        if (!currentSessionId) {
          setCurrentSessionId(targetId);
        }
      });

      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));

      const response = await sendMessageStream(outboundMessage, {
        sessionId: targetId,
        systemPrompt: currentSession || selectedAgentProfileId ? undefined : MODE_SYSTEM_PROMPTS[chatMode],
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
          setSessions(prev => prev.map(session => (
            session.id === targetId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map(message => (
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
                      : message
                  )),
                }
              : session
          )));
        },
        onDelta: (_, fullText) => {
          hasStreamedContent = true;
          hasAssistantActivity = true;
          setRunStatus(prev => (
            prev.phase === 'generating_ppt' || prev.phase === 'rendering_ppt'
              ? prev
              : { phase: 'streaming', label: '大模型正在输出' }
          ));
          setSessions(prev => prev.map(session => (
            session.id === targetId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map(message => (
                    message.id === assistantMessageId
                      ? chatMode === 'ppt'
                        ? {
                            ...message,
                            text: fullText,
                            pptArtifact: message.pptArtifact?.status === 'ready'
                              ? message.pptArtifact
                              : { status: 'generating' },
                          }
                        : { ...message, text: fullText }
                      : message
                  )),
                }
              : session
          )));
        },
        onReasoningDelta: (_, fullReasoning) => {
          hasAssistantActivity = true;
          setSessions(prev => prev.map(session => (
            session.id === targetId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map(message => (
                    message.id === assistantMessageId
                      ? { ...message, reasoningText: fullReasoning }
                      : message
                  )),
                }
              : session
          )));
        },
        onToolCalls: (toolCalls) => {
          hasAssistantActivity = true;
          setSessions(prev => prev.map(session => (
            session.id === targetId
              ? {
                  ...session,
                  messages: session.messages.map(message => (
                    message.id === assistantMessageId
                      ? { ...message, toolCalls }
                      : message
                  )),
                }
              : session
          )));
        },
      });

      const pptArtifact = response.pptArtifact || receivedPptArtifact;

      setSessions(prev => prev.map(session => (
        session.id === targetId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map(message => (
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
                      : message
                  )),
                  summary: response.sessionState?.summary ?? session.summary,
                  contextCompressed: response.sessionState?.context_compressed ?? session.contextCompressed,
                  storage: response.sessionState?.storage ?? session.storage,
                  lastUsage: response.sessionState?.last_usage ?? session.lastUsage,
                  latencyMs: response.sessionState?.last_latency_ms ?? session.latencyMs,
                  llmCalls: response.sessionState?.last_llm_calls ?? session.llmCalls,
            }
          : session
      )));

      const htmlMatch = /```html\n([\s\S]*?)\n```/.exec(response.text);
      const svgMatch = /```svg\n([\s\S]*?)\n```/.exec(response.text);
      if (pptArtifact) setArtifact({
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
        ]).then(title => {
          setSessions(prev => prev.map(s => s.id === targetId ? { ...s, title } : s));
        });
      }
    } catch (err) {
      if (abortController.signal.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
        if (targetId && assistantMessageId) {
          setSessions(prev => prev.map(session => (
            session.id === targetId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map(message => (
                    message.id === assistantMessageId
                      ? {
                          ...message,
                          text: message.text.trim()
                            ? `${message.text.trimEnd()}\n\n已停止请求。`
                            : '已停止请求。',
                        }
                      : message
                  )),
                }
              : session
          )));
        }
        setRunStatus({ phase: 'done', label: '已停止请求' });
        return;
      }
      console.error('Send error:', err);
      if (targetId && assistantMessageId) {
        setSessions(prev => prev.map(session => (
          session.id === targetId
            ? {
                ...session,
                messages: session.messages.filter(message => hasStreamedContent || hasAssistantActivity || message.id !== assistantMessageId),
              }
            : session
        )));
      }
      setError("发送消息失败，请检查后端服务或网络连接。");
      setRunStatus({ phase: 'error', label: '本轮回复失败' });
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
      }
      setIsLoading(false);
    }
  }, [currentSessionId, sessions, isLoading, chatMode, currentSession, applySessionState, selectedAgentProfileId, selectedAgent]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      chatInputRef.current?.addFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  return (
    <motion.div
      key="chat"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onDragOver={handleDragOver}
      onDragLeave={() => setIsDragging(false)}
      onDrop={handleDrop}
      className="flex h-screen bg-gradient-to-br from-[#e0fbfc] via-[#a5f3fc] to-[#60a5fa] text-slate-800 font-sans overflow-hidden selection:bg-zinc-200 selection:text-zinc-900 relative"
    >
      {/* 全屏拖拽遮罩 */}
      <DragOverlay isDragging={isDragging} />

      {/* 聊天页全局背景装饰 */}
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden">
        <RandomMascot size={400} className="absolute -bottom-20 -right-20 text-slate-900 opacity-[0.02]" />
      </div>

      {/* 移动端侧边栏遮罩 */}
      <AnimatePresence>
        {isMobile && isSidebarOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 bg-slate-900/20 backdrop-blur-sm z-10"
          />
        )}
      </AnimatePresence>

        <AnimatePresence mode="wait">
        {(isSidebarOpen || (isMobile && isSidebarOpen)) && (!artifact || isMobile || isSidebarOpen) && (
          <motion.div
            initial={{ x: -250, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -250, opacity: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="flex-shrink-0 z-20"
          >
            <Sidebar
              sessions={visibleSessions}
              currentSessionId={currentSessionId}
              onNewChat={createNewChat}
              onSelectSession={(id) => {
                setCurrentSessionId(id);
                if (isMobile) setIsSidebarOpen(false);
              }}
              onDeleteSession={deleteSession}
              onClose={() => setIsSidebarOpen(false)}
              isMobile={isMobile}
              onLoadMore={loadMoreSessions}
              hasMore={hasMoreSessions}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* 侧边栏折叠后的展开按钮 */}
      <AnimatePresence>
        {!isSidebarOpen && !isMobile && (
          <motion.button
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            onClick={() => {
              setIsSidebarOpen(true);
              setIsSidebarHiddenByArtifact(false);
            }}
            className="fixed top-4 left-4 z-50 w-12 h-12 bg-white/80 backdrop-blur-md border border-slate-200 rounded-2xl shadow-sm flex items-center justify-center text-zinc-800 hover:bg-white hover:shadow-md transition-all group"
          >
            <MascotCool size={24} className="group-hover:scale-110 transition-transform" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* 主聊天区域与制品面板 */}
      <div className="flex-1 flex overflow-hidden relative">
        <main className={cn(
          "flex flex-col h-full transition-all duration-700 ease-[0.16,1,0.3,1] min-w-0 relative",
          artifact ? "w-[40%] border-r border-slate-200/60" : "w-full",
          isWideConversation && "px-4 lg:px-8 xl:px-10"
        )}>
          {/* 时间线导航 */}
          <AnimatePresence>
            {!isMobile && currentSession?.messages && (
              <ChatTimeline messages={currentSession.messages} />
            )}
          </AnimatePresence>

          {/* 消息区域 */}
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className={cn(
              "flex-1 overflow-y-auto custom-scrollbar relative pr-16",
              isWideConversation ? "px-6 py-8 md:px-10 lg:px-14 xl:px-16" : "p-4 md:p-8"
            )}
          >
            {/* 搜索浮层 */}
            <ChatSearch
              showSearch={showSearch}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              searchCurrentIndex={searchCurrentIndex}
              searchMatchesCount={searchMatches.length}
              onPrev={prevMatch}
              onNext={nextMatch}
              onClose={() => {
                setShowSearch(false);
                setSearchQuery('');
              }}
            />

            {/* 右下角浮动工具栏 */}
            <div className="fixed right-6 bottom-10 flex flex-col gap-3 z-40">
              <button
                onClick={() => setShowSearch(!showSearch)}
                className={cn(
                  "w-12 h-12 rounded-2xl flex items-center justify-center transition-all shadow-lg backdrop-blur-md border hover:scale-105 active:scale-95",
                  showSearch
                    ? "bg-zinc-900 text-white border-zinc-800"
                    : "bg-white/80 text-slate-600 border-white/60 hover:bg-white"
                )}
              >
                <div className={cn("transition-transform duration-500", showSearch && "rotate-90")}>
                  {showSearch ? (
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  ) : (
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
                    </svg>
                  )}
                </div>
              </button>
            </div>

            {/* 错误提示 */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  className="absolute top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl shadow-lg"
                >
                  <AlertCircleIcon size={18} />
                  <span className="text-sm font-medium">{error}</span>
                  <button onClick={() => setError(null)} className="ml-2 text-red-500 hover:text-red-700">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            <MessagesList
              currentSession={currentSession}
              isLoading={isLoading}
              wideLayout={isWideConversation}
              searchQuery={searchQuery}
              activeMatchId={activeMatchId}
              onSend={handleSend}
              onSuggestionClick={(text) => setInputValue(text)}
              onOpenArtifact={handleOpenArtifact}
              messagesEndRef={messagesEndRef}
            />
          </div>

          {/* 输入区域 */}
          <div className="p-4 md:p-6 bg-transparent flex-shrink-0 relative">
            <AnimatePresence>
              {isUserScrolledUp && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute -top-4 left-0 right-0 flex justify-center z-30"
                >
                  <button
                    onClick={handleJumpToBottom}
                    className="flex items-center gap-2 px-6 py-1.5 bg-zinc-900/90 backdrop-blur-2xl text-white rounded-full text-[10px] font-black uppercase tracking-[0.2em] shadow-2xl border border-white/10 hover:bg-zinc-800 transition-all active:scale-95 group"
                  >
                    <span>回到底部</span>
                    <ChevronDownIcon size={12} className="group-hover:translate-y-0.5 transition-transform" />
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            <div className={cn("mx-auto", isWideConversation ? "max-w-[92rem] px-8" : "max-w-4xl")}>
              <PendingApprovalPanel
                approvals={pendingApprovals}
                onDecision={handleApprovalDecision}
              />
              <ChatInput
                ref={chatInputRef}
                value={inputValue}
                onChange={setInputValue}
                onSend={(text, files) => handleSend(text, files)}
                onStop={handleStopGeneration}
                isLoading={isLoading}
                chatMode={chatMode}
                setChatMode={setChatMode}
                agentProfiles={agentProfiles}
                selectedAgentProfileId={selectedAgentProfileId}
                onAgentProfileChange={(profile) => {
                  setSelectedAgentProfileId(profile?.id ?? null);
                  if (profile) {
                    setChatMode(profile.response_mode);
                  }
                }}
                isModeLocked={!!currentSession && currentSession.messages.length > 0}
              />
              <div className="mt-3 flex min-h-5 items-center justify-center gap-2 text-xs font-medium text-slate-400">
                {isLoading && (
                  <span className="flex items-center gap-1.5 text-slate-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-zinc-500/70 animate-pulse" />
                    {runStatus.label}
                  </span>
                )}
                {!isLoading && <span>AI 可能会犯错，请核实重要信息。</span>}
              </div>
            </div>
          </div>
        </main>

        {/* 制品预览面板 */}
        <AnimatePresence>
          {artifact?.language === 'ppt' ? (
            <PptArtifactPanel
              artifact={artifact}
              onClose={() => setArtifact(null)}
              borderColor={borderColor}
            />
          ) : (
            <ArtifactPanel
              artifact={artifact}
              onClose={() => setArtifact(null)}
              borderColor={borderColor}
            />
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
