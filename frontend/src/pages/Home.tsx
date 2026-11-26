import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Bot,
  Calculator,
  Database,
  Globe,
  Layout,
  Mail,
  Map,
  Plus,
  Presentation,
  Search,
  Send,
  ShieldCheck,
  Table2,
} from 'lucide-react';
import { AgentSelector } from '../components/ui/AgentSelector';
import { ArtifactMiniPreview, type MiniPreviewKind } from '../components/ui/ArtifactMiniPreview';
import { InlineSpinner } from '../components/ui/Skeletons';
import { getStoredUser } from '../services/authService';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';
import { cn } from '../lib/utils';

const QUICK_STARTS = [
  { text: '根据 Q4 华东区销售数据，设计一份 10 页商务风季度复盘 PPT', label: 'Q4 季度复盘 PPT', tag: 'SVG', mode: 'ppt', icon: Presentation, color: '#EA580C' },
  { text: '为 AI 硬件新品设计一个极简官网落地页，包含预约表单', label: '产品发布落地页', tag: 'React', mode: 'website', icon: Globe, color: '#0284C7' },
  { text: '清洗上传的营收明细表，按大区汇总同比增速并生成 Excel', label: '营收数据报表', tag: 'Excel', mode: 'general', icon: Table2, color: '#059669' },
  { text: '检索本周核心客户的未读邮件并起草回复建议', label: '重要邮件汇总', tag: 'IMAP', mode: 'general', icon: Mail, color: '#7C3AED' },
] as const;

const WORKFLOW_CARDS = [
  {
    id: 'ppt',
    category: 'ppt',
    badge: '内置',
    cap: 'SVG → PPTX',
    title: 'PPT 设计师',
    desc: '原生矢量排版，支持风格切换与一键导出可编辑母版',
    mode: 'ppt',
    image: '/images/workflows/ppt.jpg',
    prompt: '帮我制作一份 10 页极简商务风季度复盘 PPT，包含核心 KPI 与行动计划',
  },
  {
    id: 'website',
    category: 'website',
    badge: '内置',
    cap: 'React / Vue',
    title: '网站工程师',
    desc: '从需求到响应式页面原型，支持短链预览与代码导出',
    mode: 'website',
    image: '/images/workflows/website.jpg',
    prompt: '设计一个极简风格的 AI 产品官网落地页，包含交互式特性与预约表单',
  },
  {
    id: 'office',
    category: 'office',
    badge: '内置',
    cap: 'UniverJS',
    title: '办公文档与表格助手',
    desc: '浏览器内直接预览编辑电子表格与 Word，保留动态公式',
    mode: 'general',
    image: '/images/workflows/office.jpg',
    prompt: '清洗上传的营收明细表，按大区汇总同比增速并生成带公式的 Excel 报表',
  },
  {
    id: 'knowledge',
    category: 'knowledge',
    badge: 'RAG',
    cap: '图谱 · 邮箱',
    title: '知识图谱与邮箱助手',
    desc: '企业知识库精准溯源、邮件自动归纳与安全起草发送',
    mode: 'general',
    image: '/images/workflows/knowledge.jpg',
    prompt: '检索知识库中的交付规范，并汇总本周核心客户的未读重要邮件',
  },
] as const;

interface ShowcaseArtifact {
  id: string;
  type: MiniPreviewKind;
  filterKey: 'ppt' | 'website' | 'office' | 'report';
  title: string;
  meta: string;
  slug: string;
  mode: string;
  prompt: string;
}

