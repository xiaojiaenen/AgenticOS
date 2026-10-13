import { describe, it, expect } from 'vitest';
import {
  cn,
  formatNumber,
  formatTokenNumber,
  formatLatency,
  formatPercent,
  formatDay,
  shortName,
  initials,
  ratio,
} from '../utils';

describe('cn', () => {
  it('拼接多个类名，跳过假值', () => {
    expect(cn('a', undefined, 'c', null, 'd')).toBe('a c d');
    expect(cn('a', false, 'c', 0, '')).toBe('a c');
  });

  it('tailwind-merge 解决冲突类名（后者胜出）', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4');
    expect(cn('text-sm', 'text-lg')).toBe('text-lg');
  });
});

describe('formatTokenNumber', () => {
  it('按数量级缩写', () => {
    expect(formatTokenNumber(500)).toBe('500');
    expect(formatTokenNumber(10_000)).toBe('10000');
    expect(formatTokenNumber(15_000)).toBe('15K');
    expect(formatTokenNumber(2_500_000)).toBe('2.5M');
    expect(formatTokenNumber(3_000_000_000)).toBe('3.0B');
    expect(formatTokenNumber(4_000_000_000_000)).toBe('4.0T');
    expect(formatTokenNumber(-25_000)).toBe('-25K');
  });
});

describe('formatLatency / formatPercent / formatNumber', () => {
  it('formatLatency 区分 ms 与 s', () => {
    expect(formatLatency(0)).toBe('0 ms');
    expect(formatLatency(350)).toBe('350 ms');
    expect(formatLatency(1234)).toBe('1.2 s');
  });

  it('formatPercent 四舍五入', () => {
    expect(formatPercent(33.4)).toBe('33%');
    expect(formatPercent(99.6)).toBe('100%');
  });

  it('formatNumber 千位以上使用紧凑记法', () => {
    expect(formatNumber(999)).toBe('999');
    expect(formatNumber(12_345)).toBe('1.2万');
  });
});

describe('formatDay / shortName / initials', () => {
  it('formatDay 解析 YYYY-MM-DD 为 M/D', () => {
    expect(formatDay('2024-01-05')).toBe('1/5');
    expect(formatDay('2024-12-25')).toBe('12/25');
  });

  it('shortName 超长截断加省略号', () => {
    expect(shortName('')).toBe('未知');
    expect(shortName('abcdefg')).toBe('abcdefg');
    expect(shortName('abcdefgh')).toBe('abcdefg…');
    expect(shortName('abcdefghij', 3)).toBe('abc…');
  });

  it('initials 取首字符大写', () => {
    expect(initials('alice')).toBe('A');
    expect(initials('')).toBe('?');
  });
});

describe('ratio', () => {
  it('计算百分比并夹在 [0, 100]', () => {
    expect(ratio(50, 200)).toBe(25);
    expect(ratio(10, 0)).toBe(0);
    expect(ratio(200, 100)).toBe(100);
    expect(ratio(-5, 100)).toBe(0);
  });
});
