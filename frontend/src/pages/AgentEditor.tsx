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
  ArrowLeft, Bot, Check, Database, Globe, Loader2, Mail, Presentation,
  Save, ShieldAlert, Sparkles, Trash2,
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
        skill_ids: [],
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

        <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
          {/* 基础信息 */}
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

          {/* 可见性 + 提示词 */}
          <section className="admin-card flex flex-col p-5">
            <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
              行为设定
            </h2>
            <label className="mb-4 block">
              <span className="mb-1.5 block text-sm font-medium">系统提示词 *</span>
              <textarea
                value={systemPrompt}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setSystemPrompt(e.target.value)}
                placeholder={'你是公司数据平台的值守助手。\n\n职责：\n1. 接到巡检任务先给出检查清单\n2. 只引用知识库中的口径，不臆造数字\n\n约束：\n- 涉及生产变更的操作必须先说明风险并请求确认'}
                rows={12}
                className="w-full resize-y rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 font-mono text-xs leading-relaxed outline-none transition-colors focus:border-brand-400"
              />
              <span className="mt-1 block text-[11px] text-[var(--muted-foreground)]">
                这段文字会作为系统指令发送给模型，建议写清职责、边界与输出风格
              </span>
            </label>

            <div className="mt-auto">
              <span className="mb-1.5 block text-sm font-medium">可见范围</span>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { value: 'private' as const, label: '仅自己', hint: '不出现在商店给其他人' },
                  { value: 'public' as const, label: '公开', hint: '同事可在商店安装' },
                ].map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setVisibility(option.value)}
                    className={cn(
                      'rounded-lg border px-3 py-2 text-left transition-all',
                      visibility === option.value
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
          </section>
        </div>

        {/* 工具配置 */}
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