const SHOWCASE_ARTIFACTS: ShowcaseArtifact[] = [
  { id: 'g1', type: 'ppt', filterKey: 'ppt', title: '2026 Q4 季度经营复盘', meta: '12 页 · SVG 矢量', slug: '/app/q4-review', mode: 'ppt', prompt: '参考季度经营复盘结构，帮我生成一份 12 页 SVG 矢量 PPT' },
  { id: 'g2', type: 'website', filterKey: 'website', title: 'AgenticOS 3.2 产品发布页', meta: 'React · 短链预览', slug: '/app/launch-v3', mode: 'website', prompt: '生成一个极简风格的产品发布落地页，支持响应式预览' },
  { id: 'g3', type: 'office', filterKey: 'office', title: '华东区营收与预算达成表', meta: 'UniverJS · 14 公式', slug: '/app/q4-sheet', mode: 'general', prompt: '生成一份带同比、环比与预算达成率公式的营收汇总 Excel 表' },
  { id: 'g4', type: 'report', filterKey: 'report', title: '供应链风险知识图谱分析', meta: 'LlamaIndex · 38 节点', slug: '/app/risk-kg', mode: 'general', prompt: '基于企业知识库生成供应链风险分析报告与关键关系图谱' },
];

const SCENARIO_TEMPLATES = [
  { title: '产品路线图评审', desc: '16:9 甘特图与里程碑卡片', mode: 'ppt', prompt: '制作一份产品路线图与里程碑评审 PPT', icon: Map, tone: 'aos-tone-amber' },
  { title: 'SaaS 定价对比页', desc: '月付/年付切换与响应式布局', mode: 'website', prompt: '生成一个高转化 SaaS 定价与对比页面', icon: Layout, tone: 'aos-tone-sky' },
  { title: '预算偏差分析表', desc: '自动生成同比、环比与达成公式', mode: 'general', prompt: '生成季度预算执行偏差分析 Excel 表', icon: Calculator, tone: 'aos-tone-emerald' },
  { title: '项目风险周报邮件', desc: '自动提炼阻塞项，发送前人工确认', mode: 'general', prompt: '总结本周项目风险并起草给管理层的周报邮件', icon: Send, tone: 'aos-tone-violet' },
] as const;

