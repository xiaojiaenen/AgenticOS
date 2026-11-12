/**
 * Chat UI 状态管理 — Zustand Store
 *
 * 纯 UI 状态 + 会话数据统一存放。此前会话数据（sessions / runStatus /
 * pendingDecisions 等）分散在 useChatSessions / useChatStream 的 useState 里，
 * 经一个 41 字段的 ChatContext 下发 —— 流式期间每帧重建 context。
 * 统一进 store 后组件按 selector 精准订阅。
 *
 * 关键契约：``setSessions`` 等 setter 保持 React ``Dispatch<SetStateAction<T>>``
 * 形状（接受值或 ``prev => next`` 函数），useChatSessions / useChatStream 的
 * 内部逻辑与签名因此无需改动。
 */
import { create } from 'zustand';
import type { Dispatch, SetStateAction } from 'react';
import type { Artifact, Session } from '../types';
import type { AgentProfile } from '../services/agentProfileService';
import type { SessionPanelId } from '../components/panel/types';

export type ChatMode = 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'office';

export type ChatRunStatus = {
  phase: 'idle' | 'thinking' | 'streaming' | 'generating_ppt' | 'rendering_ppt' | 'rendering_website' | 'done' | 'error';
  label: string;
  /** 运行预算：当前步 / 上限步（后端透出，用于"第 N/M 步"提示） */
  step?: number;
  maxSteps?: number;
};

/** React dispatch 形状的 setter：接受新值或 ``prev => next`` 函数。 */
type StateDispatch<T> = Dispatch<SetStateAction<T>>;

function applyAction<T>(current: T, action: SetStateAction<T>): T {
  return typeof action === 'function' ? (action as (prev: T) => T)(current) : action;
}

interface ChatUIState {
  // ── 输入 ──
  inputValue: string;
  setInputValue: (v: string) => void;

  // ── 会话数据（原 useChatSessions 的 useState）──
  sessions: Session[];
  setSessions: StateDispatch<Session[]>;
  currentSessionId: string | null;
  setCurrentSessionId: StateDispatch<string | null>;
  /** 会话列表分页：一次多显示几个 */
  visibleSessionsCount: number;
  setVisibleSessionsCount: StateDispatch<number>;

  // ── 流式状态（原 useChatStream 的 useState）──
  runStatus: ChatRunStatus;
  setRunStatus: StateDispatch<ChatRunStatus>;
  pendingDecisions: import('../components/chat/DecisionPanel').UserDecision[];
  setPendingDecisions: StateDispatch<import('../components/chat/DecisionPanel').UserDecision[]>;
  /** 流式错误（与 UI 状态无冲突，沿旧名） */
  streamError: string | null;
  setStreamError: StateDispatch<string | null>;

  // ── 模式 ──
  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;
  /** 会话级审批模式：ask 逐次确认 / auto 只读自动放行 / full 全放行 */
  approvalMode: 'ask' | 'auto' | 'full';
  setApprovalMode: (mode: 'ask' | 'auto' | 'full') => void;
  /** 计划模式：只读调研→出计划→批准后执行 */
  planMode: boolean;
  setPlanMode: (on: boolean) => void;

  // ── 智能体 ──
  agentProfiles: AgentProfile[];
  setAgentProfiles: (profiles: AgentProfile[]) => void;
  selectedAgentProfileId: number | null;
  setSelectedAgentProfileId: (id: number | null) => void;

  // ── 侧边栏 ──
  isSidebarOpen: boolean;
  setIsSidebarOpen: (open: boolean) => void;
  isSidebarHiddenByArtifact: boolean;
  setIsSidebarHiddenByArtifact: (hidden: boolean) => void;

  // ── 响应式 ──
  isMobile: boolean;
  setIsMobile: (mobile: boolean) => void;

  /**
   * 正在流式运行的会话 id 集合（可多个：切走会话不掐断后台流）。
   *
   * 供侧栏「运行中」呼吸点、浏览器标题等**环境感知**界面消费 ——
   * 数据源在 useChatStream（它管 AbortController 生命周期），这里只做
   * 共享投影。必须整体替换（new Set），zustand 浅比较不认 Set 的变更。
   */
  activeStreamIds: Set<string>;
  setActiveStreamIds: (ids: Set<string>) => void;

  // ── 制品面板 ──
  artifact: Artifact | null;
  setArtifact: (artifact: Artifact | null) => void;
  /**
   * 会话级面板（运行日志 / 会话文件）：不属于某个具体产物，没有产物时
   * 也要能打开。与 artifact 互斥 —— 互斥在 Chat.tsx 的传参层保证
   * （sessionPanel 打开时给产物区传 null）。
   */
  sessionPanel: SessionPanelId | null;
  setSessionPanel: (panel: SessionPanelId | null) => void;

  // ── 组合 action ──
  createNewChat: () => void;
}

export const useChatStore = create<ChatUIState>((set) => ({
  inputValue: '',
  setInputValue: (v) => set({ inputValue: v }),

  // 会话数据：初始值沿用 localStorage 缓存（与原 useState 惰性初始化等价，
  // store 在模块导入期创建，同步读 localStorage 无副作用）
  sessions: [],
  setSessions: (action) => set((s) => ({ sessions: applyAction(s.sessions, action) })),
  currentSessionId: null,
  setCurrentSessionId: (action) =>
    set((s) => ({ currentSessionId: applyAction(s.currentSessionId, action) })),
  visibleSessionsCount: 10,
  setVisibleSessionsCount: (action) =>
    set((s) => ({ visibleSessionsCount: applyAction(s.visibleSessionsCount, action) })),

  runStatus: { phase: 'idle', label: '已就绪' },
  setRunStatus: (action) => set((s) => ({ runStatus: applyAction(s.runStatus, action) })),
  pendingDecisions: [],
  setPendingDecisions: (action) =>
    set((s) => ({ pendingDecisions: applyAction(s.pendingDecisions, action) })),
  streamError: null,
  setStreamError: (action) => set((s) => ({ streamError: applyAction(s.streamError, action) })),

  chatMode: 'general',
  setChatMode: (mode) => set({ chatMode: mode }),
  approvalMode: 'ask',
  setApprovalMode: (mode) => set({ approvalMode: mode }),
  planMode: false,
  setPlanMode: (on) => set({ planMode: on }),

  agentProfiles: [],
  setAgentProfiles: (profiles) => set({ agentProfiles: profiles }),
  selectedAgentProfileId: null,
  setSelectedAgentProfileId: (id) => set({ selectedAgentProfileId: id }),

  isSidebarOpen: false,
  setIsSidebarOpen: (open) => set({ isSidebarOpen: open }),
  isSidebarHiddenByArtifact: false,
  setIsSidebarHiddenByArtifact: (hidden) => set({ isSidebarHiddenByArtifact: hidden }),

  isMobile: false,
  setIsMobile: (mobile) => set({ isMobile: mobile }),

  activeStreamIds: new Set<string>(),
  setActiveStreamIds: (ids) => set({ activeStreamIds: ids }),

  artifact: null,
  setArtifact: (artifact) => set({ artifact }),

  sessionPanel: null,
  setSessionPanel: (sessionPanel) => set({ sessionPanel }),

  createNewChat: () =>
    set({
      chatMode: 'general',
      selectedAgentProfileId: null,
      artifact: null,
      inputValue: '',
    }),
}));
