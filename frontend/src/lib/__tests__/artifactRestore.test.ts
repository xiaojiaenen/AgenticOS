/**
 * 产物恢复的纯决策逻辑回归（issue 1）。
 *
 * 历史故障：Chat.tsx 恢复 effect 把 `artifactRestoredSessionRef.current = id`
 * 写在 getSessionArtifacts().then 的 else 分支**之后**，无产物分支提前 return，
 * ref 永远不被设置 —— 每次 setArtifact 都重跑 effect、重发请求；迟到的
 * 「无产物」响应还会清掉用户刚手动打开的产物面板。
 *
 * 这里锁住提取出来的纯决策 helper：什么情况下要等回源、挑哪个产物、
 * 什么时候才允许清面板（不能误杀刚打开、还没带 sessionId 的产物）。
 */
import { describe, expect, it } from 'vitest';
import {
  findRestorableArtifact,
  hasPendingArtifactHtml,
  shouldClearStaleArtifact,
  type ArtifactSnapshotMsg,
} from '../artifactSnapshots';

type Msg = ArtifactSnapshotMsg;

const model = (overrides: Partial<Msg> = {}): Msg => ({ role: 'model', ...overrides });

describe('hasPendingArtifactHtml', () => {
  it('缓存剥离 HTML 的 ppt / website 要等回源', () => {
    expect(hasPendingArtifactHtml([model({ pptArtifact: { html: undefined } })])).toBe(true);
    expect(hasPendingArtifactHtml([model({ websiteArtifact: { html: undefined } })])).toBe(true);
  });

  it('已有 HTML 或完全无产物时不等', () => {
    expect(hasPendingArtifactHtml([model({ pptArtifact: { html: '<svg/>' } })])).toBe(false);
    expect(hasPendingArtifactHtml([model()])).toBe(false);
    expect(hasPendingArtifactHtml([])).toBe(false);
  });

  it('用户消息上的伪产物不算', () => {
    expect(
      hasPendingArtifactHtml([{ role: 'user', pptArtifact: { html: undefined } }]),
    ).toBe(false);
  });
});

describe('findRestorableArtifact', () => {
  it('从后往前挑，PPT 优先于 website', () => {
    const messages = [
      model({ websiteArtifact: { status: 'ready', html: '<html/>' } }),
      model({ pptArtifact: { status: 'ready', html: '<svg/>' } }),
    ];
    expect(findRestorableArtifact(messages)).toBe('ppt');
  });

  it('只有 website 时恢复 website', () => {
    expect(
      findRestorableArtifact([model({ websiteArtifact: { status: 'ready', html: '<html/>' } })]),
    ).toBe('website');
  });

  it('无 ready / 无 html 的产物不恢复（交给回源探测表格/文档）', () => {
    expect(findRestorableArtifact([model({ pptArtifact: { status: 'generating', html: '' } })])).toBeNull();
    expect(findRestorableArtifact([model({ pptArtifact: { status: 'ready', html: '' } })])).toBeNull();
  });
});

describe('shouldClearStaleArtifact', () => {
  it('空面板 → 清', () => {
    expect(shouldClearStaleArtifact(null, 's1')).toBe(true);
  });

  it('属于其它会话 → 清', () => {
    expect(shouldClearStaleArtifact({ sessionId: 's2' }, 's1')).toBe(true);
  });

  it('属于本会话 → 不清', () => {
    expect(shouldClearStaleArtifact({ sessionId: 's1' }, 's1')).toBe(false);
  });

  it('流式刚设置、还没带 sessionId 的产物 → 不清（迟到响应不能打掉它）', () => {
    expect(shouldClearStaleArtifact({ sessionId: undefined }, 's1')).toBe(false);
    expect(shouldClearStaleArtifact({}, 's1')).toBe(false);
  });
});
