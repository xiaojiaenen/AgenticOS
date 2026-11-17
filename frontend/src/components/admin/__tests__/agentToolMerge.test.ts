/**
 * 智能体编辑弹窗的工具列表组装。
 *
 * 真实故障：catalog 新增工具（本次从 ppt-master 吸收的
 * list_visual_styles / validate_formula / measure_text_fit /
 * find_chart_template）后，**老智能体的编辑弹窗里看不到它们** ——
 * `draftFromProfile` 在 profile.tools 非空时直接用它，而那份记录是
 * 建号时写的快照，不含后来新增的工具。用户看到的是「后台工具少了几个」。
 */
import { describe, expect, it } from 'vitest';
import { defaultTools, mergeToolsWithCatalog } from '../agentHelpers';
import type { ToolCatalogItem } from '@/services/toolConfigService';
import type { AgentProfileTool } from '@/services/agentProfileService';

const catalog = (names: string[]): ToolCatalogItem[] =>
  names.map((name) => ({
    name,
    label: `label-${name}`,
    description: '',
    enabled: true,
    requires_approval: false,
    approvals: [],
    sub_tools: [],
    source: 'builtin',
  })) as unknown as ToolCatalogItem[];

const tool = (name: string, enabled: boolean): AgentProfileTool => ({
  tool_name: name,
  enabled,
  requires_approval: false,
  approval_sub_tools: [],
});

describe('mergeToolsWithCatalog', () => {
  it('catalog 新增的工具出现在结果里（默认关闭）', () => {
    const configured = [tool('calc', true), tool('time', true)];
    const full = catalog(['calc', 'time', 'list_visual_styles', 'validate_formula']);

    const merged = mergeToolsWithCatalog(configured, full);

    expect(merged.map((t) => t.tool_name)).toEqual([
      'calc', 'time', 'list_visual_styles', 'validate_formula',
    ]);
    // 已配置的保持原状态
    expect(merged.find((t) => t.tool_name === 'calc')?.enabled).toBe(true);
    // 新增的默认关闭（不能悄悄给老智能体開新能力）
    expect(merged.find((t) => t.tool_name === 'list_visual_styles')?.enabled).toBe(false);
  });

  it('catalog 已下线的工具不再展示', () => {
    const configured = [tool('calc', true), tool('legacy_removed', true)];
    const merged = mergeToolsWithCatalog(configured, catalog(['calc']));
    expect(merged.map((t) => t.tool_name)).toEqual(['calc']);
  });

  it('保留审批配置与子工具选择', () => {
    const configured: AgentProfileTool[] = [
      { tool_name: 'file', enabled: true, requires_approval: true, approval_sub_tools: ['read', 'write'] },
    ];
    const merged = mergeToolsWithCatalog(configured, catalog(['file']));
    expect(merged[0].requires_approval).toBe(true);
    expect(merged[0].approval_sub_tools).toEqual(['read', 'write']);
  });

  it('子工具数组是副本（不共享引用，避免表单编辑污染原对象）', () => {
    const configured: AgentProfileTool[] = [
      { tool_name: 'file', enabled: true, requires_approval: false, approval_sub_tools: ['read'] },
    ];
    const merged = mergeToolsWithCatalog(configured, catalog(['file']));
    merged[0].approval_sub_tools.push('write');
    expect(configured[0].approval_sub_tools).toEqual(['read']);
  });

  it('defaultTools 覆盖全部 catalog 项', () => {
    const full = catalog(['calc', 'time', 'x', 'y']);
    const defaults = defaultTools(full);
    expect(defaults).toHaveLength(4);
    expect(defaults.filter((t) => t.enabled).map((t) => t.tool_name)).toEqual(['calc', 'time']);
  });
});
