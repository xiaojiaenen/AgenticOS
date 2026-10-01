/**
 * 智能体配置：编辑弹窗右栏「技能绑定」面板。
 * 从 AgentManagement.tsx 拆出，纯结构拆分，逻辑不变。
 */
import type { UseFormReturn } from 'react-hook-form';
import { cn } from '@/lib/utils';
import type { AgentProfile } from '@/services/agentProfileService';
import type { AgentFormValues } from './agentHelpers';

export function AgentSkillsPanel({
  form,
  availableSkills,
}: {
  form: UseFormReturn<AgentFormValues>;
  availableSkills: AgentProfile['skills'];
}) {
  const skillIds = form.watch('skill_ids');
  const tools = form.watch('tools');

  const toggleSkill = (skillId: number) => {
    const nextSkillIds = skillIds.includes(skillId)
      ? skillIds.filter((item) => item !== skillId)
      : [...skillIds, skillId];
    const hasAnySkills = nextSkillIds.length > 0;
    form.setValue('skill_ids', nextSkillIds, { shouldDirty: true });
    const current = form.getValues('tools');
    form.setValue(
      'tools',
      current.map((tool) =>
        tool.tool_name === 'skill' ? { ...tool, enabled: hasAnySkills ? true : tool.enabled } : tool,
      ),
      { shouldDirty: true },
    );
  };

  const selectedSkills = availableSkills.filter((skill) => skillIds.includes(skill.id));
  const skillToolEnabled = tools.find((tool) => tool.tool_name === 'skill')?.enabled ?? false;

  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-1)] p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
            可用 Skill
          </p>
          <h4 className="mt-1 text-base font-semibold text-[var(--foreground)]">按智能体选择 Skill</h4>
        </div>
        <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-1)] px-3 py-1 text-xs font-semibold text-[var(--muted-foreground)]">
          已选 {selectedSkills.length}/{availableSkills.length}
        </span>
      </div>

      {!skillToolEnabled && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-sm font-medium text-amber-700">
          选中 Skill 后，系统会自动打开 `skill` 工具；脚本执行审批由 Wuwei 在运行时接管。
        </div>
      )}

      <div className="space-y-3">
        {availableSkills.length > 0 ? (
          availableSkills.map((skill) => {
            const selected = skillIds.includes(skill.id);
            return (
              <button
                key={skill.id}
                type="button"
                onClick={() => toggleSkill(skill.id)}
                className={cn(
                  'w-full rounded-lg border p-3.5 text-left transition-all',
                  selected
                    ? 'border-indigo-300 bg-indigo-50/70 shadow-sm'
                    : 'border-[var(--border-subtle)] bg-[var(--surface-1)] hover:border-zinc-300',
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-[var(--foreground)]">{skill.name}</p>
                    <p className="mt-1 truncate text-[11px] font-semibold tracking-wide text-[var(--muted-foreground)]">
                      {skill.slug}
                    </p>
                  </div>
                  <span
                    className={cn(
                      'rounded-full px-2 py-1 text-[10px] font-semibold',
                      selected ? 'bg-indigo-100 text-indigo-700' : 'bg-[var(--surface-2)] text-[var(--muted-foreground)]',
                    )}
                  >
                    {selected ? '已选择' : '可选择'}
                  </span>
                </div>
                <p className="mt-3 text-xs font-medium leading-5 text-[var(--muted-foreground)]">
                  {skill.description || '暂无描述'}
                </p>
                {skill.has_python_scripts && (
                  <div className="mt-3">
                    <span className="rounded-full border border-amber-100 bg-amber-50 px-2.5 py-1 text-[10px] font-semibold text-amber-700">
                      含 Python 脚本
                    </span>
                  </div>
                )}
                {skill.has_references && (
                  <div className="mt-2">
                    <span className="rounded-full border border-indigo-100 bg-indigo-50 px-2.5 py-1 text-[10px] font-semibold text-indigo-700">
                      {skill.reference_paths.length} refs
                    </span>
                  </div>
                )}
              </button>
            );
          })
        ) : (
          <div className="rounded-lg border border-dashed border-[var(--border-subtle)] bg-[var(--surface-1)] px-4 py-4 text-sm font-medium text-[var(--muted-foreground)]">
            还没有可绑定的 Skill，请先去 Skill 管理页创建或上传。
          </div>
        )}
      </div>
    </div>
  );
}
