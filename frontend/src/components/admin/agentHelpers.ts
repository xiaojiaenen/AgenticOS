/**
 * 智能体配置：共享 zod schema 与小型工具函数。
 * 从 AgentManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import { z } from 'zod';
import type { AgentProfile, AgentProfileTool } from '@/services/agentProfileService';
import type { AgentMode, ToolCatalogItem } from '@/services/toolConfigService';
import { MODE_SYSTEM_PROMPTS } from '@/constants/modePrompts';

// ---------------------------------------------------------------------------
// zod schema（对齐后端 AgentProfilePayload）
// ---------------------------------------------------------------------------

export const agentFormSchema = z
  .object({
    name: z.string().min(1, '请填写智能体名称'),
    slug: z
      .string()
      .regex(/^[a-z0-9-]*$/, 'slug 仅允许小写字母、数字和连字符'),
    description: z.string(),
    system_prompt: z.string().min(1, '系统提示词不能为空'),
    response_mode: z.enum(['general', 'ppt', 'website', 'email', 'bigdata', 'office']),
    max_steps: z.union([z.number().int().min(1).max(2147483647), z.null()]),
    enabled: z.boolean(),
    listed: z.boolean(),
    audience_mode: z.enum(['all', 'selected']),
    audience_user_ids: z.array(z.number()),
    tools: z.array(
      z.object({
        tool_name: z.string(),
        enabled: z.boolean(),
        requires_approval: z.boolean(),
        approval_sub_tools: z.array(z.string()),
      }),
    ),
    skill_ids: z.array(z.number()),
    external_systems: z.array(z.object({ system_id: z.number(), enabled: z.boolean() })),
  })
  .refine((data) => data.audience_mode !== 'selected' || data.audience_user_ids.length > 0, {
    message: '请选择至少一个用户，或切换为全体用户',
    path: ['audience_user_ids'],
  });

export type AgentFormValues = z.infer<typeof agentFormSchema>;

export const AGENT_MODES: AgentMode[] = ['general', 'ppt', 'website', 'email', 'bigdata', 'office'];

export function modeLabel(mode: AgentMode): string {
  if (mode === 'ppt') return 'PPT';
  if (mode === 'website') return '网站';
  if (mode === 'email') return '邮箱';
  if (mode === 'bigdata') return '大数据';
  if (mode === 'office') return '办公';
  return '通用';
}

export function modeDefaultPrompt(mode: AgentMode): string {
  return MODE_SYSTEM_PROMPTS[mode] || MODE_SYSTEM_PROMPTS.general;
}

export function defaultTools(catalog: ToolCatalogItem[]): AgentProfileTool[] {
  return catalog.map((item) => ({
    tool_name: item.name,
    enabled: item.name === 'calc' || item.name === 'time',
    requires_approval: false,
    approval_sub_tools: [],
  }));
}

export function draftFromProfile(profile: AgentProfile, catalog: ToolCatalogItem[]): AgentFormValues {
  return {
    name: profile.name,
    slug: profile.slug,
    description: profile.description,
    system_prompt: profile.system_prompt,
    response_mode: profile.response_mode,
    max_steps: profile.max_steps ?? null,
    enabled: profile.enabled,
    listed: profile.listed,
    audience_mode: profile.audience_mode,
    audience_user_ids: profile.audience_users.map((user) => user.id),
    tools:
      profile.tools.length > 0
        ? profile.tools.map((tool) => ({ ...tool, approval_sub_tools: [...tool.approval_sub_tools] }))
        : defaultTools(catalog),
    skill_ids: profile.skills.map((skill) => skill.id),
    external_systems: (profile.external_systems || []).map((es) => ({
      system_id: es.system_id,
      enabled: es.enabled,
    })),
  };
}
