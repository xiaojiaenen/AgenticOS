import { PptDeck, PptSlide } from '../../types';

export const PPT_PAGE_CLASS = 'agenticos-ppt-page';

export const DEFAULT_DECK: PptDeck = {
  title: 'AgenticOS 演示文稿',
  subtitle: '结构化内容、统一模板、可编辑导出',
  theme: 'executive',
  slides: [
    {
      type: 'cover',
      eyebrow: 'AgenticOS',
      title: '演示文稿生成方案',
      subtitle: '从需求到可编辑 PPTX 的一体化工作流',
    },
    {
      type: 'bullets',
      title: '核心能力',
      items: ['结构化生成 slide deck', '统一设计模板确保视觉质量', '浏览器端导出可编辑 PPTX'],
    },
    {
      type: 'closing',
      title: '下一步',
      subtitle: '继续细化模板、企业主题和导出 QA。',
    },
  ],
};

const allowedTypes = new Set([
  'cover',
  'section',
  'bullets',
  'imageText',
  'comparison',
  'timeline',
  'stats',
  'chart',
  'quote',
  'closing',
]);

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => asString(item)).filter(Boolean).slice(0, 7);
}

function normalizeSlide(value: any, index: number): PptSlide {
  const rawType = asString(value?.type, index === 0 ? 'cover' : 'bullets');
  const type = allowedTypes.has(rawType) ? rawType as PptSlide['type'] : 'bullets';
  return {
    type,
    eyebrow: asString(value?.eyebrow),
    title: asString(value?.title, `第 ${index + 1} 页`),
    subtitle: asString(value?.subtitle),
    body: asString(value?.body),
    items: asStringArray(value?.items),
    leftTitle: asString(value?.leftTitle),
    rightTitle: asString(value?.rightTitle),
    leftItems: asStringArray(value?.leftItems),
    rightItems: asStringArray(value?.rightItems),
    imageUrl: asString(value?.imageUrl),
    quote: asString(value?.quote),
    author: asString(value?.author),
    chart: value?.chart && Array.isArray(value.chart.labels) && Array.isArray(value.chart.values)
      ? {
          type: ['bar', 'line', 'donut'].includes(value.chart.type) ? value.chart.type : 'bar',
          labels: asStringArray(value.chart.labels).slice(0, 6),
          values: value.chart.values.slice(0, 6).map((item: unknown) => Number(item)).filter(Number.isFinite),
          unit: asString(value.chart.unit),
        }
      : undefined,
    stats: Array.isArray(value?.stats)
      ? value.stats.slice(0, 4).map((item: any) => ({
          label: asString(item?.label),
          value: asString(item?.value),
          caption: asString(item?.caption),
        })).filter((item: {label: string; value: string}) => item.label || item.value)
      : [],
    timeline: Array.isArray(value?.timeline)
      ? value.timeline.slice(0, 5).map((item: any) => ({
          label: asString(item?.label),
          title: asString(item?.title),
          body: asString(item?.body),
        })).filter((item: {label: string; title: string}) => item.label || item.title)
      : [],
  };
}

export function parsePptDeck(code: string): PptDeck | null {
  try {
    const parsed = JSON.parse(code);
    const slides = Array.isArray(parsed?.slides)
      ? parsed.slides.slice(0, 16).map(normalizeSlide)
      : [];
    if (slides.length === 0) return null;

    return {
      title: asString(parsed?.title, slides[0]?.title || DEFAULT_DECK.title),
      subtitle: asString(parsed?.subtitle),
      author: asString(parsed?.author),
      theme: ['executive', 'product', 'minimal'].includes(parsed?.theme) ? parsed.theme : 'executive',
      slides,
    };
  } catch {
    return null;
  }
}

export function extractPptDeckFromText(text: string): {code: string; deck: PptDeck} | null {
  const match = /```pptdeck\n([\s\S]*?)\n```/.exec(text) || /```json\n([\s\S]*?"slides"[\s\S]*?)\n```/.exec(text);
  if (!match) return null;
  const code = match[1].trim();
  const deck = parsePptDeck(code);
  return deck ? {code, deck} : null;
}

export function stripPptDeckFromText(text: string): string {
  const withoutCompleteBlocks = text
    .replace(/```pptdeck\n[\s\S]*?\n```/g, '')
    .replace(/```json\n(?=[\s\S]*?"slides"[\s\S]*?```)[\s\S]*?\n```/g, '');
  const partialPptIndex = withoutCompleteBlocks.indexOf('```pptdeck');
  const withoutPartialPpt = partialPptIndex >= 0
    ? withoutCompleteBlocks.slice(0, partialPptIndex)
    : withoutCompleteBlocks;
  return withoutPartialPpt.replace(/\n{3,}/g, '\n\n').trim();
}
