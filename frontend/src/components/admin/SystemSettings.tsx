import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { getAppConfig, saveAppConfig, AppConfig } from '../../services/configService';
import { 
  Check, 
  X, 
  Wrench, 
  Shapes, 
  Search, 
  Binary, 
  Code2, 
  Cpu
} from 'lucide-react';

export const SystemSettings = () => {
  const [config, setConfig] = useState<AppConfig>(getAppConfig());
  const [isSaved, setIsSaved] = useState(false);

  const toggle = (field: keyof AppConfig) => {
    const newConfig = { ...config, [field]: !config[field] };
    setConfig(newConfig);
    saveAppConfig(newConfig);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const ConfigItem = ({ 
    icon: Icon, 
    title, 
    desc, 
    field, 
    color 
  }: { 
    icon: any, 
    title: string, 
    desc: string, 
    field: keyof AppConfig,
    color: string
  }) => (
    <div className="bg-white border border-slate-200/60 p-6 rounded-[2rem] shadow-sm flex items-center justify-between group hover:shadow-md hover:border-slate-300/80 transition-all duration-300">
      <div className="flex items-center gap-5">
        <div className={`w-14 h-14 rounded-2xl ${color} flex items-center justify-center text-white shadow-lg`}>
          <Icon size={24} />
        </div>
        <div>
          <h3 className="font-display font-bold text-slate-800 text-lg leading-tight mb-1">{title}</h3>
          <p className="text-slate-400 text-sm font-medium tracking-tight">{desc}</p>
        </div>
      </div>
      
      <button 
        onClick={() => toggle(field)}
        className={`relative w-14 h-8 rounded-full transition-all duration-500 ease-in-out p-1 flex items-center ${
          config[field] ? 'bg-zinc-900 justify-end' : 'bg-slate-200 justify-start'
        }`}
      >
        <motion.div 
          layout
          className={`w-6 h-6 rounded-full bg-white shadow-sm flex items-center justify-center`}
        >
          {config[field] ? <Check size={12} className="text-zinc-900" /> : <X size={12} className="text-slate-400" />}
        </motion.div>
      </button>
    </div>
  );

  return (
    <div className="space-y-8 pb-10">
      <div className="flex justify-between items-center bg-zinc-900 p-8 rounded-[2.5rem] shadow-xl relative overflow-hidden">
        <div className="relative z-10">
          <h2 className="text-3xl font-display font-bold text-white mb-2 tracking-tight">核心工具管理</h2>
          <p className="text-slate-400 text-sm font-medium">精确控制 AgenticOS 的渲染能力、联网功能与代码预览体验</p>
        </div>
        <div className="absolute right-0 top-0 opacity-10 -rotate-12 translate-x-1/4 -translate-y-1/4">
          <Wrench size={280} color="white" />
        </div>
        {isSaved && (
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="bg-white/10 backdrop-blur-md border border-white/20 text-white px-4 py-2 rounded-xl text-sm font-bold flex items-center gap-2"
          >
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            系统配置已更新
          </motion.div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <ConfigItem 
          icon={Binary} 
          title="LaTeX 数学渲染" 
          desc="启用 Katex 渲染复杂的数学公式与方程"
          field="enableLaTeX"
          color="bg-sky-500"
        />
        <ConfigItem 
          icon={Shapes} 
          title="Mermaid 图表" 
          desc="自动转换文本为流程图、甘特图等矢量图形"
          field="enableMermaid"
          color="bg-emerald-500"
        />
        <ConfigItem 
          icon={Search} 
          title="联网实时搜索" 
          desc="连接后端智能体与外部工具，补充最新资讯与实时数据"
          field="enableSearch"
          color="bg-amber-500"
        />
        <ConfigItem 
          icon={Cpu} 
          title="智能组件 (Artifacts)" 
          desc="实时生成并预览前端应用与交互式代码"
          field="enableArtifacts"
          color="bg-purple-500"
        />
      </div>

      <div className="bg-white/40 backdrop-blur-md border border-slate-200/60 p-8 rounded-[2.5rem] mt-4">
        <div className="flex items-center gap-4 mb-6">
           <div className="w-10 h-10 bg-zinc-100 rounded-xl flex items-center justify-center text-zinc-500">
              <Code2 size={20} />
           </div>
           <h3 className="text-xl font-display font-bold text-slate-800 tracking-tight">开发人员元数据</h3>
        </div>
        <div className="grid grid-cols-3 gap-6">
          {[
            { label: '系统版本', value: 'v2.4.0-stable' },
            { label: '运行时环境', value: 'Vite + React 19' },
            { label: '智能体引擎', value: 'FastAPI + Wuwei' }
          ].map((stat, i) => (
            <div key={i} className="space-y-1">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">{stat.label}</span>
              <p className="text-sm font-mono font-medium text-slate-700">{stat.value}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
