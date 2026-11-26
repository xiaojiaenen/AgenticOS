import React from 'react';
import { motion } from 'motion/react';
import { ArrowUpRight } from 'lucide-react';
import { RandomMascot } from '../ui/RandomMascot';
import { CodeIcon, RefreshIcon, MascotCool } from '../ui/AnimatedIcons';
import { cn } from '../../lib/utils';

interface ChatSuggestionsProps {
  onSelect: (text: string) => void;
}

export const ChatSuggestions: React.FC<ChatSuggestionsProps> = ({ onSelect }) => {
  const suggestions = [
    {
      icon: <CodeIcon size={18} />,
      tone: 'aos-tone-sky',
      tag: '写作',
      title: '创意写作',
      desc: '帮我写一个关于时空旅行的小说开头',
      text: '请帮我写一个关于时空旅行的小说开头，主角是一个在图书馆发现秘密通道的学生。',
    },
    {
      icon: <CodeIcon size={18} />,
      tone: 'aos-tone-violet',
      tag: '工程',
      title: '编写代码',
      desc: '如何用 React 和 Tailwind 实现一个登录页面？',
      text: '请用 React 和 Tailwind CSS 编写一个美观、响应式的登录页面组件代码，并提供 HTML 预览。',
    },
    {
      icon: <RefreshIcon size={18} />,
      tone: 'aos-tone-emerald',
      tag: '规划',
      title: '数据分析',
      desc: '帮我制定一个下周的健身与饮食方案',
      text: '请根据我的情况，制定一个为期一周的科学健身计划和健康的饮食建议，目标是增肌减脂。',
    },
    {
      icon: <MascotCool size={18} />,
      tone: 'aos-tone-amber',
      tag: '推荐',
      title: '生活建议',
      desc: '推荐几本能提升幸福感的心理学书籍',
      text: '请推荐 5 本能提升生活幸福感、对抗焦虑的心理学书籍，并简述推荐理由。',
    },
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center px-4 py-8">
      <div className="relative mb-7 flex items-center justify-center">
        {/* Subtle orbital SVG halo */}
        <svg
          className="pointer-events-none absolute -inset-6 h-[168px] w-[168px] text-[var(--primary)]/25 aos-orbit-slow"
          viewBox="0 0 168 168"
          fill="none"
          aria-hidden="true"
        >
          <circle cx="84" cy="84" r="74" stroke="currentColor" strokeWidth="1" strokeDasharray="4 6" />
          <circle cx="84" cy="10" r="3.5" fill="currentColor" />
          <circle cx="152" cy="112" r="2.5" fill="currentColor" opacity="0.65" />
        </svg>
        <div className="relative z-10 flex h-[120px] w-[120px] items-center justify-center rounded-full bg-[var(--surface-1)]/60 shadow-lg backdrop-blur-xl ring-1 ring-[var(--border-subtle)]">
          <RandomMascot size={96} className="opacity-95" />
        </div>
        <motion.div
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
          className="aos-glass-surface absolute -right-12 -top-3 z-20 flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold text-[var(--foreground)]"
        >
          <span>Hello!</span>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="fill-amber-400 text-amber-400"
            aria-hidden="true"
          >
            <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
          </svg>
        </motion.div>
      </div>

      <h1 className="mb-2 text-2xl font-bold tracking-tight text-[var(--foreground)]">
        今天想聊些什么？
      </h1>
      <p className="mb-8 max-w-md text-center text-sm leading-relaxed text-[var(--muted-foreground)]">
        点击下方灵感卡片快速开启，或直接在输入框告诉我你的任务。
      </p>

      <div className="grid w-full max-w-2xl grid-cols-1 gap-3.5 text-left md:grid-cols-2">
        {suggestions.map((prompt, i) => (
          <motion.button
            key={prompt.title}
            type="button"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.06 + i * 0.06, duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            onClick={() => onSelect(prompt.text)}
            className={cn(
              'aos-glass-surface aos-sheen-hover group flex flex-col justify-between rounded-2xl p-4 text-left',
              'active:scale-[0.985] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[var(--ring-halo)] focus-visible:ring-[var(--ring)]',
            )}
          >
            <div className="mb-2 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className={cn('flex h-8 w-8 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105', prompt.tone)}>
                  {prompt.icon}
                </div>
                <span className="text-sm font-semibold text-[var(--foreground)]">
                  {prompt.title}
                </span>
              </div>
              <ArrowUpRight
                size={15}
                className="text-[var(--muted-foreground)] opacity-0 transition-all duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:opacity-100"
              />
            </div>
            <p className="line-clamp-1 text-xs leading-5 text-[var(--muted-foreground)]">
              {prompt.desc}
            </p>
          </motion.button>
        ))}
      </div>
    </div>
  );
};
