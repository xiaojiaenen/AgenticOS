import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  BarChart3,
  Bot,
  LogOut,
  MessageSquare,
  Puzzle,
  Users,
} from 'lucide-react';
import { Logo } from '../Logo';
import { getStoredUser, logout } from '../../services/authService';
import { cn } from '../../lib/utils';

interface AdminSidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const navItems = [
  { id: 'dashboard', icon: BarChart3, label: '系统总览', description: '核心指标与趋势', angle: -104, radius: 168 },
  { id: 'history', icon: MessageSquare, label: '聊天记录', description: '会话检索与详情', angle: -58, radius: 176 },
  { id: 'users', icon: Users, label: '用户管理', description: '账号与角色', angle: -14, radius: 178 },
  { id: 'agents', icon: Bot, label: '智能体配置', description: '工具、审批与 Skill', angle: 28, radius: 170 },
  { id: 'skills', icon: Puzzle, label: 'Skill 管理', description: '本地 Skill 目录', angle: 72, radius: 150 },
] as const;

const utilityItems = [
  { id: 'back', icon: ArrowLeft, label: '返回对话', angle: 122, radius: 112 },
  { id: 'logout', icon: LogOut, label: '退出登录', angle: 154, radius: 88 },
] as const;

function polarPosition(angle: number, radius: number) {
  const radian = (angle * Math.PI) / 180;
  return {
    x: Math.cos(radian) * radius,
    y: Math.sin(radian) * radius,
  };
}