export const Home = () => {
  const [inputValue, setInputValue] = useState('');
  const [agentProfiles, setAgentProfiles] = useState<AgentProfile[]>([]);
  const [agentsState, setAgentsState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [selectedAgentProfileId, setSelectedAgentProfileId] = useState<number | null>(null);
  const [wfFilter, setWfFilter] = useState<string>('all');
  const [galFilter, setGalFilter] = useState<string>('all');
  const [galSearch, setGalSearch] = useState<string>('');
  const [ragEnabled, setRagEnabled] = useState<boolean>(true);
  const [showBottomBar, setShowBottomBar] = useState(false);

  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement>(null);
  const heroComposerRef = useRef<HTMLDivElement>(null);
  const heroTextareaRef = useRef<HTMLTextAreaElement>(null);

  const [user] = useState(() => getStoredUser());
  const isLoggedIn = Boolean(user);
  const selectedAgent = agentProfiles.find((a) => a.id === selectedAgentProfileId) || null;
  const hasAppliedDefaultRef = useRef(false);

  const loadAgents = useCallback(() => {
    if (!isLoggedIn) return;
    setAgentsState('loading');
    getMyAgents()
      .then((res) => {
        setAgentProfiles(res.items);
        if (!hasAppliedDefaultRef.current) {
          const general = res.items.find((a) => a.slug === 'general');
          if (general) setSelectedAgentProfileId(general.id);
          hasAppliedDefaultRef.current = true;
        }
        setAgentsState('idle');
      })
      .catch(() => setAgentsState('error'));
  }, [isLoggedIn]);

  useEffect(() => {
    loadAgents();
  }, [loadAgents]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    const onScroll = () => {
      const hero = heroComposerRef.current;
      if (!hero) return;
      const scrollerRect = scroller.getBoundingClientRect();
      const heroRect = hero.getBoundingClientRect();
      setShowBottomBar(heroRect.bottom < scrollerRect.top + 36);
    };
    scroller.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => scroller.removeEventListener('scroll', onScroll);
  }, []);

  const navigateToChat = (message: string, modeOverride?: string) => {
    const trimmed = message.trim();
    if (!trimmed) return;
    if (!isLoggedIn) {
      navigate('/login', { state: { from: trimmed } });
      return;
    }
    navigate('/chat', {
      state: {
        initialMessage: trimmed,
        mode: modeOverride || selectedAgent?.response_mode || 'general',
        agentProfileId: selectedAgentProfileId,
      },
    });
  };

  const handleSend = () => navigateToChat(inputValue);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (nativeEvent.isComposing || e.key === 'Process') return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const filteredWorkflows =
    wfFilter === 'all' ? WORKFLOW_CARDS : WORKFLOW_CARDS.filter((w) => w.category === wfFilter);

  const filteredArtifacts = useMemo(() => {
    const q = galSearch.trim().toLowerCase();
    return SHOWCASE_ARTIFACTS.filter(
      (item) =>
        (galFilter === 'all' || item.filterKey === galFilter) &&
        (!q || item.title.toLowerCase().includes(q) || item.meta.toLowerCase().includes(q)),
    );
  }, [galFilter, galSearch]);

  return (
    <motion.div
      key="home"
      initial={false}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      className="relative flex h-full w-full overflow-hidden font-sans text-[var(--foreground)]"
    >
      <div className="relative z-10 flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <div ref={scrollRef} id="main-content" className="min-h-0 flex-1 overflow-y-auto px-1 pb-28 sm:px-3">
          <div className="mx-auto w-full max-w-[1140px] px-1 sm:px-4">
            {/* Hero 区 + 原型同款动态 SVG 星环 */}
            <section className="relative flex flex-col items-center pb-7 pt-5 text-center sm:pt-9">
              <svg
                className="pointer-events-none absolute -top-2 left-1/2 h-[120px] w-[480px] max-w-full -translate-x-1/2 opacity-60"
                viewBox="0 0 480 120"
                fill="none"
                aria-hidden="true"
              >
                <ellipse cx="240" cy="64" rx="210" ry="38" stroke="#EA580C" strokeOpacity="0.18" strokeWidth="1" className="aos-svg-flow" />
                <ellipse cx="240" cy="64" rx="150" ry="26" stroke="#0284C7" strokeOpacity="0.16" strokeWidth="1" strokeDasharray="3 6" />
                <circle cx="56" cy="52" r="3" fill="#EA580C" fillOpacity="0.55">
                  <animate attributeName="cy" values="52;46;52" dur="4s" repeatCount="indefinite" />
                </circle>
                <circle cx="424" cy="56" r="3.5" fill="#0284C7" fillOpacity="0.5">
                  <animate attributeName="cy" values="56;62;56" dur="4.6s" repeatCount="indefinite" />
                </circle>
                <circle cx="385" cy="24" r="2.2" fill="#7C3AED" fillOpacity="0.5">
                  <animate attributeName="opacity" values="0.25;0.85;0.25" dur="3.2s" repeatCount="indefinite" />
                </circle>
              </svg>

              <motion.h1
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.36, ease: [0.22, 1, 0.36, 1] }}
                className="relative z-10 text-[28px] font-bold leading-tight tracking-tight text-[var(--foreground)] sm:text-[38px]"
              >
                今天想让智能体帮你做什么？
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05, duration: 0.36, ease: [0.22, 1, 0.36, 1] }}
                className="relative z-10 mt-2.5 max-w-xl text-[13.5px] text-[var(--muted-foreground)] sm:text-[14.5px]"
              >
                多智能体协同创作 · 支持 PPT、网站、办公文档与邮件 · 工具级人工审批
              </motion.p>

              {/* 主输入框卡片（1:1 复刻原型白底圆角卡片 + 底部胶囊控制栏） */}
              <motion.div
                ref={heroComposerRef}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                className="aos-composer-card relative z-10 mt-6 w-full max-w-[820px] rounded-[24px] p-4 text-left sm:p-5"
              >
                <textarea
                  ref={heroTextareaRef}
                  aria-label="输入消息"
                  rows={3}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  maxLength={4000}
                  placeholder="描述你的任务目标，按 Enter 直接执行（往下滑动页面试试底部悬浮输入框）..."
                  className="w-full resize-none border-0 bg-transparent text-[15px] leading-relaxed text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-subtle)] pt-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {user ? (
                      agentsState === 'error' ? (
                        <span className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                          智能体加载失败
                          <button type="button" onClick={loadAgents} className="font-semibold text-[var(--foreground)] underline">
                            重试
                          </button>
                        </span>
                      ) : agentProfiles.length > 0 ? (
                        <AgentSelector
                          agents={agentProfiles}
                          selectedId={selectedAgentProfileId}
                          onSelect={(agent) => setSelectedAgentProfileId(agent.id)}
                          variant="full"
                        />
                      ) : (
                        <InlineSpinner label="加载智能体…" />
                      )
                    ) : (
                      <button type="button" onClick={() => navigate('/login')} className="aos-pill-btn">
                        <Bot size={14} style={{ color: '#EA580C' }} />
                        <span>PPT 设计师</span>
                      </button>
                    )}

                    <span className="aos-pill-btn hidden sm:inline-flex">
                      <ShieldCheck size={14} style={{ color: '#059669' }} />
                      <span>审批: 询问</span>
                    </span>

                    <button
                      type="button"
                      onClick={() => setRagEnabled((v) => !v)}
                      className={cn('aos-pill-btn', ragEnabled && 'active')}
                    >
                      <Database size={14} />
                      <span>知识库</span>
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={handleSend}
                    disabled={!inputValue.trim()}
                    aria-label="发送消息"
                    className="aos-cta-pill ml-auto disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <span>开始执行</span>
                    <ArrowUp size={14} />
                  </button>
                </div>
              </motion.div>

              {/* 试一试快捷芯片 */}
              <div className="relative z-10 mt-4 flex max-w-[820px] flex-wrap items-center justify-center gap-2">
                <span className="mr-1 text-xs text-[var(--muted-foreground)]">试一试</span>
                {QUICK_STARTS.map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => navigateToChat(item.text, item.mode)}
                    className="aos-pill-btn aos-glass-surface !py-1.5 !text-xs"
                  >
                    <item.icon size={14} style={{ color: item.color }} />
                    <span>{item.label}</span>
                    <span className="text-[10.5px] text-[var(--muted-foreground)]">{item.tag}</span>
                  </button>
                ))}
              </div>
            </section>

            {/* Section 1: 精选智能体与场景套件（1:1 复刻原版摄影视觉卡） */}
            <section className="mt-3">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="mr-2 text-[16px] font-semibold text-[var(--foreground)]">精选智能体与场景套件</h2>
                  {[
                    { id: 'all', label: '全部' },
                    { id: 'ppt', label: '演示文稿' },
                    { id: 'website', label: '前端构建' },
                    { id: 'office', label: '办公表格' },
                    { id: 'knowledge', label: '知识与邮件' },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setWfFilter(tab.id)}
                      className={cn('aos-pill-btn !py-1 !px-3 !text-xs', wfFilter === tab.id && 'active')}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/agents')}
                  className="inline-flex items-center gap-1 border-0 bg-transparent text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
                >
                  <span>全部 5 个内置智能体</span>
                  <ArrowRight size={14} />
                </button>
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {filteredWorkflows.map((w) => (
                  <button
                    key={w.id}
                    type="button"
                    onClick={() => navigateToChat(w.prompt, w.mode)}
                    className="aos-workflow-card group text-left"
                  >
                    <img src={w.image} alt={w.title} loading="lazy" />
                    <div className="aos-workflow-scrim" />
                    <div className="absolute left-3 right-3 top-3 flex items-center justify-between gap-2">
                      <span className="aos-glass-tag rounded-full px-2.5 py-0.5 text-[10.5px] font-medium">
                        {w.badge}
                      </span>
                      <span className="aos-glass-tag rounded-full px-2.5 py-0.5 text-[10.5px] font-medium">
                        {w.cap}
                      </span>
                    </div>
                    <div className="absolute bottom-3.5 left-3.5 right-3.5 flex items-end justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[15px] font-semibold leading-snug text-white">{w.title}</div>
                        <div className="mt-0.5 line-clamp-1 text-[11.5px] text-white/75">{w.desc}</div>
                      </div>
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-[#141416] shadow-md transition-transform duration-200 group-hover:scale-110">
                        <ArrowUpRight size={16} />
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            {/* Section 2: 产物预览与快捷搜索区（1:1 补齐截图 1 中下区域） */}
            <section className="mt-10">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  {[
                    { id: 'all', label: '全部产物' },
                    { id: 'ppt', label: 'PPT 演示' },
                    { id: 'website', label: '交互网站' },
                    { id: 'office', label: '办公表格' },
                    { id: 'report', label: '知识报告' },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setGalFilter(tab.id)}
                      className={cn('aos-pill-btn !py-1.5 !px-3.5 !text-xs', galFilter === tab.id && 'active')}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-2">
                  <div className="relative">
                    <Search
                      size={14}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted-foreground)]"
                    />
                    <input
                      type="text"
                      value={galSearch}
                      onChange={(e) => setGalSearch(e.target.value)}
                      placeholder="搜索产物、模板..."
                      className="aos-glass-surface w-44 rounded-full py-1.5 pl-8 pr-3 text-xs text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)] focus:border-[var(--border-strong)] sm:w-52"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate('/gallery')}
                    className="hidden items-center gap-1 border-0 bg-transparent text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] sm:inline-flex cursor-pointer"
                  >
                    <span>作品库</span>
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>

              {filteredArtifacts.length === 0 ? (
                <div className="aos-glass-surface rounded-2xl py-10 text-center text-xs text-[var(--muted-foreground)]">
                  没有匹配的产物
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {filteredArtifacts.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => navigateToChat(item.prompt, item.mode)}
                      className="aos-glass-surface aos-surface-interactive group flex flex-col gap-3 rounded-2xl p-3 text-left cursor-pointer"
                    >
                      <div className="aspect-[16/10] w-full overflow-hidden rounded-xl border border-[var(--border-subtle)]">
                        <ArtifactMiniPreview kind={item.type} />
                      </div>
                      <div className="px-1">
                        <div className="truncate text-[13.5px] font-semibold text-[var(--foreground)]">{item.title}</div>
                        <div className="mt-1 flex items-center justify-between text-[11px] text-[var(--muted-foreground)]">
                          <span>{item.meta}</span>
                          <span className="font-mono">{item.slug}</span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </section>

            {/* Section 3: 团队高频场景模板 */}
            <section className="mt-10">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-[16px] font-semibold text-[var(--foreground)]">团队高频场景模板</h2>
                <button
                  type="button"
                  onClick={() => navigate('/agents')}
                  className="border-0 bg-transparent text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
                >
                  自定义模板 →
                </button>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {SCENARIO_TEMPLATES.map((tpl) => (
                  <button
                    key={tpl.title}
                    type="button"
                    onClick={() => navigateToChat(tpl.prompt, tpl.mode)}
                    className="aos-glass-surface aos-surface-interactive flex items-start gap-3 rounded-2xl p-4 text-left cursor-pointer"
                  >
                    <span className={cn('aos-icon-badge h-10 w-10', tpl.tone)}>
                      <tpl.icon size={17} />
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-[var(--foreground)]">{tpl.title}</div>
                      <div className="mt-1 text-[11px] leading-relaxed text-[var(--muted-foreground)]">{tpl.desc}</div>
                    </div>
                  </button>
                ))}
              </div>
            </section>
          </div>
        </div>
      </div>

      {/* 下滑后底部居中自动浮现的毛玻璃快捷输入框 */}
      <div
        className={cn(
          'aos-floating-bottom-bar flex items-center gap-2 rounded-full px-3 py-2',
          showBottomBar && 'aos-visible',
        )}
      >
        <button
          type="button"
          onClick={() => {
            scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
            setTimeout(() => heroTextareaRef.current?.focus(), 250);
          }}
          aria-label="回到顶部输入"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
        >
          <Plus size={16} />
        </button>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="描述你想执行的任务..."
          className="min-w-0 flex-1 border-0 bg-transparent px-1 text-[13.5px] text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!inputValue.trim()}
          aria-label="发送"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] cursor-pointer disabled:opacity-40"
        >
          <ArrowUp size={15} />
        </button>
      </div>
    </motion.div>
  );
};
