/**
 * 后台功能导航清单（侧栏「企业后台」面板用）。
 *
 * 与 AdminDashboard 的 ADMIN_GROUPS 一一对应（tab 值相同），用于左侧栏
 * 可展开的后台功能导航。只保留导航所需字段，业务描述仍在 AdminDashboard。
 */
import {
  Activity, AppWindow, BellRing, BookOpen, Bot, Brain, Building2, Cpu,
  FlaskConical, Gauge, Globe, KeyRound, MessageSquare, MessageSquarePlus,
  Network, Plug, Puzzle, Settings, ShieldAlert, ShieldBan, Sparkles,
  Users,
  type LucideIcon,
} from 'lucide-react';

export interface AdminNavItem {
  tab: string;
  label: string;
  icon: LucideIcon;
  cap: string;
}

export interface AdminNavGroup {
  key: string;
  label: string;
  icon: LucideIcon;
  items: AdminNavItem[];
}

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    key: 'content', label: '对话与内容', icon: MessageSquare,
    items: [
      { tab: 'approvals', label: '审批中心', icon: ShieldAlert, cap: 'approval:review' },
      { tab: 'announcements', label: '公告设计', icon: BellRing, cap: 'announcement:manage' },
      { tab: 'history', label: '聊天记录元数据', icon: MessageSquare, cap: 'user:manage' },
      { tab: 'user_analytics', label: '用户行为分析', icon: Activity, cap: 'audit:view' },
      { tab: 'memory', label: '记忆管理', icon: Brain, cap: 'user:manage' },
      { tab: 'traces', label: '运行追踪', icon: Activity, cap: 'user:manage' },
      { tab: 'feedback', label: '反馈中心', icon: MessageSquarePlus, cap: 'user:manage' },
    ],
  },
  {
    key: 'knowledge', label: '智能体与能力', icon: Cpu,
    items: [
      { tab: 'agents', label: '智能体配置', icon: Bot, cap: 'agent:manage' },
      { tab: 'skills', label: 'Skill 管理', icon: Puzzle, cap: 'agent:manage' },
      { tab: 'tool_policy', label: '能力限制', icon: ShieldBan, cap: 'agent:manage' },
      { tab: 'knowledge', label: '知识库与 Wiki', icon: BookOpen, cap: 'knowledge:manage' },
      { tab: 'website_deploys', label: '网站部署审批', icon: Globe, cap: 'gallery:manage' },
      { tab: 'app_platform', label: '网站应用化平台', icon: AppWindow, cap: 'gallery:manage' },
      { tab: 'llm_providers', label: 'AI 提供商', icon: Sparkles, cap: 'provider:manage' },
      { tab: 'evals', label: '回归评测', icon: FlaskConical, cap: 'user:manage' },
    ],
  },
  {
    key: 'gateway', label: '组织与系统', icon: Building2,
    items: [
      { tab: 'users', label: '用户与角色管理', icon: Users, cap: 'user:manage' },
      { tab: 'permissions', label: 'Casbin 权限矩阵', icon: Building2, cap: 'user:manage' },
      { tab: 'integrations', label: '第三方集成与 MCP', icon: Plug, cap: 'user:manage' },
      { tab: 'api_keys', label: '平台级 API Key', icon: KeyRound, cap: 'apikey:manage' },
      { tab: 'gateway', label: '对外接口网关', icon: Network, cap: 'user:manage' },
      { tab: 'task_queue', label: '任务队列', icon: Cpu, cap: 'user:manage' },
      { tab: 'quota', label: '配额与限流', icon: Gauge, cap: 'audit:view' },
      { tab: 'settings', label: '系统设置', icon: Settings, cap: 'system:settings' },
    ],
  },
];