export const AdminSidebar = ({ activeTab, setActiveTab }: AdminSidebarProps) => {
  const navigate = useNavigate();
  const user = getStoredUser();
  const [isExpanded, setIsExpanded] = useState(false);
  const positions = useMemo(
    () =>
      new Map(
        [...navItems, ...utilityItems].map((item) => [
          item.id,
          polarPosition(item.angle, item.radius),
        ]),
      ),
    [],
  );

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleUtility = async (id: 'back' | 'logout') => {
    if (id === 'back') {
      navigate('/chat');
      return;
    }
    await handleLogout();
  };

  return (
    <>
      <div className="pointer-events-none fixed left-4 top-1/2 z-30 hidden -translate-y-1/2 lg:block">
        <div
          className="pointer-events-auto relative h-[420px] w-[320px]"
          onMouseEnter={() => setIsExpanded(true)}
          onMouseLeave={() => setIsExpanded(false)}
        >
          <motion.div
            initial={false}
            animate={{
              opacity: isExpanded ? 1 : 0.78,
              scale: isExpanded ? 1 : 0.92,
              width: isExpanded ? 250 : 86,
            }}
            transition={{ type: 'spring', stiffness: 280, damping: 28 }}
            className="absolute left-0 top-1/2 h-[320px] -translate-y-1/2 rounded-r-[170px] border border-white/65 bg-white/48 shadow-[0_30px_90px_rgba(15,23,42,0.12)] ring-1 ring-white/35 backdrop-blur-[32px]"
          />

          <motion.div
            initial={false}
            animate={{
              opacity: isExpanded ? 1 : 0,
              x: isExpanded ? 0 : -12,
            }}
            transition={{ duration: 0.18 }}
            className="pointer-events-none absolute left-[96px] top-[58px] max-w-[150px] rounded-[26px] border border-white/75 bg-white/76 px-4 py-3 text-sm shadow-[0_20px_60px_rgba(15,23,42,0.08)]"
          >
            <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">Admin</p>
            <p className="mt-1 truncate font-black text-slate-900">{user?.name || 'Admin'}</p>
            <p className="mt-1 text-xs font-medium leading-5 text-slate-500">悬停吉祥物，半圆展开导航与工作区入口。</p>
          </motion.div>

          {navItems.map((item) => {
            const position = positions.get(item.id) ?? { x: 0, y: 0 };
            const active = activeTab === item.id;

            return (
              <motion.button
                key={item.id}
                type="button"
                initial={false}
                animate={{
                  opacity: isExpanded || active ? 1 : 0,
                  x: isExpanded || active ? position.x : 0,
                  y: isExpanded || active ? position.y : 0,
                  scale: isExpanded || active ? 1 : 0.72,
                }}
                transition={{ type: 'spring', stiffness: 360, damping: 28 }}
                onClick={() => setActiveTab(item.id)}
                className={cn(
                  'absolute left-[34px] top-1/2 flex h-14 w-14 -translate-y-1/2 items-center justify-center rounded-full border shadow-[0_18px_40px_rgba(15,23,42,0.12)] backdrop-blur-2xl transition-colors',
                  active
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-white/80 bg-white/88 text-slate-700 hover:bg-white',
                )}
              >
                <item.icon size={20} />
                <motion.div
                  initial={false}
                  animate={{
                    opacity: isExpanded ? 1 : 0,
                    x: isExpanded ? 0 : -8,
                  }}
                  transition={{ duration: 0.18 }}
                  className="pointer-events-none absolute left-[64px] flex min-w-[124px] items-center gap-2 rounded-full border border-white/80 bg-white/88 px-3 py-2 text-left shadow-[0_18px_40px_rgba(15,23,42,0.1)]"
                >
                  <div className="min-w-0">
                    <p className="truncate text-xs font-black text-slate-900">{item.label}</p>
                    <p className="truncate text-[10px] font-medium text-slate-500">{item.description}</p>
                  </div>
                </motion.div>
              </motion.button>
            );
          })}

          {utilityItems.map((item) => {
            const position = positions.get(item.id) ?? { x: 0, y: 0 };

            return (
              <motion.button
                key={item.id}
                type="button"
                initial={false}
                animate={{
                  opacity: isExpanded ? 1 : 0,
                  x: isExpanded ? position.x : 0,
                  y: isExpanded ? position.y : 0,
                  scale: isExpanded ? 1 : 0.7,
                }}
                transition={{ type: 'spring', stiffness: 340, damping: 26 }}
                onClick={() => handleUtility(item.id)}
                className="absolute left-[42px] top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/80 bg-white/84 text-slate-600 shadow-[0_12px_28px_rgba(15,23,42,0.08)] backdrop-blur-xl hover:bg-white hover:text-slate-900"
                title={item.label}
              >
                <item.icon size={16} />
              </motion.button>
            );
          })}

          <motion.button
            type="button"
            initial={false}
            animate={{
              scale: isExpanded ? 1.02 : 1,
              boxShadow: isExpanded
                ? '0 26px 70px rgba(15,23,42,0.18)'
                : '0 18px 40px rgba(15,23,42,0.12)',
            }}
            onClick={() => setIsExpanded((value) => !value)}
            className="absolute left-0 top-1/2 flex h-[86px] w-[86px] -translate-y-1/2 items-center justify-center rounded-full border border-white/80 bg-white/90 backdrop-blur-[32px]"
          >
            <div className="rounded-full bg-[radial-gradient(circle,#ffffff_0%,rgba(255,255,255,0.86)_55%,rgba(224,242,254,0.72)_100%)] p-3">
              <Logo iconSize={34} showText={false} />
            </div>
          </motion.button>
        </div>
      </div>

      <div className="fixed inset-x-3 bottom-3 z-30 lg:hidden">
        <div className="flex items-center justify-between rounded-full border border-white/70 bg-white/74 px-3 py-2 shadow-[0_24px_60px_rgba(15,23,42,0.12)] ring-1 ring-white/30 backdrop-blur-[26px]">
          <button
            type="button"
            onClick={() => setIsExpanded((value) => !value)}
            className="flex h-11 w-11 items-center justify-center rounded-full border border-white/80 bg-white/88"
          >
            <Logo iconSize={24} showText={false} />
          </button>

          <div className="flex items-center gap-1.5">
            {navItems.map((item) => {
              const active = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveTab(item.id)}
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-full transition-colors',
                    active ? 'bg-slate-900 text-white' : 'bg-white/72 text-slate-600',
                  )}
                  title={item.label}
                >
                  <item.icon size={16} />
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => handleUtility('back')}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-white/72 text-slate-600"
              title="返回对话"
            >
              <ArrowLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => handleUtility('logout')}
              className="flex h-10 w-10 items-center justify-center rounded-full bg-white/72 text-slate-600"
              title="退出登录"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </div>
    </>
  );
};
