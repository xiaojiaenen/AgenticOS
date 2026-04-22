import React from 'react';
import { Database, Server } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

export const ModelConfig = () => {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">模型管理</h2>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        {/* OpenAI 兼容模型网关 */}
        <Card>
          <CardHeader>
            <CardTitle>
              <div className="p-2.5 bg-zinc-100 text-zinc-600 rounded-xl"><Database size={20} /></div>
              OpenAI 兼容配置
            </CardTitle>
            <div className="w-14 h-7 bg-emerald-400 rounded-full relative cursor-pointer shadow-inner">
              <div className="w-5 h-5 bg-white rounded-full absolute right-1 top-1 shadow-sm transition-transform duration-300"></div>
            </div>
          </CardHeader>
          <CardContent>
            <Input 
              label="API 密钥" 
              type="password" 
              value="sk-........................" 
              readOnly 
              className="font-mono text-sm"
            />
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 ml-1">默认模型</label>
              <select className="w-full px-5 py-3.5 bg-white border border-slate-200 rounded-2xl text-slate-700 font-medium focus:outline-none focus:border-zinc-400 focus:ring-4 focus:ring-zinc-100/50 transition-all appearance-none cursor-pointer">
                <option>gpt-5.4</option>
                <option>deepseek-chat</option>
                <option>gpt-4o</option>
              </select>
            </div>
            <Button variant="secondary" className="w-full mt-2" size="lg">测试连接</Button>
          </CardContent>
        </Card>

        {/* 本地模型配置 */}
        <Card>
          <CardHeader>
            <CardTitle>
              <div className="p-2.5 bg-zinc-100 text-zinc-600 rounded-xl"><Server size={20} /></div>
              Ollama 配置 (本地)
            </CardTitle>
            <div className="w-14 h-7 bg-emerald-400 rounded-full relative cursor-pointer shadow-inner transition-colors duration-300">
              <div className="w-5 h-5 bg-white rounded-full absolute right-1 top-1 shadow-sm transition-transform duration-300"></div>
            </div>
          </CardHeader>
          <CardContent>
            <Input 
              label="API 地址"
              type="text" 
              defaultValue="http://localhost:11434"
            />
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-2 ml-1">已安装模型</label>
              <div className="flex flex-wrap gap-2 p-4 bg-slate-50 border border-slate-100 rounded-2xl">
                <span className="px-3 py-1.5 bg-white text-slate-700 rounded-xl text-sm font-bold border border-slate-200 shadow-sm transition-all hover:border-zinc-400 cursor-default">llama3:8b</span>
                <span className="px-3 py-1.5 bg-white text-slate-700 rounded-xl text-sm font-bold border border-slate-200 shadow-sm transition-all hover:border-zinc-400 cursor-default">mistral</span>
                <span className="px-3 py-1.5 bg-white text-slate-700 rounded-xl text-sm font-bold border border-slate-200 shadow-sm transition-all hover:border-zinc-400 cursor-default">qwen:7b</span>
              </div>
            </div>
            <Button variant="secondary" className="w-full mt-2" size="lg">刷新模型列表</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
