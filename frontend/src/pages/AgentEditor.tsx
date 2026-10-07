/**
 * 自建智能体：创建 / 编辑。
 *
 * 用户在这里定义一个专属助手：身份（名称/描述/头像）、能力边界（系统提示词）、
 * 可用模式（general/ppt/website/email/bigdata）、以及**可勾选的工具**——
 * 工具按模式分组，每个工具可单独开关，高风险工具可标记"需人工审批"。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ArrowLeft, BookOpen, Bot, Check, Database, Globe, Library, Loader2, Mail,
  Plug, Presentation, Save, ShieldAlert, Sparkles, Trash2, Wand2, Wrench,
} from 'lucide-react';
import { Button } from '../components/shadcn/button';
import { Input } from '../components/shadcn/input';
import { Badge } from '../components/ui/Badge';
import { cn } from '../lib/utils';
import {
  createAgentProfile,
  deleteAgentProfile,
  getAgentStore,
  getMyAgents,
  updateAgentProfile,
  type AgentProfile,
  type AgentProfileSkill,
  type AgentProfileTool,
} from '../services/agentProfileService';
import type { ToolCatalogItem } from '../services/toolConfigService';

/**
 * 工具分组（后端 catalog 无分类字段，这里按工具语义归类，
 * 让 36 个工具在勾选界面里可读，而不是一长条平铺列表）。
 */
const TOOL_CATEGORIES: Record<string, string[]> = {
  基础能力: ['calc', 'time', 'decision'],
  文件与代码: ['file', 'file_to_md', 'python', 'git'],
  知识与记忆: ['knowledge', 'memory', 'skill', 'email'],
  数据与图表: ['analyze_data', 'render_chart', 'analyze_template'],
  演示文稿: ['save_slide', 'save_slides_batch', 'read_slide', 'batch_edit_slides',
    'submit_slide_plan', 'submit_spec_lock', 'calc_chart_positions', 'check_svg_quality',
    'convert_pptx_to_svg', 'import_pptx_template', 'resume_ppt', 'check_ppt_progress',
    'read_notes'],
  图片与图标: ['search_images', 'get_image_info', 'search_icons', 'list_icons'],
  网站与部署: ['copy_template', 'check_website_project', 'build_website', 'deploy_website', 'npm'],
};

const TOOL_CATEGORY_OF = (() => {
  const map = new Map<string, string>();
  for (const [category, tools] of Object.entries(TOOL_CATEGORIES)) {
    for (const tool of tools) map.set(tool, category);
  }
  return map;
})();

function categoryOf(name: string): string {
  return TOOL_CATEGORY_OF.get(name) ?? '其他';
}

const MODE_OPTIONS: { value: AgentProfile['response_mode']; label: string; hint: string }[] = [
  { value: 'general', label: '通用问答', hint: '日常问答、资料整理、轻量工具调用' },
  { value: 'ppt', label: '演示文稿', hint: '生成可编辑的 SVG 幻灯片并导出 PPTX' },
  { value: 'website', label: '网站生成', hint: '构建前端项目并预览/部署' },
  { value: 'email', label: '邮件助手', hint: '收发、搜索、统计邮件' },
  { value: 'bigdata', label: '大数据运维', hint: '巡检、排查、容量与应急止血' },
  { value: 'office', label: '办公文档', hint: '电子表格（公式/多工作表）+ 文档（标题层级/正文）' },
];

type EditorSection = 'basic' | 'prompt' | 'tool' | 'skill' | 'knowledge' | 'mcp';

/** 左侧分区导航：每项带当前值摘要，避免打开页面要通读全文 */
const SECTION_META: {
  key: EditorSection;
  label: string;
  hint: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
}[] = [
  { key: 'basic', label: '基本信息', hint: '名称、模式与可见范围', icon: Bot },
  { key: 'prompt', label: '提示词', hint: '定义它的行为方式', icon: Wand2 },
  { key: 'tool', label: '工具', hint: '能做什么', icon: Wrench },
  { key: 'skill', label: '技能', hint: '按什么流程做事', icon: BookOpen },
  { key: 'knowledge', label: '知识库', hint: '能查哪些资料', icon: Library },
  { key: 'mcp', label: 'MCP', hint: '能连哪些外部系统', icon: Plug },
];

