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
    max_steps: z
      .union([
        z
          .number()
          .int('最大步数必须是整数')
          .min(1, '最大步数至少为 1')
          .max(2147483647, '最大步数不能超过 2147483647'),
        z.null(),
      ])
      .refine((v) => v === null || Number.isFinite(v), { message: '最大步数必须是有效数字' }),
    enabled: z.boolean(),
    listed: z.boolean(),
    audience_mode: z.enum(['all', 'selected', 'none']),
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

/**
 * 合并「已配置的工具」与「当前 catalog 全集」。
 *
 * 为什么必须合并：catalog 随版本增长（新增工具），而
 * `agent_profile_tools` 里只存「当初配置过的那批」。直接 `profile.tools.map`
 * 会让**新增工具在这个智能体上完全不可见** —— 用户看到「后台工具列表少了
 * 几个」，实际只是它们没进过这份快照。
 *
 * 规则：
 * - catalog 有的 → 用 profile 的配置；没配置过的按默认（关闭），
 *   避免悄悄给老智能体開新能力；
 * - profile 有、catalog 没有的（已下线工具）→ 丢弃。
 */
export function mergeToolsWithCatalog(
  configured: AgentProfileTool[],
  catalog: ToolCatalogItem[],
): AgentProfileTool[] {
  const byName = new Map(configured.map((t) => [t.tool_name, t]));
  return catalog.map((item) => {
    const existing = byName.get(item.name);
    return existing
      ? { ...existing, approval_sub_tools: [...(existing.approval_sub_tools ?? [])] }
      : {
          tool_name: item.name,
          enabled: false,
          requires_approval: false,
          approval_sub_tools: [],
        };
  });
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
        ? mergeToolsWithCatalog(profile.tools, catalog)
        : defaultTools(catalog),
    skill_ids: profile.skills.map((skill) => skill.id),
    external_systems: (profile.external_systems || []).map((es) => ({
      system_id: es.system_id,
      enabled: es.enabled,
    })),
  };
}
