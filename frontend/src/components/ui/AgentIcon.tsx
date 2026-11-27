/**
 * 智能体图标：全站统一入口（avatar key → kubai 插画图标 + 色调）。
 *
 * avatar 字段全链路已存在（model/schema/API/前端 payload），但此前渲染层
 * 各按 mode/slug 硬编码映射，导致同一智能体在不同页面图标/色调不一致。
 * 本组件是唯一映射源：所有展示智能体图标的地方都用它，保证一致。
 *
 * 用静态导入（非 DynamicIcon）避免异步加载闪烁；白名单外 avatar 回退到 Sparkles。
 */
import React from 'react';
import {
  Sparkles, Presentation, Globe, Table, Mail, Bot, Database, Brain,
  Code, ChartBar, ChartLine, Cpu, Lightbulb, Wrench, Shield, Rocket, Zap,
  Palette, BookOpen,
} from 'kubai-icons-react';
import { cn } from '../../lib/utils';

type IconComp = React.ComponentType<{ size?: number; className?: string; color?: string }>;

/** 可选图标清单（新建智能体选择器用，带中文名便于搜索）。 */
export const AGENT_ICON_CHOICES: { key: string; label: string; Icon: IconComp; tone: string }[] = [
  { key: 'sparkles', label: '通用', Icon: Sparkles, tone: 'aos-tone-violet' },
  { key: 'presentation', label: '演示文稿', Icon: Presentation, tone: 'aos-tone-amber' },
  { key: 'globe', label: '网站', Icon: Globe, tone: 'aos-tone-sky' },
  { key: 'table', label: '表格', Icon: Table, tone: 'aos-tone-emerald' },
  { key: 'mail', label: '邮件', Icon: Mail, tone: 'aos-tone-violet' },
  { key: 'bot', label: '机器人', Icon: Bot, tone: 'aos-tone-slate' },
  { key: 'database', label: '数据', Icon: Database, tone: 'aos-tone-sky' },
  { key: 'brain', label: '智能', Icon: Brain, tone: 'aos-tone-violet' },
  { key: 'code', label: '代码', Icon: Code, tone: 'aos-tone-slate' },
  { key: 'chart-bar', label: '图表', Icon: ChartBar, tone: 'aos-tone-emerald' },
  { key: 'chart-line', label: '趋势', Icon: ChartLine, tone: 'aos-tone-emerald' },
  { key: 'cpu', label: '算力', Icon: Cpu, tone: 'aos-tone-sky' },
  { key: 'lightbulb', label: '灵感', Icon: Lightbulb, tone: 'aos-tone-amber' },
  { key: 'wrench', label: '工具', Icon: Wrench, tone: 'aos-tone-slate' },
  { key: 'shield', label: '安全', Icon: Shield, tone: 'aos-tone-emerald' },
  { key: 'rocket', label: '发布', Icon: Rocket, tone: 'aos-tone-amber' },
  { key: 'zap', label: '效率', Icon: Zap, tone: 'aos-tone-amber' },
  { key: 'palette', label: '设计', Icon: Palette, tone: 'aos-tone-violet' },
  { key: 'book', label: '知识', Icon: BookOpen, tone: 'aos-tone-sky' },
];

const BY_KEY = new Map(AGENT_ICON_CHOICES.map((c) => [c.key, c]));

/** 按 avatar key 取图标与色调；未知 key 回退到通用。 */
export function getAgentIcon(avatar?: string | null): { Icon: IconComp; tone: string } {
  const key = (avatar || '').toLowerCase();
  return BY_KEY.get(key) ?? BY_KEY.get('sparkles')!;
}

/** 智能体图标组件。 */
export const AgentIcon: React.FC<{
  avatar?: string | null;
  size?: number | string;
  className?: string;
}> = ({ avatar, size = 16, className }) => {
  const { Icon } = getAgentIcon(avatar);
  return <Icon size={size} className={cn('shrink-0', className)} />;
};
