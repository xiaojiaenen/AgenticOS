/**
 * 回归：右侧产物面板收起后必须能重新打开。
 *
 * 真实故障（用户原话）：「右侧边栏收起来报错 no elements in sequence，
 * 右侧边栏收起来后无法再次打开」。
 *
 * 两个独立原因：
 *
 * 1. **打不开**：`reopenableArtifact` 只认 ppt / website，表格、文档
 *    产物关掉后「重新打开」按钮永远不出现。
 * 2. **报错**：收起表格/文档面板会 `univer.dispose()`，Univer 内部的
 *    `observable.pipe(first())` 在已 complete 的流上踩空，异步抛
 *    `EmptyError: no elements in sequence`。
 *
 * 这里测的是纯逻辑部分（选择逻辑 + 噪音判定），不渲染 Univer。
 */
import { describe, expect, it } from 'vitest';
import {
  beginUniverTeardown,
  isKnownUniverTeardownNoise,
} from '../univerTeardown';

describe('univerTeardown', () => {
  it('卸载窗口内的 EmptyError 被识别为已知噪音', () => {
    beginUniverTeardown();
    expect(isKnownUniverTeardownNoise(new Error('no elements in sequence'))).toBe(true);
    // rxjs 的 EmptyError 原文也可能带前缀
    expect(
      isKnownUniverTeardownNoise(new Error('EmptyError: no elements in sequence')),
    ).toBe(true);
  });

  it('窗口外的同样文案不算噪音（避免掩盖真实错误）', () => {
    // 窗口是 2 秒，这里直接构造一个「从未 begin」的干净状态：
    // 通过伪造 Date.now 让窗口已过期
    const realNow = Date.now;
    beginUniverTeardown();
    try {
      Date.now = () => realNow() + 10_000;
      expect(isKnownUniverTeardownNoise(new Error('no elements in sequence'))).toBe(false);
    } finally {
      Date.now = realNow;
    }
  });

  it('窗口内的其它错误一律放行', () => {
    beginUniverTeardown();
    expect(isKnownUniverTeardownNoise(new Error('Cannot read properties of null'))).toBe(
      false,
    );
    expect(isKnownUniverTeardownNoise(new Error('network error'))).toBe(false);
  });

  it('非 Error 形态也能判定（字符串 reason）', () => {
    beginUniverTeardown();
    expect(isKnownUniverTeardownNoise('no elements in sequence')).toBe(true);
    expect(isKnownUniverTeardownNoise(undefined)).toBe(false);
    expect(isKnownUniverTeardownNoise({})).toBe(false);
  });
});
