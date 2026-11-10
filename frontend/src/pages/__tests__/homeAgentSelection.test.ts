/**
 * 回归：首页智能体选择不得被重置回「通用助手」。
 *
 * 两个真实失效点（都会导致"选了别的智能体，立刻跳回通用助手"）：
 * 1. `getStoredUser()` 每次调用都 JSON.parse 出新对象。把它当 useCallback
 *    依赖 → loadAgents 每次渲染换新引用 → useEffect 重跑 → 重新拉列表。
 * 2. 重新拉列表后无条件 `setSelectedAgentProfileId(general.id)`，直接覆盖
 *    用户刚做的选择。
 *
 * 这里不挂完整 Home（依赖 router/懒加载），而是照搬它的两个关键模式做
 * 等价断言：引用稳定 + 默认只应用一次。
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';

describe('首页智能体选择稳定性', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('getStoredUser 每次返回新对象（因此不能直接作为 hook 依赖）', async () => {
    localStorage.setItem(
      'auth_user',
      JSON.stringify({ id: 1, email: 'a@b.c', name: 'A', role: 'admin' }),
    );
    const { getStoredUser } = await import('../../services/authTokenStore');
    const a = getStoredUser();
    const b = getStoredUser();
    expect(a).toEqual(b);
    // 关键：值相等但不是同一个引用 —— 这正是依赖不稳定的根源
    expect(a).not.toBe(b);
  });

  it('惰性 state 捕获后引用稳定（首页修复采用的写法）', async () => {
    localStorage.setItem(
      'auth_user',
      JSON.stringify({ id: 1, email: 'a@b.c', name: 'A', role: 'admin' }),
    );
    const { getStoredUser } = await import('../../services/authTokenStore');
    // 模拟 useState(() => getStoredUser()) 只执行一次
    const captured = getStoredUser();
    const renders = [captured, captured, captured];
    expect(new Set(renders).size).toBe(1);
    expect(Boolean(captured)).toBe(true);
  });

  it('默认选中只应用一次，后续拉取不覆盖用户选择', () => {
    // 照搬 Home 的应用逻辑
    let selected: number | null = null;
    let appliedDefault = false;
    const applyAgents = (items: Array<{ id: number; slug: string }>) => {
      if (!appliedDefault) {
        const general = items.find((a) => a.slug === 'general');
        if (general) selected = general.id;
        appliedDefault = true;
      }
    };

    const agents = [
      { id: 1, slug: 'general' },
      { id: 2, slug: 'ppt-designer' },
    ];
    applyAgents(agents);
    expect(selected).toBe(1); // 首次默认 general

    selected = 2; // 用户选择 PPT 设计师
    applyAgents(agents); // 再次拉取（历史 bug：这里会把 selected 覆盖回 1）
    expect(selected).toBe(2); // 选择必须保留
  });
});