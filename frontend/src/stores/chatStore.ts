/**
 * Chat UI 状态管理 — Zustand Store
 *
 * 只存放纯 UI 状态，会话数据仍由 useChatSessions 管理（localStorage 持久化）。
 * 组件通过 useChatStore(selector) 精准订阅，避免不必要的重渲染。
 */
import { create } from 'zustand';
import type { Artifact } from '../types';
import type { AgentProfile } from '../services/agentProfileService';
import type { SessionPanelId } from '../components/panel/types';

export type ChatMode = 'general' | 'ppt' | 'website' | 'email' | 'bigdata' | 'office';

interface ChatUIState {
  // ── 输入 ──
  inputValue: string;
  setInputValue: (v: string) => void;

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
