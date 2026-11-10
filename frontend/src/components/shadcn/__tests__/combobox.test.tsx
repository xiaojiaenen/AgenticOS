/**
 * Combobox 回归：可搜索选择器。
 *
 * 背景：模型名动辄几十上百个，原来用的是不可搜索的 Select，只能靠滚。
 * 换成基于 cmdk 的组合框后，需要锁住几个关键行为 —— 尤其是「自由输入」
 * 那条：新建提供商时还没有目录，必须允许填列表外的值，否则用户根本没法
 * 配第一个模型。
 *
 * 渲染方式跟随本仓库既有约定（`react-dom/client` + `act`），不引入
 * @testing-library —— 项目里没有这个依赖。
 */
import { describe, expect, it, vi } from 'vitest';
import { createRoot, type Root } from 'react-dom/client';
import { act } from 'react';
import { Combobox } from '../combobox';

const OPTIONS = [
  { value: 'gpt-4o', label: 'gpt-4o', hint: 'text-generation' },
  { value: 'deepseek-chat', label: 'deepseek-chat', hint: 'text-generation' },
  { value: 'bge-m3', label: 'bge-m3', hint: 'embedding' },
];

// jsdom 没实现 scrollIntoView，cmdk 在选中项变化时会调用它。
// 不打这个桩，任何展开操作都会抛 "e.scrollIntoView is not a function"。
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

function mount(ui: React.ReactElement) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  act(() => root.render(ui));
  return {
    host,
    root,
    unmount: () => {
      act(() => root.unmount());
      host.remove();
    },
  };
}

function trigger(host: HTMLElement) {
  return host.querySelector('[role="combobox"]') as HTMLElement;
}

function open(host: HTMLElement) {
  act(() => {
    trigger(host).dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

describe('Combobox', () => {
  it('未选中时显示 placeholder', () => {
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="" onValueChange={() => {}} placeholder="选择模型" />,
    );
    expect(trigger(host).textContent).toContain('选择模型');
    unmount();
  });

  it('已选中时显示对应 label', () => {
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="deepseek-chat" onValueChange={() => {}} />,
    );
    expect(trigger(host).textContent).toContain('deepseek-chat');
    unmount();
  });

  it('allowCustom：值不在列表里时也能回显', () => {
    // 否则手填的内容在触发器上看不见，用户以为没填上
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="my-custom-model" onValueChange={() => {}} allowCustom />,
    );
    expect(trigger(host).textContent).toContain('my-custom-model');
    unmount();
  });

  it('非 allowCustom：值不在列表里时不回显（避免显示脏值）', () => {
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="ghost" onValueChange={() => {}} />,
    );
    expect(trigger(host).textContent).not.toContain('ghost');
    unmount();
  });

  it('disabled 时按钮被禁用', () => {
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="" onValueChange={() => {}} disabled />,
    );
    expect((trigger(host) as HTMLButtonElement).disabled).toBe(true);
    unmount();
  });

  it('展开后渲染选项列表（cmdk 挂到 body 的 portal 里）', () => {
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="" onValueChange={() => {}} />,
    );
    open(host);
    // cmdk 走 Portal，选项在 document.body 下而不在 host 内
    expect(document.body.textContent).toContain('gpt-4o');
    expect(document.body.textContent).toContain('bge-m3');
    unmount();
  });

  it('搜索框可过滤选项', () => {
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="" onValueChange={() => {}} />,
    );
    open(host);
    const input = document.querySelector('[cmdk-input]') as HTMLInputElement | null;
    expect(input).not.toBeNull();
    if (input) {
      act(() => {
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          'value',
        )?.set;
        setter?.call(input, 'deep');
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
      const items = Array.from(document.querySelectorAll('[cmdk-item]')).map(
        (el) => el.textContent ?? '',
      );
      expect(items.some((t) => t.includes('deepseek-chat'))).toBe(true);
      expect(items.some((t) => t.includes('gpt-4o'))).toBe(false);
    }
    unmount();
  });

  it('点选项回调 onValueChange', () => {
    const onChange = vi.fn();
    const { host, unmount } = mount(
      <Combobox options={OPTIONS} value="" onValueChange={onChange} />,
    );
    open(host);
    const item = Array.from(document.querySelectorAll('[cmdk-item]')).find((el) =>
      (el.textContent ?? '').includes('gpt-4o'),
    ) as HTMLElement | undefined;
    expect(item).toBeDefined();
    if (item) {
      act(() => {
        item.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      });
      expect(onChange).toHaveBeenCalledWith('gpt-4o');
    }
    unmount();
  });
});
