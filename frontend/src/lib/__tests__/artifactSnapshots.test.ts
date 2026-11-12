import { describe, expect, it } from 'vitest';
import {
  patchLastModelMessage,
  pptMessageArtifact,
  sheetMessageArtifact,
  websiteMessageArtifact,
} from '../artifactSnapshots';

describe('pptMessageArtifact', () => {
  it('snake_case payload 映射为 ready 快照（含 mode/theme）', () => {
    expect(
      pptMessageArtifact({
        artifact_id: 'a1',
        title: 'T',
        slide_count: 8,
        html: '<svg/>',
        theme: 'apple',
      }),
    ).toEqual({
      status: 'ready',
      artifactId: 'a1',
      title: 'T',
      slideCount: 8,
      html: '<svg/>',
      mode: 'ppt',
      theme: 'apple',
    });
  });
});

describe('websiteMessageArtifact', () => {
  const payload = {
    artifact_id: 'w1',
    title: 'W',
    project_slug: 'p',
    stack: 'vanilla',
    preview_html: '<html/>',
  };

  it('默认不落 previewUrl（流式路径：预览令牌 15 分钟 TTL）', () => {
    const snap = websiteMessageArtifact({ ...payload, preview_url: 'https://signed' });
    expect(snap.previewUrl).toBeUndefined();
    expect(snap.html).toBe('<html/>');
    expect(snap.status).toBe('ready');
  });

  it('回源路径显式传入新签的 previewUrl', () => {
    const snap = websiteMessageArtifact(
      { ...payload, preview_url: 'https://fresh-signed' },
      { previewUrl: 'https://fresh-signed' },
    );
    expect(snap.previewUrl).toBe('https://fresh-signed');
  });

  it('previewUrl 为 null 时落 undefined 而不是 null', () => {
    const snap = websiteMessageArtifact(payload, { previewUrl: null });
    expect(snap.previewUrl).toBeUndefined();
  });
});

describe('sheetMessageArtifact', () => {
  it('映射 sheetNames/sheetCount', () => {
    expect(
      sheetMessageArtifact({
        artifact_id: 's1',
        title: 'S',
        sheet_names: ['A', 'B'],
        sheet_count: 2,
      }),
    ).toEqual({
      status: 'ready',
      artifactId: 's1',
      title: 'S',
      sheetNames: ['A', 'B'],
      sheetCount: 2,
    });
  });
});

describe('patchLastModelMessage', () => {
  it('patch 最后一条 model 消息，其余保持同一引用', () => {
    const user = { role: 'user' as const, id: 'u1' };
    const model1 = { role: 'model' as const, id: 'm1' };
    const model2 = { role: 'model' as const, id: 'm2' };
    const messages = [user, model1, model2];

    const next = patchLastModelMessage(messages, (m) => ({ ...m, id: `${m.id}-patched` }));
    expect(next).toHaveLength(3);
    expect(next[0]).toBe(user);
    expect(next[1]).toBe(model1);
    expect(next[2].id).toBe('m2-patched');
    // 原数组不被修改
    expect(messages[2].id).toBe('m2');
  });

  it('没有 model 消息时原样返回同一数组', () => {
    const user = { role: 'user' as const, id: 'u1' };
    const messages = [user];
    expect(patchLastModelMessage(messages, (m) => ({ ...m }))).toBe(messages);
  });
});
