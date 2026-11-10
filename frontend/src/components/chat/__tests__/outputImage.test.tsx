/**
 * 回归：markdown 图片（`![alt](outputs/x.png)`）必须重写 src。
 *
 * 真实故障：模型生图后回「![AI大模型宣传图](outputs/img-xxx.png)」，
 * 界面显示成裂图。原因是 ReactMarkdown 默认渲染出
 * `<img src="outputs/img-xxx.png">` —— 相对路径，浏览器按**当前页面 URL**
 * 解析（如 `/chat/outputs/...`），必然 404。
 *
 * 工作区不在静态目录下，只能走带会话鉴权的
 * `/api/v1/agent/sessions/{sid}/outputs/{file}`。
 *
 * 同时锁住边界：外部图片（http/data:/blob:）不能被打成站内地址，
 * 否则用户贴的外链图会全挂。
 */
import { describe, expect, it } from 'vitest';
import { createRoot } from 'react-dom/client';
import { act } from 'react';
import { OutputImage } from '../markdownRenderParts';

function renderImg(props: { src?: string; alt?: string; sessionId?: string }) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root = createRoot(host);
  act(() => root.render(<OutputImage {...props} />));
  const img = host.querySelector('img');
  const result = { src: img?.getAttribute('src'), alt: img?.getAttribute('alt') };
  act(() => root.unmount());
  host.remove();
  return result;
}

describe('OutputImage', () => {
  it('工作区相对路径 → 带会话鉴权的端点', () => {
    const { src } = renderImg({
      src: 'outputs/img-7ec359d461.png',
      alt: 'AI大模型宣传图',
      sessionId: 'sess-123',
    });
    expect(src).toBe('/api/v1/agent/sessions/sess-123/outputs/img-7ec359d461.png');
  });

  it('容忍 ./outputs/ 与 /outputs/ 前缀', () => {
    expect(renderImg({ src: './outputs/a.png', sessionId: 's1' }).src).toBe(
      '/api/v1/agent/sessions/s1/outputs/a.png',
    );
    expect(renderImg({ src: '/outputs/a.png', sessionId: 's1' }).src).toBe(
      '/api/v1/agent/sessions/s1/outputs/a.png',
    );
  });

  it('外部 http 图片保持原样', () => {
    const url = 'https://example.com/cat.png';
    expect(renderImg({ src: url, sessionId: 's1' }).src).toBe(url);
  });

  it('data: / blob: 保持原样', () => {
    const dataUrl = 'data:image/png;base64,AAAA';
    expect(renderImg({ src: dataUrl, sessionId: 's1' }).src).toBe(dataUrl);
    const blobUrl = 'blob:http://localhost/uuid';
    expect(renderImg({ src: blobUrl, sessionId: 's1' }).src).toBe(blobUrl);
  });

  it('没有 sessionId 时不改写（保持原样，避免拼出半截地址）', () => {
    expect(renderImg({ src: 'outputs/a.png' }).src).toBe('outputs/a.png');
  });

  it('src 为空时不渲染', () => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => root.render(<OutputImage alt="x" />));
    expect(host.querySelector('img')).toBeNull();
    act(() => root.unmount());
    host.remove();
  });

  it('文件名做 URL 编码（防路径穿越与特殊字符）', () => {
    // 正则只放行 [A-Za-z0-9._-]，所以带斜杠的路径不会被当成工作区产物
    const { src } = renderImg({ src: 'outputs/../../etc/passwd.png', sessionId: 's1' });
    // 不匹配工作区正则 → 原样返回，不会被拼进鉴权端点
    expect(src).not.toContain('/agent/sessions/s1/outputs/');
  });
});
