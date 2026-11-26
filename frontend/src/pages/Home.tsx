import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  Bot,
  Calculator,
  Globe,
  Layout,
  LayoutGrid,
  Mail,
  Map,
  MessageSquareText,
  Plus,
  Presentation,
  Send,
  Sparkles,
  Table2,
} from 'lucide-react';
import { AgentSelector } from '../components/ui/AgentSelector';
import { InlineSpinner } from '../components/ui/Skeletons';
import { getStoredUser } from '../services/authService';
import { canEnterAdmin } from '../services/authTokenStore';
import { AgentProfile, getMyAgents } from '../services/agentProfileService';
import { cn } from '../lib/utils';

/** 试一试快捷提示：点击直接填框或发起 */
const QUICK_STARTS = [
  { text: '帮我做个 PPT', label: 'Q4 季度复盘 PPT', tag: 'SVG', mode: 'ppt', icon: Presentation, color: '#EA580C' },
  { text: '写一个网站首页', label: '产品发布落地页', tag: 'React', mode: 'website', icon: Globe, color: '#0284C7' },
  { text: '帮我分析数据', label: '营收数据报表', tag: 'Excel', mode: 'general', icon: Table2, color: '#059669' },
  { text: '写一封邮件', label: '重要邮件汇总', tag: 'IMAP', mode: 'general', icon: Mail, color: '#7C3AED' },
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
    prompt: '帮我制作一份 10 页极简商务风季度复盘 PPT，包含核心 KPI 与行动计划',
    bg: 'linear-gradient(135deg, #2C231E 0%, #4E3B30 52%, #1C1917 100%)',
    accent: '#FB923C',
  },
  {
    id: 'website',
    category: 'website',
    badge: '内置',
    cap: 'React / Vue',
    title: '网站工程师',
    desc: '从需求到响应式页面原型，支持短链预览与代码导出',
    mode: 'website',
    prompt: '设计一个极简风格的 AI 产品官网落地页，包含交互式特性与预约表单',
    bg: 'linear-gradient(135deg, #172536 0%, #243B53 52%, #111827 100%)',
    accent: '#38BDF8',
  },
  {
    id: 'office',
    category: 'office',
    badge: '内置',
    cap: 'UniverJS',
    title: '办公文档与表格助手',
    desc: '浏览器内直接预览编辑电子表格与 Word，保留动态公式',
    mode: 'general',
    prompt: '清洗上传的营收明细表，按大区汇总同比增速并生成带公式的 Excel 报表',
    bg: 'linear-gradient(135deg, #142B24 0%, #1F4539 52%, #111917 100%)',
    accent: '#34D399',
  },
  {
    id: 'knowledge',
    category: 'knowledge',
    badge: 'RAG',
    cap: '图谱 · 邮箱',
    title: '知识图谱与邮箱助手',
    desc: '企业知识库精准溯源、邮件自动归纳与安全起草发送',
    mode: 'general',
    prompt: '检索知识库中的交付规范，并汇总本周核心客户的未读重要邮件',
    bg: 'linear-gradient(135deg, #251B36 0%, #3B2854 52%, #161221 100%)',
    accent: '#A78BFA',
  },
] as const;

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
  const [showBottomBar, setShowBottomBar] = useState(false);

  const navigate = useNavigate();
  const scrollRef = useRef<HTMLDivElement>(null);
  const heroComposerRef = useRef<HTMLDivElement>(null);
  const heroTextareaRef = useRef<HTMLTextAreaElement>(null);

  // 保持与 homeAgentSelection.test.ts 一致：惰性 state 稳定 user 引用
  const [user] = useState(() => getStoredUser());
  const isLoggedIn = Boolean(user);
  const showAdmin = isLoggedIn && canEnterAdmin();
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

  // 监听首页滚动容器：主输入框滚出视口后，底部居中平滑弹出快捷输入框
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    const onScroll = () => {
      const hero = heroComposerRef.current;
      if (!hero) return;
      const scrollerRect = scroller.getBoundingClientRect();
      const heroRect = hero.getBoundingClientRect();
      setShowBottomBar(heroRect.bottom < scrollerRect.top + 32);
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

  return (
    <motion.div
      key="home"
      initial={false}
      exit={{ opacity: 0, transition: { duration: 0.2 } }}
      className="relative flex h-full w-full overflow-hidden font-sans text-[var(--foreground)] p-2.5 sm:p-3"
    >

      {/* 右侧主列：顶部固定栏 + 独立滚动内容区 */}
      <div className="relative z-10 flex-1 min-w-0 h-full flex flex-col overflow-hidden">
        {/* 顶部固定栏（右上角放登录/注册，绝不放新建智能体，无多余状态文案） */}
        <header className="shrink-0 pb-2 px-1 sm:px-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">

          </div>

          <div className="aos-glass-surface flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs">
            {user ? (
              <>
                <button
                  type="button"
                  onClick={() => navigate('/chat')}
                  className="px-3 py-1 rounded-full text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)] font-medium transition-colors cursor-pointer"
                >
                  进入工作台
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/agents')}
                  className="px-3 py-1 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] font-medium cursor-pointer"
                >
                  {user.name}
                </button>
              </>
            ) : (
              <>
                <button
                  type="button"
                  onClick={() => navigate('/login')}
                  className="px-3 py-1 rounded-full text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)] font-medium transition-colors cursor-pointer"
                >
                  登录
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/signup')}
                  className="px-3.5 py-1 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] font-semibold hover:opacity-90 transition-opacity cursor-pointer"
                >
                  注册
                </button>
              </>
            )}
          </div>
        </header>

        {/* 独立滚动内容区 */}
        <div ref={scrollRef} id="main-content" className="flex-1 min-h-0 overflow-y-auto px-1 sm:px-4 pb-28">
          <div className="w-full max-w-[1120px] mx-auto">
            {/* Hero 区 + 轻盈动态 SVG 星环 */}
            <section className="relative pt-6 sm:pt-10 pb-8 flex flex-col items-center text-center">
              <svg
                className="pointer-events-none absolute -top-1 left-1/2 -translate-x-1/2 w-[480px] max-w-full h-[120px] opacity-60"
                viewBox="0 0 480 120"
                fill="none"
                aria-hidden="true"
              >
                <ellipse cx="240" cy="64" rx="210" ry="38" stroke="#EA580C" strokeOpacity="0.2" strokeWidth="1" className="aos-svg-flow" />
                <ellipse cx="240" cy="64" rx="150" ry="26" stroke="#0284C7" strokeOpacity="0.16" strokeWidth="1" strokeDasharray="3 6" />
                <circle cx="56" cy="52" r="3" fill="#EA580C" fillOpacity="0.55">
                  <animate attributeName="cy" values="52;46;52" dur="4s" repeatCount="indefinite" />
                </circle>
                <circle cx="424" cy="56" r="3.5" fill="#0284C7" fillOpacity="0.5">
                  <animate attributeName="cy" values="56;62;56" dur="4.6s" repeatCount="indefinite" />
                </circle>
              </svg>

              <motion.h1
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="relative z-10 text-3xl sm:text-4xl font-bold tracking-tight text-[var(--foreground)]"
              >
                今天想让智能体帮你做什么？
              </motion.h1>
              <motion.p
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.05, duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className="relative z-10 mt-2.5 text-sm sm:text-[15px] text-[var(--muted-foreground)] max-w-xl"
              >
                多智能体协同创作 · 支持 PPT、网站、办公文档与邮件 · 工具级人工审批
              </motion.p>

              {/* 主输入框卡片 */}
              <motion.div
                ref={heroComposerRef}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.09, duration: 0.42, ease: [0.16, 1, 0.3, 1] }}
                className="relative z-10 aos-composer w-full max-w-[820px] mt-6 rounded-[24px] p-4 sm:p-5 text-left"
              >
                <textarea
                  ref={heroTextareaRef}
                  aria-label="输入消息"
                  rows={3}
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  maxLength={4000}
                  placeholder="描述你的任务目标，按 Enter 直接执行（Shift+Enter 换行）..."
                  className="w-full bg-transparent resize-none outline-none text-[15px] leading-relaxed text-[var(--foreground)] placeholder:text-[var(--muted-foreground)]"
                />
                <div className="mt-3 pt-3 border-t border-[var(--border)] flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
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
                      <span className="text-xs text-[var(--muted-foreground)]">登录后可选择专属智能体</span>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={handleSend}
                    disabled={!inputValue.trim()}
                    aria-label="发送消息"
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-xs font-semibold bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span>开始执行</span>
                    <ArrowUp size={14} />
                  </button>
                </div>
              </motion.div>

              {/* 试一试快捷芯片 */}
              <div className="relative z-10 mt-4 flex flex-wrap items-center justify-center gap-2 max-w-[820px]">
                <span className="text-xs text-[var(--muted-foreground)] mr-1">试一试</span>
                {QUICK_STARTS.map((item) => (
                  <button
                    key={item.text}
                    type="button"
                    onClick={() => navigateToChat(item.text, item.mode)}
                    className="aos-glass-surface inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium text-[var(--foreground)] hover:-translate-y-0.5 transition-transform cursor-pointer"
                  >
                    <item.icon size={13} style={{ color: item.color }} />
                    <span>{item.label}</span>
                    <span className="text-[10.5px] text-[var(--muted-foreground)]">{item.tag}</span>
                  </button>
                ))}
              </div>
            </section>

            {/* 精选智能体与场景套件（4 列视觉卡） */}
            <section className="mt-4">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[16px] font-semibold text-[var(--foreground)] mr-2">精选智能体与场景套件</h2>
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
                      className={cn(
                        'px-3 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer',
                        wfFilter === tab.id
                          ? 'bg-[var(--primary)] text-[var(--primary-foreground)]'
                          : 'bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
                      )}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => navigate('/agents')}
                  className="text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] inline-flex items-center gap-1 cursor-pointer"
                >
                  <span>全部智能体</span>
                  <ArrowRight size={14} />
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {filteredWorkflows.map((w) => (
                  <button
                    key={w.id}
                    type="button"
                    onClick={() => navigateToChat(w.prompt, w.mode)}
                    style={{ background: w.bg }}
                    className="group relative rounded-[20px] overflow-hidden aspect-[16/10] p-3.5 text-left flex flex-col justify-between border border-white/10 shadow-sm hover:-translate-y-1 hover:shadow-lg transition-all duration-200 cursor-pointer"
                  >
                    {/* 极简几何装饰 SVG */}
                    <svg className="pointer-events-none absolute inset-0 w-full h-full opacity-25" viewBox="0 0 280 175" fill="none" aria-hidden="true">
                      <circle cx="220" cy="40" r="72" stroke={w.accent} strokeWidth="1" strokeDasharray="4 6" />
                      <circle cx="60" cy="145" r="56" stroke={w.accent} strokeWidth="1" strokeOpacity="0.5" />
                    </svg>
                    <div className="relative z-10 flex items-center justify-between gap-2">
                      <span className="text-[10.5px] font-medium px-2.5 py-0.5 rounded-full bg-black/40 text-white border border-white/15">
                        {w.badge}
                      </span>
                      <span className="text-[10.5px] font-medium px-2.5 py-0.5 rounded-full bg-black/40 text-white border border-white/15">
                        {w.cap}
                      </span>
                    </div>
                    <div className="relative z-10 flex items-end justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[15px] font-semibold text-white leading-snug">{w.title}</div>
                        <div className="text-[11.5px] text-white/75 line-clamp-1 mt-0.5">{w.desc}</div>
                      </div>
                      <span className="w-8 h-8 rounded-full bg-white text-[#141416] flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-110">
                        <ArrowUpRight size={15} />
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </section>

            {/* 高频场景模板（提供顺滑下滑纵深以触发底部悬浮快捷输入框） */}
            <section className="mt-10">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-[16px] font-semibold text-[var(--foreground)]">高频场景模板</h2>
                <button
                  type="button"
                  onClick={() => navigate('/gallery')}
                  className="text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] inline-flex items-center gap-1 cursor-pointer"
                >
                  <span>逛逛作品库</span>
                  <ArrowRight size={14} />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {SCENARIO_TEMPLATES.map((tpl) => (
                  <button
                    key={tpl.title}
                    type="button"
                    onClick={() => navigateToChat(tpl.prompt, tpl.mode)}
                    className="aos-glass-surface rounded-2xl p-4 text-left hover:-translate-y-0.5 hover:shadow-md transition-all cursor-pointer flex items-start gap-3"
                  >
                    <span className={cn('w-10 h-10 rounded-xl flex items-center justify-center shrink-0', tpl.tone)}>
                      <tpl.icon size={17} />
                    </span>
                    <div className="min-w-0">
                      <div className="text-[13px] font-semibold text-[var(--foreground)] truncate">{tpl.title}</div>
                      <div className="text-[11.5px] text-[var(--muted-foreground)] mt-1 leading-relaxed">{tpl.desc}</div>
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
          'aos-floating-bottom-bar rounded-full px-3 py-2 flex items-center gap-2',
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
          className="w-8 h-8 rounded-full bg-[var(--secondary)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] flex items-center justify-center shrink-0 cursor-pointer"
        >
          <Plus size={16} />
        </button>
        <input
          type="text"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="描述你想执行的任务..."
          className="flex-1 min-w-0 bg-transparent border-0 outline-none text-[13.5px] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] px-1"
        />
        <button
          type="button"
          onClick={handleSend}
          disabled={!inputValue.trim()}
          aria-label="发送"
          className="w-8 h-8 rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] flex items-center justify-center shrink-0 cursor-pointer disabled:opacity-40"
        >
          <ArrowUp size={15} />
        </button>
      </div>
    </motion.div>
  );
};
