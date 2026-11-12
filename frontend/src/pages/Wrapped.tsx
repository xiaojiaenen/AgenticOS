import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { motion } from 'motion/react';
import { ArrowLeft, CalendarDays, Clock, Flame, Share2, Sparkles, Trophy, Wrench } from 'lucide-react';
import { Button } from '../components/shadcn/button';
import { CountUp } from '../components/ui/CountUp';
import { cn } from '../lib/utils';
import { listItem, staggerContainer } from '../lib/motion';
import { getWrapped, getWrappedYears } from '../services/wrappedService';

function StatCard({ value, label, gradient, format }: {
  value: number;
  label: string;
  gradient: string;
  format?: (n: number) => string;
}) {
  return (
    <div className={cn('flex flex-col justify-between rounded-3xl p-6 text-white shadow-lg', gradient)}>
      <CountUp
        value={value}
        format={format ?? ((n) => n.toLocaleString('zh-CN'))}
        className="wrapped-display block text-4xl tabular-nums tracking-tight sm:text-5xl"
      />
      <div className="mt-3 text-sm font-medium opacity-90">{label}</div>
    </div>
  );
}

function BarList({ data, color }: { data: { name: string; value: number }[]; color: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <div className="flex flex-col gap-2.5">
      {data.map((d, i) => (
        <div key={d.name} className="flex items-center gap-3">
          <span className="w-5 text-sm font-bold tabular-nums opacity-50">{i + 1}</span>
          <span className="w-28 shrink-0 truncate text-sm font-medium">{d.name}</span>
          <div className="h-3 flex-1 overflow-hidden rounded-full bg-white/15">
            {/* 条宽从 0 生长：按名次错峰，长条先到（同期数时长），克制不抢数字 */}
            <motion.div
              className={cn('h-full rounded-full', color)}
              initial={{ width: 0 }}
              animate={{ width: `${(d.value / max) * 100}%` }}
              transition={{ duration: 0.7, delay: 0.2 + i * 0.08, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
          <span className="w-10 text-right text-sm font-semibold tabular-nums">{d.value}</span>
        </div>
      ))}
    </div>
  );
}

export function Wrapped() {
  const { year: yearParam } = useParams();
  const navigate = useNavigate();
  const yearsQ = useQuery({ queryKey: ['wrapped', 'years'], queryFn: getWrappedYears });
  const fallbackYear = yearsQ.data?.years[0] ?? yearsQ.data?.current_year ?? new Date().getFullYear();
  const year = yearParam ? Number(yearParam) : fallbackYear;
  const q = useQuery({ queryKey: ['wrapped', year], queryFn: () => getWrapped(year), enabled: !!year });
  const d = q.data;

  const share = async () => {
    const url = `${window.location.origin}/wrapped/${year}`;
    try { await navigator.clipboard.writeText(url); toast.success('报告链接已复制，快去分享吧！'); }
    catch { toast.error('复制失败，请手动复制地址栏链接'); }
  };

  return (
    <div className="min-h-screen bg-[#0a0a12] text-white">
      <div className="mx-auto max-w-3xl px-4 py-8">
        <div className="mb-6 flex items-center justify-between">
          <button type="button" onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-white">
            <ArrowLeft size={16} /> 返回
          </button>
          <div className="flex items-center gap-2">
            {yearsQ.data && yearsQ.data.years.length > 0 && (
              <select value={year} onChange={(e) => navigate(`/wrapped/${e.target.value}`)}
                className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm outline-none">
                {yearsQ.data.years.map((y) => <option key={y} value={y} className="bg-[#0a0a12]">{y}</option>)}
              </select>
            )}
            <Button size="sm" variant="outline" className="gap-1.5 border-white/20 bg-white/5 text-white hover:bg-white/10" onClick={share}>
              <Share2 size={14} /> 分享
            </Button>
          </div>
        </div>

        {q.isLoading ? (
          <div className="py-24 text-center text-white/50">正在生成你的年度报告…</div>
        ) : !d || !d.has_data ? (
          <div className="flex flex-col items-center gap-4 py-24 text-center">
            <Sparkles size={40} className="text-white/30" />
            <p className="text-lg font-semibold">{year} 年还没有足够的足迹</p>
            <p className="max-w-sm text-sm text-white/50">多和 AI 聊几句、做几个 PPT 或网站，明年这时就会有一份属于你的精彩报告。</p>
            <Button className="mt-2" onClick={() => navigate('/chat')}>开始对话</Button>
          </div>
        ) : (
          // 数据到达才挂载 → stagger 编排按「Hero → 大数字 → 时段 → 偏好 →
          // 工具 → 结语」依次入场；staggerContainer 全局上限防长列表拖沓
          <motion.div className="flex flex-col gap-5" variants={staggerContainer} initial="hidden" animate="show">
            {/* Hero */}
            <motion.div variants={listItem} className="wrapped-bg-hero relative overflow-hidden rounded-3xl p-8 shadow-2xl">
              <div className="text-sm font-medium uppercase tracking-[0.2em] opacity-80">{d.year} Wrapped</div>
              <h1 className="wrapped-display wrapped-art mt-3 text-3xl leading-tight sm:text-4xl">{d.user_name}，<br />这是你的 {d.year}。</h1>
              <div className="wrapped-display mt-5 inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-lg backdrop-blur">
                <Trophy size={20} /> 年度称号 · {d.persona}
              </div>
            </motion.div>

            {/* 大数字 */}
            <motion.div variants={listItem} className="grid grid-cols-2 gap-4">
              <StatCard value={d.total_runs} label="次对话" gradient="bg-gradient-to-br from-sky-500 to-blue-600" />
              <StatCard value={d.active_days} label="天活跃" gradient="bg-gradient-to-br from-emerald-500 to-teal-600" />
              <StatCard value={d.total_tokens} label="Token 往来" gradient="bg-gradient-to-br from-amber-500 to-orange-600" />
              <StatCard value={d.longest_streak} label="天连续打卡" gradient="bg-gradient-to-br from-rose-500 to-pink-600" />
            </motion.div>

            {/* 时段 */}
            <motion.div variants={listItem} className="grid grid-cols-2 gap-4">
              <div className="rounded-3xl bg-white/5 p-6">
                <Clock size={22} className="text-indigo-300" />
                <div className="mt-3 text-2xl font-bold">{d.busiest_hour != null ? `${d.busiest_hour}:00` : '—'}</div>
                <div className="mt-1 text-sm text-white/50">你最活跃的时刻</div>
              </div>
              <div className="rounded-3xl bg-white/5 p-6">
                <CalendarDays size={22} className="text-fuchsia-300" />
                <div className="mt-3 text-2xl font-bold">{d.busiest_weekday ?? '—'}</div>
                <div className="mt-1 text-sm text-white/50">你最常在的日子</div>
              </div>
            </motion.div>

            {/* 常用功能 */}
            {d.mode_distribution.length > 0 && (
              <motion.div variants={listItem} className="rounded-3xl bg-gradient-to-br from-violet-600/30 to-indigo-600/20 p-6">
                <div className="mb-4 flex items-center gap-2 text-lg font-bold"><Sparkles size={20} /> 你的功能偏好</div>
                <BarList data={d.mode_distribution} color="bg-gradient-to-r from-fuchsia-400 to-indigo-400" />
              </motion.div>
            )}

            {/* 常用工具 */}
            {d.top_tools.length > 0 && (
              <motion.div variants={listItem} className="rounded-3xl bg-white/5 p-6">
                <div className="mb-4 flex items-center gap-2 text-lg font-bold"><Wrench size={20} /> 你最常用的工具</div>
                <BarList data={d.top_tools.map((t) => ({ name: t.name, value: t.count }))} color="bg-gradient-to-r from-emerald-400 to-teal-400" />
              </motion.div>
            )}

            {/* 结语 */}
            <motion.div variants={listItem} className="wrapped-bg-footer rounded-3xl p-8 text-center shadow-xl">
              <Flame size={28} className="mx-auto text-amber-300" />
              <p className="wrapped-display wrapped-art-warm mt-3 text-lg">
                {d.first_activity} 到 {d.last_activity}，{d.conversation_count} 场对话，{d.total_hours} 小时并肩。
              </p>
              <p className="mt-2 text-sm opacity-80">新的一年，继续一起把想法变成现实。</p>
              <Button className="mt-5 bg-white text-indigo-700 hover:bg-white/90" onClick={share}>
                <Share2 size={16} /> 分享我的 {d.year}
              </Button>
            </motion.div>
          </motion.div>
        )}
      </div>
    </div>
  );
}

export default Wrapped;
