/**
 * 登录页 LDAP 形态文案回归。
 *
 * 用户报障：「LDAP 登录应该是邮箱号，而不是工号」。员工记住的是自己的企业
 * 邮箱，目录里的 sAMAccountName 只有管理员知道，所以登录框必须收邮箱。
 *
 * 这里锁住文案与占位符 —— 纯文案改动没有逻辑可以断言，但**文案回退**正是
 * 这次要防的回归（哪怕是复制粘贴旧代码或改配置时顺手带回"工号"）。
 */
import { describe, expect, it } from 'vitest';

import {
  LDAP_ACCOUNT_LABEL,
  LDAP_ACCOUNT_REQUIRED,
  ldapAccountPlaceholder,
} from '../Login';

describe('LDAP 登录文案', () => {
  it('标签是「企业邮箱」，不再是工号/域账号', () => {
    expect(LDAP_ACCOUNT_LABEL).toBe('企业邮箱');
    expect(LDAP_ACCOUNT_LABEL).not.toContain('工号');
  });

  it('必填提示说的是企业邮箱', () => {
    expect(LDAP_ACCOUNT_REQUIRED).toBe('请输入企业邮箱');
    expect(LDAP_ACCOUNT_REQUIRED).not.toContain('工号');
  });

  it('配了邮箱域名 → 占位符给出完整示例', () => {
    expect(ldapAccountPlaceholder('corp.com')).toBe('name@corp.com');
    // 配置里可能带前导 @，不应出现 name@@corp.com
    expect(ldapAccountPlaceholder('@corp.com')).toBe('name@corp.com');
    // 前后空白同样容忍（管理员手输容易带）
    expect(ldapAccountPlaceholder('  corp.com  ')).toBe('name@corp.com');
  });

  it('没配邮箱域名 → 占位符不编造域名', () => {
    expect(ldapAccountPlaceholder('')).toBe('请输入企业邮箱');
    expect(ldapAccountPlaceholder('   ')).toBe('请输入企业邮箱');
    // 只有 @ 也算没配
    expect(ldapAccountPlaceholder('@')).toBe('请输入企业邮箱');
  });
});
