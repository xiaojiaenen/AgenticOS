import React from 'react';
import { motion } from 'motion/react';
import { Download, FileText, LayoutDashboard, RefreshCcw, X } from 'lucide-react';
import { MotionValue } from 'motion/react';
import { PptDeck, PptSlide, PptThemeName } from '../../types';
import { cn } from '../../lib/utils';
import { PPT_PAGE_CLASS } from './pptDeck';

type PptArtifactPanelProps = {
  deck: PptDeck;
  onClose: () => void;
  borderColor: MotionValue<string>;
};

type Theme = {
  page: string;
  dark: string;
  muted: string;
  accent: string;
  accentSoft: string;
  accentText: string;
  accentHex: string;
  text: string;
  panel: string;
};

const themes: Record<PptThemeName, Theme> = {
  executive: {
    page: 'bg-[#f6f8fb]',
    dark: 'bg-[#121826]',
    muted: 'text-slate-500',
    accent: 'bg-[#1f6feb]',
    accentSoft: 'bg-[#dbeafe]',
    accentText: 'text-[#1f6feb]',
    accentHex: '#1f6feb',
    text: 'text-slate-950',
    panel: 'bg-white',
  },
  product: {
    page: 'bg-[#f7fbf9]',
    dark: 'bg-[#0f2f2a]',
    muted: 'text-slate-500',
    accent: 'bg-[#14b8a6]',
    accentSoft: 'bg-[#ccfbf1]',
    accentText: 'text-[#0f766e]',
    accentHex: '#14b8a6',
    text: 'text-slate-950',
    panel: 'bg-white',
  },
  minimal: {
    page: 'bg-[#fafafa]',
    dark: 'bg-[#18181b]',
    muted: 'text-zinc-500',
    accent: 'bg-[#27272a]',
    accentSoft: 'bg-[#e4e4e7]',
    accentText: 'text-[#27272a]',
    accentHex: '#27272a',
    text: 'text-zinc-950',
    panel: 'bg-white',
  },
};

const safeTheme = (name?: PptThemeName) => themes[name || 'executive'] || themes.executive;

const Page = ({ children, theme, dark = false }: { children: React.ReactNode; theme: Theme; dark?: boolean }) => (
  <section
    className={cn(
      PPT_PAGE_CLASS,
      'relative h-[562.5px] w-[1000px] overflow-hidden rounded-[20px] border border-black/5 font-sans shadow-[0_24px_70px_rgba(15,23,42,0.12)]',
      dark ? `${theme.dark} text-white` : `${theme.page} ${theme.text}`,
    )}
  >
    <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full bg-white/50" />
    <div className={cn('absolute -bottom-24 left-16 h-64 w-64 rounded-full opacity-45', dark ? 'bg-white/10' : theme.accentSoft)} />
    <div className="absolute inset-0 [background-image:linear-gradient(90deg,rgba(15,23,42,0.04)_1px,transparent_1px),linear-gradient(0deg,rgba(15,23,42,0.04)_1px,transparent_1px)] [background-size:48px_48px] opacity-45" />
    {children}
  </section>
);

