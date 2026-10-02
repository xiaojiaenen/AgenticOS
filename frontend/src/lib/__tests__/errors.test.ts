import { describe, it, expect } from 'vitest';
import { localizeError } from '../errors';

describe('localizeError', () => {
  it('保留已是中文的错误', () => {
    expect(localizeError('邮箱或密码不正确')).toBe('邮箱或密码不正确');
  });

  it('翻译已知英文错误', () => {
    expect(localizeError('Invalid email or password')).toBe('邮箱或密码不正确');
    expect(localizeError('Email already registered')).toBe('该邮箱已注册，请直接登录');
    expect(localizeError('User is disabled')).toBe('账号已被禁用，请联系管理员');
  });

  it('翻译网络类错误', () => {
    expect(localizeError('Failed to fetch')).toContain('网络连接失败');
    expect(localizeError('Load failed')).toContain('网络连接失败');
  });

  it('翻译超时与限流', () => {
    expect(localizeError('Request timeout')).toContain('超时');
    expect(localizeError('Too Many Requests')).toContain('操作过于频繁');
  });

  it('翻译权限与不存在', () => {
    expect(localizeError('Forbidden')).toBe('没有权限执行该操作');
    expect(localizeError('Not Found')).toBe('请求的内容不存在');
    expect(localizeError('401 Unauthorized')).toContain('没有权限');
  });

  it('翻译框架级固定文案', () => {
    expect(localizeError('Request body too large.')).toContain('内容太长');
  });

  it('未知英文错误：给出中文兜底并保留技术信息', () => {
    const out = localizeError('psycopg2.errors.UniqueViolation: duplicate key');
    expect(out).toContain('操作失败');
    expect(out).toContain('psycopg2');
  });

  it('空值与 null 使用兜底', () => {
    expect(localizeError(null)).toBe('操作失败，请稍后重试');
    expect(localizeError('')).toBe('操作失败，请稍后重试');
    expect(localizeError('   ')).toBe('操作失败，请稍后重试');
  });

  it('支持 Error 对象', () => {
    expect(localizeError(new Error('NetworkError when attempting to fetch resource')))
      .toContain('网络连接失败');
  });

  it('自定义兜底文案生效', () => {
    expect(localizeError('some unknown failure', '保存失败'))
      .toContain('保存失败');
  });
});
