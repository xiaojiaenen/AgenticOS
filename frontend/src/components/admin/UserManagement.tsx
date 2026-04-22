import React, { useState } from 'react';
import { Settings, Search, Plus } from 'lucide-react';
import { Pagination } from './Pagination';
import { Card, CardContent } from '../ui/Card';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';

// Generate mock data
const MOCK_USERS = Array.from({ length: 32 }, (_, i) => ({
  id: i + 1,
  email: `user${i + 1}@example.com`,
  regDate: `2024-01-${String((i % 28) + 1).padStart(2, '0')}`,
  active: i === 0 ? '刚刚' : i < 5 ? `${i * 15}分钟前` : `${(i % 12) + 1}小时前`,
  status: i % 7 === 0 ? '封禁' : '正常'
}));

const ITEMS_PER_PAGE = 6;

export const UserManagement = () => {
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Filter data based on search
  const filteredData = MOCK_USERS.filter(user => 
    user.email.toLowerCase().includes(searchQuery.toLowerCase()) || 
    `U${user.id}`.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalPages = Math.ceil(filteredData.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const currentData = filteredData.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  // Reset to page 1 when search changes
  React.useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800">用户管理 (User Management)</h2>
      <Card className="flex flex-col p-0 overflow-hidden">
        <div className="p-8 flex-1">
          <div className="flex justify-between items-center mb-8">
            <div className="relative w-80">
              <Search className="absolute left-5 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
              <input 
                type="text" 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索用户邮箱或 ID..." 
                className="w-full pl-12 pr-5 py-3.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-zinc-400 focus:ring-4 focus:ring-zinc-100/50 transition-all font-medium text-sm" 
              />
            </div>
            <Button variant="primary" size="md">
              <Plus size={18} />
              添加新用户
            </Button>
          </div>
          <div className="space-y-4">
            {currentData.length > 0 ? (
              currentData.map((user) => (
                <div key={user.id} className="flex items-center justify-between p-5 bg-white border border-slate-100 rounded-2xl hover:border-zinc-300 hover:shadow-md transition-all group">
                  <div className="flex items-center gap-5">
                    <div className="w-12 h-12 bg-gradient-to-br from-slate-100 to-slate-200 rounded-2xl flex items-center justify-center text-slate-500 font-black shadow-inner">
                      U{user.id}
                    </div>
                    <div>
                      <p className="font-bold text-slate-800 text-base">{user.email}</p>
                      <p className="text-xs text-slate-400 font-medium mt-0.5">注册时间: {user.regDate} · 最后活跃: {user.active}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className={`px-3 py-1 rounded-full text-xs font-bold border ${
                      user.status === '正常' 
                        ? 'bg-emerald-50 text-emerald-600 border-emerald-100' 
                        : 'bg-rose-50 text-rose-600 border-rose-100'
                    }`}>
                      {user.status}
                    </span>
                    <button className="p-2.5 text-slate-400 hover:text-zinc-600 hover:bg-zinc-50 rounded-xl transition-colors">
                      <Settings size={18} />
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="py-12 text-center text-slate-400 font-medium">
                没有找到匹配的用户
              </div>
            )}
          </div>
        </div>
        {totalPages > 0 && (
          <Pagination 
            currentPage={currentPage} 
            totalPages={totalPages} 
            onPageChange={setCurrentPage} 
          />
        )}
      </Card>
    </div>
  );
};