const SlideNumber = ({ index, total, dark = false }: { index: number; total: number; dark?: boolean }) => (
  <div className={cn('absolute bottom-8 right-10 text-[12px] font-bold tracking-[0.18em]', dark ? 'text-white/40' : 'text-slate-400')}>
    {String(index + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}
  </div>
);

function CoverSlide({ slide, theme, index, total, deck }: { slide: PptSlide; theme: Theme; index: number; total: number; deck: PptDeck }) {
  return (
    <Page theme={theme} dark>
      <div className="absolute inset-0 opacity-30 [background-image:linear-gradient(120deg,transparent_0%,transparent_54%,rgba(255,255,255,0.2)_54%,rgba(255,255,255,0.2)_100%)]" />
      <div className="absolute -right-20 top-16 h-80 w-80 rounded-full border-[52px] border-white/10" />
      <div className="absolute right-24 bottom-40 h-24 w-56 rounded-full bg-white/10 blur-sm" />
      <div className="absolute left-14 top-12 flex items-center gap-3 text-[13px] font-black uppercase tracking-[0.24em] text-white/60">
        <span className={cn('h-2 w-10 rounded-full', theme.accent)} />
        {slide.eyebrow || deck.author || 'AgenticOS'}
      </div>
      <div className="absolute left-14 top-40 w-[650px]">
        <h1 className="text-[62px] font-black leading-[0.96] tracking-[-0.02em]">{slide.title}</h1>
        <p className="mt-7 max-w-[540px] text-[22px] font-medium leading-[1.35] text-white/68">{slide.subtitle || deck.subtitle}</p>
      </div>
      <div className="absolute bottom-16 left-14 h-1.5 w-28 rounded-full bg-white/20" />
      <div className={cn('absolute bottom-16 right-14 h-40 w-40 rounded-[34px]', theme.accent)} />
      <SlideNumber index={index} total={total} dark />
    </Page>
  );
}

function ChartSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  const chart = slide.chart && slide.chart.labels.length && slide.chart.values.length
    ? slide.chart
    : { type: 'bar', labels: ['入口', '转化', '留存', '复购'], values: [32, 58, 74, 86], unit: '%' };
  const max = Math.max(...chart.values, 1);
  const linePoints = chart.values.map((value, pointIndex) => {
    const x = 18 + pointIndex * (260 / Math.max(chart.values.length - 1, 1));
    const y = 180 - (value / max) * 145;
    return `${x},${y}`;
  }).join(' ');

  return (
    <Page theme={theme}>
      <div className="absolute left-12 top-10 right-12 flex items-start justify-between">
        <div>
          <div className={cn('mb-3 text-[13px] font-black uppercase tracking-[0.2em]', theme.accentText)}>Data view</div>
          <h2 className="max-w-[620px] text-[42px] font-black leading-[1.04] tracking-[-0.02em]">{slide.title}</h2>
          {slide.subtitle && <p className={cn('mt-4 max-w-[520px] text-[16px] leading-[1.42]', theme.muted)}>{slide.subtitle}</p>}
        </div>
        <div className={cn('rounded-full px-4 py-2 text-[12px] font-black uppercase tracking-[0.18em]', theme.accentSoft, theme.accentText)}>
          {chart.type || 'bar'} chart
        </div>
      </div>

      <div className="absolute left-12 right-12 top-[184px] grid grid-cols-[1fr_300px] gap-7">
        <div className="h-[300px] rounded-[32px] bg-white p-7 shadow-[0_22px_56px_rgba(15,23,42,0.1)]">
          {chart.type === 'line' ? (
            <svg viewBox="0 0 300 200" className="h-full w-full overflow-visible">
              <polyline points={linePoints} fill="none" stroke={theme.accentHex} strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
              {chart.values.map((value, pointIndex) => {
                const x = 18 + pointIndex * (260 / Math.max(chart.values.length - 1, 1));
                const y = 180 - (value / max) * 145;
                return <circle key={pointIndex} cx={x} cy={y} r="7" fill={theme.accentHex} />;
              })}
            </svg>
          ) : (
            <div className="flex h-full items-end gap-5">
              {chart.values.map((value, barIndex) => (
                <div key={barIndex} className="flex flex-1 flex-col items-center gap-3">
                  <div className={cn('flex w-full items-start justify-center rounded-t-[18px]', theme.accent)} style={{ height: `${Math.max(18, (value / max) * 210)}px` }}>
                    <span className="mt-3 text-[15px] font-black text-white">{value}{chart.unit}</span>
                  </div>
                  <div className="text-center text-[12px] font-bold text-slate-500">{chart.labels[barIndex]}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className={cn('h-[300px] rounded-[32px] p-7 text-white shadow-[0_22px_56px_rgba(15,23,42,0.16)]', theme.dark)}>
          <div className="text-[13px] font-black uppercase tracking-[0.18em] text-white/45">Insight</div>
          <div className="mt-7 text-[52px] font-black leading-none tracking-[-0.04em]">
            {Math.max(...chart.values)}{chart.unit}
          </div>
          <p className="mt-6 text-[18px] font-bold leading-[1.32] text-white/78">
            {slide.body || '关键指标呈现上升趋势，适合作为方案价值或阶段进展的主证据。'}
          </p>
        </div>
      </div>
      <SlideNumber index={index} total={total} />
    </Page>
  );
}

function SectionSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  return (
    <Page theme={theme} dark>
      <div className={cn('absolute left-0 top-0 h-full w-3', theme.accent)} />
      <div className="absolute left-20 top-28 w-[760px]">
        <div className="mb-7 text-[14px] font-black uppercase tracking-[0.24em] text-white/45">{slide.eyebrow || 'Section'}</div>
        <h2 className="text-[56px] font-black leading-[1.02] tracking-[-0.02em]">{slide.title}</h2>
        {slide.subtitle && <p className="mt-6 max-w-[620px] text-[22px] leading-[1.35] text-white/64">{slide.subtitle}</p>}
      </div>
      <SlideNumber index={index} total={total} dark />
    </Page>
  );
}

function BulletsSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  const items = slide.items?.length ? slide.items : [slide.body || '补充要点'];
  return (
    <Page theme={theme}>
      <div className="absolute left-12 top-11 w-[420px]">
        <div className={cn('mb-4 h-2 w-16 rounded-full', theme.accent)} />
        <h2 className="text-[42px] font-black leading-[1.04] tracking-[-0.02em]">{slide.title}</h2>
        {slide.subtitle && <p className={cn('mt-4 text-[17px] leading-[1.45]', theme.muted)}>{slide.subtitle}</p>}
      </div>
      <div className="absolute right-12 top-32 grid w-[460px] gap-4">
        {items.slice(0, 5).map((item, itemIndex) => (
          <div key={itemIndex} className={cn('flex gap-4 rounded-[22px] px-5 py-4 shadow-[0_18px_40px_rgba(15,23,42,0.08)]', theme.panel)}>
            <div className={cn('flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-[13px] font-black text-white', theme.accent)}>
              {itemIndex + 1}
            </div>
            <p className="text-[20px] font-bold leading-[1.28] text-slate-800">{item}</p>
          </div>
        ))}
      </div>
      <SlideNumber index={index} total={total} />
    </Page>
  );
}

function ComparisonSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  const columns = [
    { title: slide.leftTitle || 'Before', items: slide.leftItems || [] },
    { title: slide.rightTitle || 'After', items: slide.rightItems || [] },
  ];
  return (
    <Page theme={theme}>
      <div className="absolute left-12 top-10 right-12 flex items-end justify-between">
        <h2 className="w-[580px] text-[40px] font-black leading-[1.04] tracking-[-0.02em]">{slide.title}</h2>
        <div className={cn('h-3 w-28 rounded-full', theme.accent)} />
      </div>
      <div className="absolute left-12 right-12 top-[146px] grid grid-cols-2 gap-6">
        {columns.map((column, columnIndex) => (
          <div key={columnIndex} className={cn('h-[330px] rounded-[28px] p-8 shadow-[0_18px_50px_rgba(15,23,42,0.08)]', columnIndex === 1 ? `${theme.dark} text-white` : theme.panel)}>
            <div className={cn('mb-6 text-[15px] font-black uppercase tracking-[0.18em]', columnIndex === 1 ? 'text-white/55' : theme.muted)}>{column.title}</div>
            <div className="space-y-4">
              {(column.items.length ? column.items : ['补充对比项']).slice(0, 5).map((item, itemIndex) => (
                <div key={itemIndex} className="flex gap-3 text-[18px] font-bold leading-[1.28]">
                  <span className={cn('mt-2 h-2.5 w-2.5 flex-shrink-0 rounded-full', columnIndex === 1 ? theme.accent : theme.accentSoft)} />
                  {item}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <SlideNumber index={index} total={total} />
    </Page>
  );
}

function StatsSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  const stats = slide.stats?.length ? slide.stats : [{ value: '3x', label: '效率提升' }, { value: '80%', label: '重复工作减少' }, { value: '24/7', label: '持续响应' }];
  return (
    <Page theme={theme}>
      <div className="absolute left-12 top-12 right-12">
        <h2 className="max-w-[650px] text-[42px] font-black leading-[1.04] tracking-[-0.02em]">{slide.title}</h2>
        {slide.subtitle && <p className={cn('mt-4 text-[17px]', theme.muted)}>{slide.subtitle}</p>}
      </div>
      <div className="absolute bottom-[88px] left-12 right-12 grid grid-cols-3 gap-5">
        {stats.slice(0, 3).map((stat, statIndex) => (
          <div key={statIndex} className={cn('h-[210px] rounded-[30px] p-7 shadow-[0_18px_50px_rgba(15,23,42,0.08)]', statIndex === 0 ? `${theme.dark} text-white` : theme.panel)}>
            <div className={cn('text-[60px] font-black leading-none tracking-[-0.04em]', statIndex === 0 ? 'text-white' : 'text-slate-950')}>{stat.value}</div>
            <div className={cn('mt-7 text-[20px] font-black leading-[1.15]', statIndex === 0 ? 'text-white/82' : 'text-slate-800')}>{stat.label}</div>
            {stat.caption && <div className={cn('mt-3 text-[13px] leading-[1.35]', statIndex === 0 ? 'text-white/48' : theme.muted)}>{stat.caption}</div>}
          </div>
        ))}
      </div>
      <SlideNumber index={index} total={total} />
    </Page>
  );
}

function TimelineSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  const timeline = slide.timeline?.length ? slide.timeline : [{ label: '01', title: '定义目标' }, { label: '02', title: '生成内容' }, { label: '03', title: '导出文件' }];
  return (
    <Page theme={theme}>
      <div className="absolute left-12 top-10">
        <h2 className="max-w-[700px] text-[42px] font-black leading-[1.04] tracking-[-0.02em]">{slide.title}</h2>
      </div>
      <div className="absolute left-14 right-14 top-[250px] h-1 rounded-full bg-slate-200" />
      <div className="absolute left-14 right-14 top-[178px] grid grid-cols-5 gap-4">
        {timeline.slice(0, 5).map((item, itemIndex) => (
          <div key={itemIndex} className="relative">
            <div className={cn('mb-5 flex h-12 w-12 items-center justify-center rounded-full text-[13px] font-black text-white', theme.accent)}>{item.label || `0${itemIndex + 1}`}</div>
            <h3 className="text-[19px] font-black leading-[1.12] text-slate-900">{item.title}</h3>
            {item.body && <p className={cn('mt-3 text-[13px] leading-[1.35]', theme.muted)}>{item.body}</p>}
          </div>
        ))}
      </div>
      <SlideNumber index={index} total={total} />
    </Page>
  );
}

function QuoteSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  return (
    <Page theme={theme} dark>
      <div className={cn('absolute left-14 top-14 h-3 w-24 rounded-full', theme.accent)} />
      <div className="absolute left-14 top-[138px] w-[760px]">
        <div className="text-[82px] font-black leading-none text-white/16">“</div>
        <div className="text-[38px] font-black leading-[1.16] tracking-[-0.02em]">{slide.quote || slide.title}</div>
        {slide.author && <div className="mt-8 text-[16px] font-black uppercase tracking-[0.2em] text-white/45">{slide.author}</div>}
      </div>
      <SlideNumber index={index} total={total} dark />
    </Page>
  );
}

function ImageTextSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  return (
    <Page theme={theme}>
      <div className={cn('absolute left-0 top-0 h-full w-[390px]', theme.dark)} />
      <div className="absolute left-[176px] top-[92px] h-[380px] w-[380px] overflow-hidden rounded-[34px] bg-white/12 shadow-[0_20px_60px_rgba(15,23,42,0.2)]">
        {slide.imageUrl ? <img src={slide.imageUrl} alt="" className="h-full w-full object-cover" /> : <div className={cn('h-full w-full', theme.accent)} />}
      </div>
      <div className="absolute right-14 top-[94px] w-[450px]">
        <h2 className="text-[40px] font-black leading-[1.05] tracking-[-0.02em]">{slide.title}</h2>
        <p className={cn('mt-5 text-[19px] font-medium leading-[1.45]', theme.muted)}>{slide.body || slide.subtitle}</p>
        <div className="mt-8 space-y-3">
          {(slide.items || []).slice(0, 3).map((item, itemIndex) => (
            <div key={itemIndex} className="flex gap-3 text-[17px] font-bold text-slate-800">
              <span className={cn('mt-2 h-2.5 w-2.5 rounded-full', theme.accent)} />
              {item}
            </div>
          ))}
        </div>
      </div>
      <SlideNumber index={index} total={total} />
    </Page>
  );
}

function ClosingSlide({ slide, theme, index, total }: { slide: PptSlide; theme: Theme; index: number; total: number }) {
  return (
    <Page theme={theme} dark>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <div className={cn('mb-9 h-3 w-28 rounded-full', theme.accent)} />
        <h2 className="max-w-[760px] text-[56px] font-black leading-[1.02] tracking-[-0.02em]">{slide.title}</h2>
        {slide.subtitle && <p className="mt-6 max-w-[620px] text-[21px] leading-[1.38] text-white/64">{slide.subtitle}</p>}
      </div>
      <SlideNumber index={index} total={total} dark />
    </Page>
  );
}

function renderSlide(slide: PptSlide, deck: PptDeck, index: number) {
  const theme = safeTheme(deck.theme);
  const total = deck.slides.length;
  if (slide.type === 'cover') return <CoverSlide slide={slide} deck={deck} theme={theme} index={index} total={total} />;
  if (slide.type === 'section') return <SectionSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'comparison') return <ComparisonSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'stats') return <StatsSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'timeline') return <TimelineSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'chart') return <ChartSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'quote') return <QuoteSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'imageText') return <ImageTextSlide slide={slide} theme={theme} index={index} total={total} />;
  if (slide.type === 'closing') return <ClosingSlide slide={slide} theme={theme} index={index} total={total} />;
  return <BulletsSlide slide={slide} theme={theme} index={index} total={total} />;
}

