/**
 * Chat UI 状态管理 — Zustand Store
 *
 * 只存放纯 UI 状态，会话数据仍由 useChatSessions 管理（localStorage 持久化）。
 * 组件通过 useChatStore(selector) 精准订阅，避免不必要的重渲染。
 */
import { create } from 'zustand';
import type { Artifact } from '../types';
import type { AgentProfile } from '../services/agentProfileService';

export type ChatMode = 'general' | 'ppt' | 'website' | 'video' | 'bigdata';

interface ChatUIState {
  // ── 输入 ──
  inputValue: string;
  setInputValue: (v: string) => void;

  // ── 模式 ──
  chatMode: ChatMode;
  setChatMode: (mode: ChatMode) => void;

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

  // ── 制品面板 ──
  artifact: Artifact | null;
  setArtifact: (artifact: Artifact | null) => void;

  // ── 组合 action ──
  createNewChat: () => void;
}

export const useChatStore = create<ChatUIState>((set) => ({
  inputValue: '',
  setInputValue: (v) => set({ inputValue: v }),

  chatMode: 'general',
  setChatMode: (mode) => set({ chatMode: mode }),

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

  artifact: null,
  setArtifact: (artifact) => set({ artifact }),

  createNewChat: () =>
    set({
      chatMode: 'general',
      selectedAgentProfileId: null,
      artifact: null,
      inputValue: '',
    }),
}));
