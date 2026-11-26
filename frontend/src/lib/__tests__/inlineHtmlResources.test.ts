import { describe, it, expect } from 'vitest';
import {
  isInlineableRelative,
  inlineHtmlResources,
  hasRelativeResourceRefs,
  referencedResourceNames,
} from '../inlineHtmlResources';

describe('isInlineableRelative', () => {
  it('接受相对路径', () => {
    expect(isInlineableRelative('style.css')).toBe(true);
    expect(isInlineableRelative('assets/main.css')).toBe(true);
  });
  it('拒绝绝对 URL / 协议相对 / data / 片段 / 穿越', () => {
    for (const href of [
      'https://cdn.example.com/a.css', 'http://x/a.css', '//cdn.example.com/a.css',
      'data:text/css,x', 'blob:https://x/a', '#anchor', '../etc/passwd', 'javascript:alert(1)',
    ]) {
      expect(isInlineableRelative(href), href).toBe(false);
    }
  });
});

describe('hasRelativeResourceRefs / referencedResourceNames', () => {
  const html = '<html><head><link rel="stylesheet" href="style.css"></head>'
    + '<body><img src="logo.png"><img src="https://cdn/x.png"></body></html>';
  it('检测相对资源引用', () => {
    expect(hasRelativeResourceRefs(html)).toBe(true);
    expect(hasRelativeResourceRefs('<html><body>纯文本</body></html>')).toBe(false);
  });
  it('只列相对资源文件名（去重、跳过绝对 URL）', () => {
    expect(referencedResourceNames(html)).toEqual(['style.css', 'logo.png']);
  });
});

describe('inlineHtmlResources', () => {
  it('把相对 CSS 内联成 <style>，抓取失败保留原样', async () => {
    const html = '<link rel="stylesheet" href="style.css">';
    const fetched: string[] = [];
    const result = await inlineHtmlResources(html, async (filename) => {
      fetched.push(filename);
      if (filename === 'style.css') return { text: 'body { color: red; }' };
      throw new Error('not found');
    });
    expect(fetched).toEqual(['style.css']);
    expect(result).toContain('<style data-inline-src="style.css">');
    expect(result).toContain('body { color: red; }');
  });

  it('跳过绝对 URL，不发起抓取', async () => {
    const html = '<link rel="stylesheet" href="https://cdn.example.com/a.css">';
    let called = false;
    const result = await inlineHtmlResources(html, async () => {
      called = true;
      return { text: 'x' };
    });
    expect(called).toBe(false);
    expect(result).toBe(html);
  });

  it('CSS 内容里的 </style> 被转义，避免提前闭合', async () => {
    const html = '<link rel="stylesheet" href="evil.css">';
    const result = await inlineHtmlResources(html, async () => ({
      text: '</style><script>alert(1)</script>',
    }));
    expect(result).toContain('<\\/style>');
    expect(result).not.toMatch(/<\/style><script>/);
  });

  it('没有相对引用时原样返回（不发抓取）', async () => {
    const html = '<html><body>no resources</body></html>';
    let called = false;
    const result = await inlineHtmlResources(html, async () => {
      called = true;
      return { text: 'x' };
    });
    expect(called).toBe(false);
    expect(result).toBe(html);
  });
});