export const PptArtifactPanel: React.FC<PptArtifactPanelProps> = ({ deck, onClose, borderColor }) => {
  const [isExporting, setIsExporting] = React.useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      await document.fonts?.ready;
      const { downloadHtmlToPpt } = await import('html-to-pptx');
      await downloadHtmlToPpt(PPT_PAGE_CLASS, deck.title || 'AgenticOS-PPT');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <motion.aside
      initial={{ width: 0, opacity: 0 }}
      animate={{ width: '60%', opacity: 1 }}
      exit={{ width: 0, opacity: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="relative z-20 flex h-full flex-col overflow-hidden border-l bg-white/42 ring-1 ring-white/70 backdrop-blur-3xl"
      style={{ borderColor }}
    >
      <div className="z-10 flex h-14 flex-shrink-0 items-center justify-between border-b border-slate-200/80 bg-white/82 px-6 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/20 bg-zinc-900 text-white shadow-lg shadow-zinc-900/20">
            <LayoutDashboard size={18} />
          </div>
          <div>
            <h2 className="text-sm font-bold leading-none text-slate-800">{deck.title}</h2>
            <div className="mt-1 flex items-center gap-1.5">
              <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                {deck.slides.length} slides · editable pptx
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleExport}
            disabled={isExporting}
            className="inline-flex items-center gap-2 rounded-xl bg-zinc-900 px-3 py-2 text-xs font-bold text-white transition-colors hover:bg-zinc-800 disabled:opacity-60"
            title="导出 PPTX"
          >
            {isExporting ? <RefreshCcw size={14} className="animate-spin" /> : <Download size={14} />}
            导出
          </button>
          <button
            onClick={() => navigator.clipboard.writeText(JSON.stringify(deck, null, 2))}
            className="rounded-xl p-2 text-slate-400 transition-all hover:bg-slate-100 hover:text-zinc-600"
            title="复制 deck JSON"
          >
            <FileText size={16} />
          </button>
          <div className="mx-2 h-4 w-px bg-slate-200" />
          <button onClick={onClose} className="rounded-xl p-2 text-slate-400 transition-all hover:bg-rose-50 hover:text-rose-500">
            <X size={18} />
          </button>
        </div>
      </div>
      <div className="z-10 flex-1 overflow-auto p-6">
        <div className="mx-auto flex w-[720px] flex-col gap-8 pb-8">
          {deck.slides.map((slide, index) => (
            <motion.div
              key={`${slide.title}-${index}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(index * 0.06, 0.4) }}
              className="origin-top-left scale-[0.72]"
              style={{ height: 405 }}
            >
              {renderSlide(slide, deck, index)}
            </motion.div>
          ))}
        </div>
      </div>
    </motion.aside>
  );
};
