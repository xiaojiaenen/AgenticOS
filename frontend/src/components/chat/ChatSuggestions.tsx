import React from 'react';
import { motion } from 'motion/react';
import { RandomMascot } from '../ui/RandomMascot';
import { CodeIcon, RefreshIcon, MascotCool } from '../ui/AnimatedIcons';

interface ChatSuggestionsProps {
  onSelect: (text: string) => void;
}

export const ChatSuggestions: React.FC<ChatSuggestionsProps> = ({ onSelect }) => {
  const suggestions = [
    { icon: <CodeIcon size={20} className="text-blue-500" />, title: '创意写作', desc: '帮我写一个关于时空旅行的小说开头', text: '请帮我写一个关于时空旅行的小说开头，主角是一个在图书馆发现秘密通道的学生。' },
    { icon: <CodeIcon size={20} className="text-purple-500" />, title: '编写代码', desc: '如何用 React 和 Tailwind 实现一个登录页面？', text: '请用 React 和 Tailwind CSS 编写一个美观、响应式的登录页面组件代码，并提供 HTML 预览。' },
    { icon: <RefreshIcon size={20} className="text-green-500" />, title: '数据分析', desc: '帮我制定一个下周的健身与饮食方案', text: '请根据我的情况，制定一个为期一周的科学健身计划和健康的饮食建议，目标是增肌减脂。' },
    { icon: <MascotCool size={20} className="text-amber-500" />, title: '生活建议', desc: '推荐几本能提升幸福感的心理学书籍', text: '请推荐 5 本能提升生活幸福感、对抗焦虑的心理学书籍，并简述推荐理由。' }
  ];

  return (
    <div className="h-full flex flex-col items-center justify-center animate-in fade-in zoom-in duration-700">
      <div className="relative mb-8">
        <RandomMascot size={120} className="opacity-80" />
        <motion.div 
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
          className="absolute -top-6 -right-12 bg-white px-3 py-1 rounded-full shadow-sm border border-slate-100 text-xs font-bold text-sky-500 flex items-center gap-1.5"
        >
          <span>Hello!</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-yellow-400 fill-yellow-400"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/></svg>
        </motion.div>
      </div>
      <h2 className="text-2xl font-bold text-slate-800 mb-2">今天想聊些什么？</h2>
      <p className="text-slate-500 mb-8 max-w-sm text-center">你可以尝试点击下方的建议，或者直接在下方输入框告诉我你的想法。</p>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-2xl w-full px-4 text-left">
        {suggestions.map((prompt, i) => (
          <motion.button
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.1 }}
            onClick={() => onSelect(prompt.text)}
            className="p-4 bg-white/60 hover:bg-white border border-slate-200/60 rounded-2xl text-left transition-all hover:shadow-md hover:scale-[1.02] active:scale-[0.98] group"
          >
            <div className="flex items-center gap-3 mb-1">
              <div className="w-8 h-8 rounded-lg bg-slate-50 flex items-center justify-center group-hover:bg-white transition-colors">
                {prompt.icon}
              </div>
              <span className="font-bold text-slate-700 group-hover:text-sky-600 transition-colors">{prompt.title}</span>
            </div>
            <p className="text-xs text-slate-500 line-clamp-1">{prompt.desc}</p>
          </motion.button>
        ))}
      </div>
    </div>
  );
};
