/**
 * 诊断测试：A2UI 按钮点击 → actionHandler 链路。
 * 只在排查期存在，用于定位「点击提交没反应」的断点。
 */
import { describe, expect, it } from 'vitest';
import { MessageProcessor } from '@a2ui/web_core/v0_9';
import { basicCatalog } from '@a2ui/web_core/v0_9/basic_catalog';

const SURFACE = 'form-diag';
const CATALOG = 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';

/** 与 backend/app/services/a2ui/builder.form_page 产出一致的消息序列。 */
function formMessages() {
  return [
    { version: 'v0.9', createSurface: { surfaceId: SURFACE, catalogId: CATALOG, sendDataModel: true } },
    {
      version: 'v0.9',
      updateComponents: {
        surfaceId: SURFACE,
        components: [
          { id: 'root', component: 'Column', children: ['title', 'name-label', 'name', 'submit'] },
          { id: 'title', component: 'Text', text: '登记', variant: 'h2' },
          { id: 'name-label', component: 'Text', text: '姓名' },
          { id: 'name', component: 'TextField', label: '姓名', value: { path: '/name' } },
          { id: 'submit-label', component: 'Text', text: '提交' },
          { id: 'submit', component: 'Button', child: 'submit-label', action: { event: { name: 'submit_form' } } },
        ],
      },
    },
    { version: 'v0.9', updateDataModel: { surfaceId: SURFACE, value: { name: '' } } },
  ];
}

describe('a2ui action chain', () => {
  it('form_page 消息序列能被 MessageProcessor 接受', () => {
    const p = new MessageProcessor([basicCatalog], () => {});
    expect(() => p.processMessages(formMessages() as never)).not.toThrow();
    expect(p.model.surfacesMap.size).toBe(1);
  });

  it('surface.dispatchAction 能把 action 冒泡到 actionHandler', async () => {
    const seen: Array<Record<string, unknown>> = [];
    const p = new MessageProcessor([basicCatalog], (action) => {
      seen.push(action as Record<string, unknown>);
    });
    p.processMessages(formMessages() as never);
    const surface = p.getSurface(SURFACE) as unknown as {
      dispatchAction: (payload: unknown, source: string) => Promise<void>;
    };
    expect(surface).toBeTruthy();
    await surface.dispatchAction({ event: { name: 'submit_form' } }, 'submit');
    expect(seen).toHaveLength(1);
    expect(seen[0].name).toBe('submit_form');
    expect(seen[0].surfaceId).toBe(SURFACE);
    expect(seen[0].sourceComponentId).toBe('submit');
  });
});
