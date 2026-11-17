/**
 * 发送邮件时 React error #185（Maximum update depth exceeded）的回归。
 *
 * 根因：Chat 页有个 effect 依赖 `artifact`，而它每次都 `setArtifact(新对象)`。
 * 新对象 → artifact 引用变 → effect 重跑 → 再 setArtifact → 无限循环。
 *
 * 修法是把「从审批参数取数据」与「内容是否等价」抽成纯函数，在写入前比较。
 * 这里锁住那个比较语义 —— 一旦有人改回无条件写入，这些用例会红。
 */
import { describe, expect, it } from 'vitest';

import { emailArtifactFromApproval, isSameArtifact } from '../emailArtifact';

const APPROVAL_ARGS = {
  to: 'zhangwei@corp.com',
  subject: '项目周报',
  body: '本周进展如下…',
  cc: 'lisi@corp.com',
  is_html: false,
};

describe('emailArtifactFromApproval', () => {
  it('正常参数 → 生成面板数据', () => {
    const a = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    expect(a).toEqual({
      language: 'email',
      approvalId: 'ap-1',
      to: 'zhangwei@corp.com',
      subject: '项目周报',
      body: '本周进展如下…',
      cc: 'lisi@corp.com',
      isHtml: false,
    });
  });

  it('参数是 JSON 字符串也能解析（模型有时传字符串）', () => {
    const a = emailArtifactFromApproval(JSON.stringify(APPROVAL_ARGS), 'ap-1');
    expect(a?.subject).toBe('项目周报');
  });

  it('JSON 非法 → null（不抛异常、不弹空面板）', () => {
    expect(emailArtifactFromApproval('{ not json', 'ap-1')).toBeNull();
  });

  it('缺 to 或 subject → null（模型还在补参数，不该弹面板）', () => {
    expect(emailArtifactFromApproval({ to: 'a@b.com' }, 'x')).toBeNull();
    expect(emailArtifactFromApproval({ subject: 'hi' }, 'x')).toBeNull();
    expect(emailArtifactFromApproval({}, 'x')).toBeNull();
  });

  it('cc 为空时不写 undefined 之外的怪值', () => {
    const a = emailArtifactFromApproval({ to: 'a@b.com', subject: 's' }, 'x');
    expect(a?.cc).toBeUndefined();
    expect(a?.body).toBe('');
  });
});

describe('isSameArtifact（#185 的核心防线）', () => {
  it('内容相同的两个对象 → true（不再触发 setArtifact）', () => {
    const a = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    const b = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    // 关键：两个不同引用、内容相同
    expect(a).not.toBe(b);
    expect(isSameArtifact(a, b)).toBe(true);
  });

  it('任何字段变化 → false（该更新面板）', () => {
    const base = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    const cases = [
      emailArtifactFromApproval({ ...APPROVAL_ARGS, subject: '改了' }, 'ap-1'),
      emailArtifactFromApproval({ ...APPROVAL_ARGS, body: '改了' }, 'ap-1'),
      emailArtifactFromApproval({ ...APPROVAL_ARGS, to: 'other@corp.com' }, 'ap-1'),
      emailArtifactFromApproval({ ...APPROVAL_ARGS, cc: 'other@corp.com' }, 'ap-1'),
      emailArtifactFromApproval({ ...APPROVAL_ARGS, is_html: true }, 'ap-1'),
      emailArtifactFromApproval(APPROVAL_ARGS, 'ap-2'),
    ];
    for (const changed of cases) {
      expect(isSameArtifact(base, changed)).toBe(false);
    }
  });

  it('null / undefined 参与比较时不误判为相同', () => {
    const a = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    expect(isSameArtifact(null, a)).toBe(false);
    expect(isSameArtifact(a, null)).toBe(false);
    expect(isSameArtifact(null, null)).toBe(true);
  });

  it('语言不同 → false（不会把邮件面板当成 PPT 面板）', () => {
    const email = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    const ppt = {
      language: 'ppt' as const,
      html: '<svg/>',
      title: 't',
      slideCount: 1,
    };
    expect(isSameArtifact(email, ppt)).toBe(false);
  });

  it('重复比较同一内容始终稳定（模拟 effect 反复执行）', () => {
    // 模拟 effect 跑 5 次：每次都从参数重建，比较结果必须一直是"相同"，
    // 否则就会第 N 次写到 store 里 → 继续触发 effect → #185。
    let current = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
    for (let i = 0; i < 5; i += 1) {
      const rebuilt = emailArtifactFromApproval(APPROVAL_ARGS, 'ap-1');
      expect(isSameArtifact(current, rebuilt)).toBe(true);
      if (!isSameArtifact(current, rebuilt)) current = rebuilt;
    }
  });
});
