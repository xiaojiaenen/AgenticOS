import { describe, it, expect } from 'vitest';
import { parseApiDate, formatApiDate, formatApiDateTime, APP_TIME_ZONE } from '../datetime';

describe('parseApiDate', () => {
  it('无时区的 API 时间串按东八区解析', () => {
    const date = parseApiDate('2024-01-15T08:30:00');
    expect(date).not.toBeNull();
    expect(date!.getTime()).toBe(new Date('2024-01-15T08:30:00+08:00').getTime());
  });

  it('已带时区/UTC 标记的时间串不追加时区', () => {
    expect(parseApiDate('2024-01-15T00:00:00Z')!.getTime())
      .toBe(new Date('2024-01-15T00:00:00Z').getTime());
    expect(parseApiDate('2024-01-15T08:30:00+05:00')!.getTime())
      .toBe(new Date('2024-01-15T08:30:00+05:00').getTime());
  });

  it('空值与非法值返回 null', () => {
    expect(parseApiDate(null)).toBeNull();
    expect(parseApiDate(undefined)).toBeNull();
    expect(parseApiDate('')).toBeNull();
    expect(parseApiDate('not-a-date')).toBeNull();
  });
});

describe('formatApiDate / formatApiDateTime', () => {
  it('格式化为 zh-CN 日期（含横杠输入返回 -）', () => {
    expect(formatApiDate('2024-01-15T08:30:00')).toBe('2024/01/15');
    expect(formatApiDate(null)).toBe('-');
    expect(formatApiDate('bad')).toBe('-');
  });

  it('格式化日期时间包含时分秒且使用东八区', () => {
    const out = formatApiDateTime('2024-01-15T08:30:05');
    expect(out).toBe('2024/01/15 08:30:05');
    // UTC 22:00 前一天 → 东八区次日 06:00
    const cross = formatApiDateTime('2024-01-14T22:00:00Z');
    expect(cross).toBe('2024/01/15 06:00:00');
    expect(APP_TIME_ZONE).toBe('Asia/Shanghai');
  });
});
