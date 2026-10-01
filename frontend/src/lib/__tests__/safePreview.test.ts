import { describe, it, expect } from 'vitest';
import { sanitizeHtml, buildSandboxedHtmlDocument } from '../safePreview';

describe('sanitizeHtml', () => {
  it('移除 <script> 标签及其内容', () => {
    const out = sanitizeHtml('<p>ok</p><script>alert(1)</script>');
    expect(out).not.toContain('script');
    expect(out).not.toContain('alert(1)');
    expect(out).toContain('<p>ok</p>');
  });

  it('移除 <iframe> / <object> / <embed> / <form> 等标签', () => {
    const out = sanitizeHtml(
      '<iframe src="https://evil.example"></iframe><object data="x"></object><embed src="y"><form action="/steal"><input type="text"><button>go</button></form>',
    );
    expect(out).not.toMatch(/<iframe|<object|<embed|<form|<input|<button/i);
  });

  it('移除 on* 事件属性', () => {
    const out = sanitizeHtml('<div onclick="alert(1)" onmouseover="steal()" data-ok="1">text</div>');
    expect(out).not.toContain('onclick');
    expect(out).not.toContain('onmouseover');
    expect(out).toContain('data-ok');
  });

  it('拦截 javascript: / data:text/html URL，保留 https 与图片 data URL', () => {
    const out = sanitizeHtml(
      '<a href="javascript:alert(1)">x</a><a href="data:text/html,<b>y</b>">z</a><a href="https://example.com">ok</a><img src="data:image/png;base64,AAAA">',
    );
    expect(out).not.toContain('javascript:');
    expect(out).not.toContain('data:text/html');
    expect(out).toContain('https://example.com');
    expect(out).toContain('data:image/png');
  });

  it('空输入返回空字符串', () => {
    expect(sanitizeHtml('')).toBe('');
  });
});

describe('buildSandboxedHtmlDocument', () => {
  it('为片段补全 HTML 骨架并注入 CSP meta', () => {
    const out = buildSandboxedHtmlDocument('<p>hello</p>');
    expect(out).toContain('<!DOCTYPE html>');
    expect(out).toContain('Content-Security-Policy');
    expect(out).toContain('<body><p>hello</p></body>');
  });

  it('完整 HTML 文档在 <head> 内注入 CSP meta，不破坏原有结构', () => {
    const out = buildSandboxedHtmlDocument('<html><head><title>t</title></head><body><h1>hi</h1></body></html>');
    expect(out).toContain('<title>t</title>');
    expect(out).toContain('Content-Security-Policy');
    expect(out).toContain('<h1>hi</h1>');
  });

  it('剥离本地相对路径脚本（srcdoc 内无法解析），保留 http(s) 与内联脚本', () => {
    const out = buildSandboxedHtmlDocument(
      '<script src="./local.js"></script><script src="https://cdn.example/a.js"></script><script>inline()</script>',
    );
    expect(out).not.toContain('./local.js');
    expect(out).toContain('https://cdn.example/a.js');
    expect(out).toContain('inline()');
  });

  it('检测到 Chart 用法时注入 Chart.js CDN', () => {
    const out = buildSandboxedHtmlDocument('<canvas id="c"></canvas><script>new Chart(ctx, {})</script>');
    expect(out).toContain('chart.js@4.4.3');
  });
});