/** 图标选项：lucide 图标本身即选择器（此前用文字缩写，不可辨识） */
const AVATAR_CHOICES = [
  { key: 'sparkles', label: '星芒', Icon: Sparkles },
  { key: 'presentation', label: '演示', Icon: Presentation },
  { key: 'globe', label: '网站', Icon: Globe },
  { key: 'mail', label: '邮件', Icon: Mail },
  { key: 'bot', label: '机器人', Icon: Bot },
  { key: 'database', label: '数据', Icon: Database },
] as const;

export const AgentEditor: React.FC = () => {
  const navigate = useNavigate();
  const { profileId } = useParams();
  const [searchParams] = useSearchParams();
  const editingId = profileId ? Number(profileId) : null;
  const isEditing = editingId !== null && Number.isFinite(editingId);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [responseMode, setResponseMode] = useState<AgentProfile['response_mode']>(
    (searchParams.get('mode') as AgentProfile['response_mode']) || 'general',
  );
  const [avatar, setAvatar] = useState('sparkles');
  const [visibility, setVisibility] = useState<'private' | 'public'>('private');
  const [maxSteps, setMaxSteps] = useState<string>('');
  const [tab, setTab] = useState<EditorSection>('basic');

  /** 左侧导航的当前值摘要：不展开也能知道配了什么 */
  const sectionSummary = (key: EditorSection): string => {
    switch (key) {
      case 'basic':
        return name.trim() || '未命名';
      case 'prompt':
        return systemPrompt.trim() ? `${systemPrompt.trim().length} 字` : '未填写';
      case 'tool':
        return enabledCount > 0 ? `${enabledCount} 个已启用` : '未选择';
      case 'skill':
        return selectedSkills.length > 0 ? `${selectedSkills.length} 个技能` : '未绑定';
      case 'knowledge':
        return enabledTools.knowledge ? '检索已开启' : '未开启检索';
      case 'mcp':
        return '管理入口';
    }
  };

  const sectionCount = (key: EditorSection): string => {
    switch (key) {
      case 'tool':
        return `${enabledCount}/${catalog.length}`;
      case 'skill':
        return selectedSkills.length > 0 ? String(selectedSkills.length) : '';
      default:
        return '';
    }
  };
  const [skills, setSkills] = useState<AgentProfileSkill[]>([]);
  const [selectedSkills, setSelectedSkills] = useState<number[]>([]);
  const [enabledTools, setEnabledTools] = useState<Record<string, boolean>>({});
  const [approvalTools, setApprovalTools] = useState<Record<string, boolean>>({});
  const [catalog, setCatalog] = useState<ToolCatalogItem[]>([]);
  const [loading, setLoading] = useState(isEditing);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // 加载工具目录（编辑时还要回填已有配置）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const store = await getAgentStore();
        if (cancelled) return;
        setCatalog(store.catalog ?? []);
        setSkills(store.available_skills ?? []);
        if (!isEditing) return;
        const mine = await getMyAgents();
        const profile = mine.items.find((item) => item.id === editingId);
        if (profile) applyProfile(profile);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingId]);

  const applyProfile = (profile: AgentProfile) => {
    setName(profile.name);
    setDescription(profile.description || '');
    setSystemPrompt(profile.system_prompt || '');
    setResponseMode(profile.response_mode);
    setAvatar(profile.avatar || 'sparkles');
    setVisibility(profile.visibility || 'private');
    setMaxSteps(profile.max_steps ? String(profile.max_steps) : '');
    const tools: Record<string, boolean> = {};
    const approvals: Record<string, boolean> = {};
    for (const tool of profile.tools ?? []) {
      if (tool.enabled) tools[tool.tool_name] = true;
      if (tool.requires_approval) approvals[tool.tool_name] = true;
    }
    setEnabledTools(tools);
    setApprovalTools(approvals);
    setSelectedSkills((profile.skills ?? []).filter((s) => s.enabled).map((s) => s.id));
  };

  // 切换模式不做隐式工具推荐：工具配置始终由用户显式勾选，避免"看不见的默认值"
  const toggleMode = (mode: AgentProfile['response_mode']) => setResponseMode(mode);

  const toggleTool = (toolName: string) => {
    setEnabledTools((prev) => ({ ...prev, [toolName]: !prev[toolName] }));
  };

  const toggleApproval = (toolName: string) => {
    setApprovalTools((prev) => ({ ...prev, [toolName]: !prev[toolName] }));
  };

  const grouped = useMemo(() => {
    const map = new Map<string, ToolCatalogItem[]>();
    for (const item of catalog) {
      const category = categoryOf(item.name);
      const bucket = map.get(category) ?? [];
      bucket.push(item);
      map.set(category, bucket);
    }
    // 按 TOOL_CATEGORIES 的声明顺序排列，"其他"永远垫底
    const order = [...Object.keys(TOOL_CATEGORIES), '其他'];
    return [...map.entries()].sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  }, [catalog]);

  const enabledCount = Object.values(enabledTools).filter(Boolean).length;

  const buildToolsPayload = (): AgentProfileTool[] =>
    Object.entries(enabledTools)
      .filter(([, on]) => on)
      .map(([tool_name]) => ({
        tool_name,
        enabled: true,
        requires_approval: Boolean(approvalTools[tool_name]),
        approval_sub_tools: [],
      }));

  const handleSave = async () => {
    if (!name.trim()) {
      setError('请填写智能体名称');
      return;
    }
    if (!systemPrompt.trim()) {
      setError('请填写系统提示词，它决定智能体的行为方式');
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        system_prompt: systemPrompt.trim(),
        response_mode: responseMode,
        avatar,
        enabled: true,
        listed: false,
        visibility,
        audience_mode: 'all' as const,
        audience_user_ids: [],
        max_steps: maxSteps ? Number(maxSteps) : null,
        tools: buildToolsPayload(),
        skill_ids: selectedSkills,
      };
      const saved = isEditing
        ? await updateAgentProfile(editingId, payload)
        : await createAgentProfile(payload);
      setNotice(isEditing ? '已保存修改' : `「${saved.name}」创建成功`);
      setTimeout(() => navigate('/agents'), 700);
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!isEditing) return;
    if (!window.confirm('确定删除这个智能体吗？此操作不可撤销。')) return;
    try {
      await deleteAgentProfile(editingId);
      navigate('/agents');
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center gap-3 text-sm text-[var(--muted-foreground)]">
        <Loader2 className="animate-spin" size={18} />
        正在加载
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="min-h-screen bg-[var(--surface-0)] text-[var(--foreground)]"
    >
      <header className="sticky top-0 z-20 border-b border-[var(--border-subtle)] bg-[var(--surface-1)]/85 backdrop-blur-xl">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-5">
          <Button variant="ghost" onClick={() => navigate('/agents')} className="gap-2">
            <ArrowLeft size={16} />
            返回商店
          </Button>
          <div className="flex items-center gap-2">
            {isEditing && (
              <Button variant="outline" onClick={handleDelete} className="gap-2 text-rose-600 hover:bg-rose-50">
                <Trash2 size={15} />
                删除
              </Button>
            )}
            <Button onClick={handleSave} disabled={saving} className="gap-2">
              {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              {isEditing ? '保存' : '创建'}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl px-5 py-8 pb-24">
        <div className="mb-8">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            {isEditing ? 'Edit Agent' : 'New Agent'}
          </p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            {isEditing ? '编辑智能体' : '创建我的智能体'}
          </h1>
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            定义它的身份与能力。工具决定它能做什么，风险工具建议开启「需人工审批」。
          </p>
        </div>

        {(error || notice) && (
          <div
            className={cn(
              'mb-5 flex items-center gap-2 rounded-xl border px-4 py-3 text-sm font-medium',
              error
                ? 'border-rose-200 bg-rose-50 text-rose-700'
                : 'border-emerald-200 bg-emerald-50 text-emerald-700',
            )}
          >
            {error ? '⚠' : <Check size={16} />}
            {error || notice}
          </div>
        )}

        {/* 左侧分区导航 + 右侧单区内容（Linear/Notion 设置页范式） */}
        <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
          <nav className="flex gap-1 overflow-x-auto lg:sticky lg:top-24 lg:h-fit lg:flex-col lg:gap-0.5" aria-label="编辑分区">
            {SECTION_META.map(({ key, label, hint, icon: Icon }) => {
              const active = tab === key;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setTab(key)}
                  className={cn(
                    'flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition-all lg:w-full',
                    active
                      ? 'bg-[var(--surface-2)] text-[var(--foreground)]'
                      : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]/60',
                  )}
                  aria-current={active ? 'page' : undefined}
                >
                  <Icon size={15} className="shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold whitespace-nowrap">{label}</span>
                    <span className="hidden text-[11px] lg:block lg:mt-0.5 lg:text-left lg:text-[10px] lg:leading-tight">
                      {sectionSummary(key)}
                    </span>
                  </span>
                  <span className="hidden text-[10px] tabular-nums text-[var(--muted-foreground)] lg:block">
                    {sectionCount(key)}
                  </span>
                </button>
              );
            })}
          </nav>

          <div className="min-w-0">
        {tab === 'basic' && (
          <section className="admin-card p-5">
            <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
              基本信息
            </h2>
            <label className="mb-4 block">
              <span className="mb-1.5 block text-sm font-medium">名称 *</span>
              <Input
                value={name}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
                placeholder="例如：运维值班助手"
                maxLength={120}
              />
            </label>
            <label className="mb-4 block">
              <span className="mb-1.5 block text-sm font-medium">一句话介绍</span>
              <textarea
                value={description}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
                placeholder="它擅长什么？什么场景下找它？"
                rows={2}
                maxLength={200}
                className="w-full resize-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-sm outline-none transition-colors focus:border-brand-400"
              />
            </label>

            <div className="mb-4">
              <span className="mb-1.5 block text-sm font-medium">工作模式</span>
              <div className="grid grid-cols-2 gap-2">
                {MODE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => toggleMode(option.value)}
                    className={cn(
                      'rounded-lg border px-3 py-2 text-left transition-all',
                      responseMode === option.value
                        ? 'border-brand-500 bg-brand-500/10'
                        : 'border-[var(--border-subtle)] hover:bg-[var(--surface-2)]',
                    )}
                  >
                    <span className="block text-sm font-semibold">{option.label}</span>
                    <span className="mt-0.5 block text-[11px] text-[var(--muted-foreground)]">
                      {option.hint}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-4">
              <span className="mb-1.5 block text-sm font-medium">图标</span>
              <div className="flex flex-wrap gap-2">
                {AVATAR_CHOICES.map(({ key, label, Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setAvatar(key)}
                    title={label}
                    aria-label={`图标：${label}`}
                    className={cn(
                      'flex h-9 w-9 items-center justify-center rounded-lg border transition-all',
                      avatar === key
                        ? 'border-brand-500 bg-brand-500/10 text-brand-600'
                        : 'border-[var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[var(--surface-2)]',
                    )}
                  >
                    <Icon size={16} />
                  </button>
                ))}
              </div>
            </div>

            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">最大步骤数（可选）</span>
              <Input
                value={maxSteps}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMaxSteps(e.target.value.replace(/\D/g, ''))}
                placeholder="留空使用系统默认"
                inputMode="numeric"
              />
              <span className="mt-1 block text-[11px] text-[var(--muted-foreground)]">
                单轮对话允许的最大工具调用轮次
              </span>
            </label>
          </section>


        )}

        {/* 提示词分区：原本塞在"行为设定"卡片里，拆成独立分区 */}
        {tab === 'prompt' && (
          <section className="admin-card p-5">
            <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
              提示词
            </h2>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">系统提示词 *</span>
              <textarea
                value={systemPrompt}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setSystemPrompt(e.target.value)}
                rows={20}
                placeholder={'你是公司数据平台的值守助手。\n\n职责：\n1. 接到巡检任务先给出检查清单\n2. 只引用知识库中的口径，不臆造数字\n\n约束：\n- 涉及生产变更的操作必须先说明风险并请求确认'}
                className="w-full resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 font-mono text-sm leading-relaxed outline-none transition-colors focus:border-brand-400"
              />
              <span className="mt-1.5 block text-[11px] text-[var(--muted-foreground)]">
                这段文字会作为系统指令发送给模型，建议写清职责、边界与输出风格
              </span>
            </label>
          </section>
        )}
          </div>
        </div>
        {/* 技能绑定（tab=skill） */}
        {tab === 'skill' && (
          <section className="admin-card mt-5 p-5">
            <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
              技能
            </h2>
            <p className="mt-1 text-xs text-[var(--muted-foreground)]">
              技能是"按什么流程做事"的说明书（如周报格式、巡检清单），与工具互补。
            </p>
            {skills.length === 0 ? (
              <p className="mt-4 rounded-xl border border-dashed border-[var(--border-subtle)] px-4 py-6 text-center text-sm text-[var(--muted-foreground)]">
                暂无可用技能
              </p>
            ) : (
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {skills.map((skill) => {
                  const on = selectedSkills.includes(skill.id);
                  return (
                    <button
                      key={skill.id}
                      type="button"
                      onClick={() =>
                        setSelectedSkills((prev) =>
                          on ? prev.filter((id) => id !== skill.id) : [...prev, skill.id],
                        )
                      }
                      className={cn(
                        'flex items-start gap-2.5 rounded-xl border px-3 py-2.5 text-left transition-all',
                        on
                          ? 'border-brand-500 bg-brand-500/5'
                          : 'border-[var(--border-subtle)] hover:bg-[var(--surface-2)]',
                      )}
                    >
                      <span
                        className={cn(
                          'mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border',
                          on ? 'border-brand-500 bg-brand-500 text-white' : 'border-[var(--border-medium)]',
                        )}
                      >
                        {on && <Check size={11} />}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-sm font-medium">{skill.name}</span>
                        <span className="block truncate text-[11px] text-[var(--muted-foreground)]">
                          {skill.description || skill.slug}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* 知识库 / MCP：说明当前可用范围，避免误解 */}
        {(tab === 'knowledge' || tab === 'mcp') && (
          <section className="admin-card mt-5 p-5">
            <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
              {tab === 'knowledge' ? '知识库' : 'MCP'}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--muted-foreground)]">
              {tab === 'knowledge'
                ? '启用「知识库检索」工具后，智能体即可在回答时检索已建知识库中的文档。知识库本身在「管理后台 → 知识库」中维护，此处只需确保工具已勾选。'
                : 'MCP 服务在「管理后台 → 集成管理」中配置；配置完成后，相关工具会出现在上方「工具」列表里，勾选即可使用。'}
            </p>
          </section>
        )}

        {/* 工具配置 */}
        {tab === 'tool' && (
        <section className="admin-card mt-5 p-5">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
                可用工具
              </h2>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                已启用 {enabledCount} / {catalog.length} 个 · 带盾标的工具建议开启人工审批
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEnabledTools(Object.fromEntries(catalog.map((c) => [c.name, true])));
                }}
              >
                全选
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setEnabledTools({});
                }}
              >
                清空
              </Button>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {grouped.map(([category, items]) => (
              <div key={category} className="admin-inset rounded-xl p-3">
                <p className="mb-2 text-xs font-bold uppercase tracking-[0.1em] text-[var(--muted-foreground)]">
                  {category}
                </p>
                <div className="flex flex-col gap-1">
                  {items.map((item) => {
                    const on = Boolean(enabledTools[item.name]);
                    const needsApproval = Boolean(approvalTools[item.name]);
                    return (
                      <div
                        key={item.name}
                        className={cn(
                          'flex items-start gap-3 rounded-lg px-2.5 py-2 transition-colors',
                          on ? 'bg-[var(--surface-1)]' : 'hover:bg-[var(--surface-1)]/60',
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => toggleTool(item.name)}
                          role="switch"
                          aria-checked={on}
                          aria-label={`启用 ${item.label}`}
                          className={cn(
                            'mt-0.5 flex h-5 w-9 flex-shrink-0 items-center rounded-full p-0.5 transition-colors',
                            on ? 'bg-brand-500' : 'bg-[var(--border-medium)]',
                          )}
                        >
                          <span
                            className={cn(
                              'block h-4 w-4 rounded-full bg-white shadow transition-transform',
                              on && 'translate-x-4',
                            )}
                          />
                        </button>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold">{item.label}</span>
                            <code className="rounded bg-[var(--surface-2)] px-1 py-0.5 text-[10px] text-[var(--muted-foreground)]">
                              {item.name}
                            </code>
                            {on && item.approval_scope?.length ? (
                              <Badge variant="warning" size="sm">
                                <ShieldAlert size={11} />
                                高风险
                              </Badge>
                            ) : null}
                          </div>
                          <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--muted-foreground)]">
                            {item.description}
                          </p>
                        </div>
                        {on && (
                          <label className="flex flex-shrink-0 cursor-pointer items-center gap-1.5 text-[11px] text-[var(--muted-foreground)]">
                            <input
                              type="checkbox"
                              checked={needsApproval}
                              onChange={() => toggleApproval(item.name)}
                              className="h-3.5 w-3.5 accent-amber-500"
                            />
                            需审批
                          </label>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </section>
        )}

        {/* 底部操作条 */}
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-[var(--border-subtle)] bg-[var(--surface-1)]/90 backdrop-blur-xl">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-5 py-3">
            <p className="text-xs text-[var(--muted-foreground)]">
              {enabledCount > 0 ? (
                <>将启用 {enabledCount} 个工具</>
              ) : (
                <>未选择工具，智能体只能进行纯文本对话</>
              )}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => navigate('/agents')}>
                取消
              </Button>
              <Button onClick={handleSave} disabled={saving} className="gap-2">
                {saving ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
                {isEditing ? '保存修改' : '创建智能体'}
              </Button>
            </div>
          </div>
        </div>
      </main>
    </motion.div>
  );
};