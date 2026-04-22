import React, { useState } from 'react';
import { Pagination } from './Pagination';
import { Card } from '../ui/Card';

// 生成演示用的历史记录数据
const MOCK_HISTORY = Array.from({ length: 45 }, (_, i) => {
  const models = ['GPT-5.4', 'DeepSeek Chat', 'Qwen 3', 'Ollama/Llama3'];
  const snippets = [
    '帮我写一个 React 组件...', 
    '如何配置 Nginx 反向代理？', 
    '翻译这段文字到法语...', 
    '解释一下量子力学', 
    '写一首关于春天的诗',
    '帮我检查这段 Python 代码的 bug',
    '推荐几本关于投资理财的书籍'
  ];
  
  return {
    id: `usr_${Math.random().toString(36).substring(2, 7)}`,
    snippet: snippets[i % snippets.length],
    model: models[i % models.length],
    time: i === 0 ? '刚刚' : i < 5 ? `${i * 10}分钟前` : `${(i % 24) + 1}小时前`,
  };
});

const ITEMS_PER_PAGE = 8;

export const ChatHistory = () => {
  const [currentPage, setCurrentPage] = useState(1);
  
  const totalPages = Math.ceil(MOCK_HISTORY.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const currentData = MOCK_HISTORY.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  const getModelColor = (model: string) => {
    if (model.includes('GPT')) return 'bg-zinc-100 text-zinc-700';
    if (model.includes('Claude')) return 'bg-slate-100 text-slate-700';
    if (model.includes('Ollama')) return 'bg-zinc-200 text-zinc-800';
    return 'bg-slate-200 text-slate-800';
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">对话历史管理</h2>
      <Card className="flex flex-col p-0 overflow-hidden">
        <div className="overflow-x-auto flex-1 min-h-[500px]">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/50 text-slate-500 text-sm border-b border-slate-100">
                <th className="p-6 font-bold uppercase tracking-wider rounded-tl-2xl">用户 ID</th>
                <th className="p-6 font-bold uppercase tracking-wider">对话片段</th>
                <th className="p-6 font-bold uppercase tracking-wider">模型</th>
                <th className="p-6 font-bold uppercase tracking-wider">时间</th>
                <th className="p-6 font-bold uppercase tracking-wider text-right rounded-tr-2xl">操作</th>
              </tr>
            </thead>
            <tbody className="text-sm text-slate-700">
              {currentData.map((item, index) => (
                <tr key={index} className="border-b border-slate-50 hover:bg-slate-50/80 transition-colors group">
                  <td className="p-6 font-mono text-xs text-slate-500 group-hover:text-zinc-800 transition-colors">{item.id}</td>
                  <td className="p-6 truncate max-w-xs font-medium text-slate-800">{item.snippet}</td>
                  <td className="p-6">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold ${getModelColor(item.model)}`}>
                      {item.model}
                    </span>
                  </td>
                  <td className="p-6 text-slate-500 font-medium">{item.time}</td>
                  <td className="p-6 text-right">
                    <button className="px-4 py-2 bg-slate-100 text-slate-600 rounded-xl hover:bg-zinc-900 hover:text-white font-bold transition-colors text-xs shadow-sm hover:shadow-md">
                      查看详情
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pagination 
          currentPage={currentPage} 
          totalPages={totalPages} 
          onPageChange={setCurrentPage} 
        />
      </Card>
    </div>
  );
};
