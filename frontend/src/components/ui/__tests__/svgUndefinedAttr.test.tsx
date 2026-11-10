/**
 * 复现「<circle> attribute cy: Expected length, "undefined"」。
 *
 * motion 的 `motion.circle` 自己用 setAttribute 落 SVG 静态属性（所以报错行
 * 落在 motion-vendor chunk），任何 cx/cy 为 undefined 的调用都会在浏览器里
 * 变成字符串 "undefined" 并触发该报错。这里直接换成对 setAttribute 的探针，
 * 比只看 React 告警更早定位。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react';

import { MascotCompanion } from '../MascotCompanion';
import { RandomMascot } from '../RandomMascot';

const PHASES = ['thinking', 'streaming', 'generating_ppt', 'rendering_ppt', 'done', 'error'] as const;

describe('SVG 坐标不得为 undefined', () => {
  const offenders: string[] = [];
  const original = Element.prototype.setAttribute;

  beforeEach(() => {
    offenders.length = 0;
    Element.prototype.setAttribute = function (name: string, value: string) {
      // 区分「真 undefined」与字符串 "undefined"：Sparkle 用模板串拼坐标，
      // 拿到 undefined 会变成字符串，同样是非法长度。
      if (value === undefined || value === null) {
        offenders.push(`${this.tagName.toLowerCase()}#${name}=<${typeof value}>`);
      } else if (value === 'undefined' || value === 'null') {
        offenders.push(`${this.tagName.toLowerCase()}#${name}="${value}"`);
      }
      return original.call(this, name, value);
    };
  });

  afterEach(() => {
    Element.prototype.setAttribute = original;
  });

  async function mount(node: React.ReactNode) {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(node);
    });
    await act(async () => {
      root.unmount();
    });
    host.remove();
  }

  for (const phase of PHASES) {
    it(`MascotCompanion(${phase}) 不写非法坐标`, async () => {
      await mount(<MascotCompanion phase={phase} />);
      expect(offenders.filter((o) => o.includes('#cx') || o.includes('#cy'))).toEqual([]);
    });
  }

  it('RandomMascot 不写非法坐标', async () => {
    await mount(<RandomMascot />);
    expect(offenders.filter((o) => o.includes('#cx') || o.includes('#cy'))).toEqual([]);
  });
});