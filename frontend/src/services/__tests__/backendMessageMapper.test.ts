/**
 * 会话历史加载的映射回归。
 *
 * 背景：后端把图表挂在 metadata.chart、把 A2UI 挂在 metadata.a2ui。
 * 之前这里只恢复 A2UI —— 图表"出图了但刷新一次就消失"。
 */
import { describe, expect, it } from 'vitest';
import { mapBackendMessages, type BackendMessage } from '../backendMessageMapper';

const CHART_OPTION = {
  title: { text: '任务量' },
  xAxis: { type: 'category', data: ['A', 'B'] },
  series: [{ type: 'bar', data: [3, 5] }],
};

function assistant(metadata?: Record<string, unknown>, extra: Partial<BackendMessage> = {}): BackendMessage {
  return { role: 'assistant', content: '好了', metadata, ...extra };
}

describe('mapBackendMessages', () => {
  it('恢复 metadata.chart 并解包 {version, chart} 包裹', () => {
    const raw = [
      assistant({
        chart: [{ version: 'v0.9', chart: { title: '任务量', option: CHART_OPTION } }],
      }),
    ];
    const msgs = mapBackendMessages(raw);
    expect(msgs).toHaveLength(1);
    expect(msgs[0].chartMessages).toEqual([{ title: '任务量', option: CHART_OPTION }]);
  });

  it('兼容已是扁平 {title, option} 的旧数据，并剔除非法项', () => {
    const raw = [
      assistant({
        chart: [
          { title: '旧格式', option: CHART_OPTION },
          'garbage',
          null,
          { version: 'v0.9' }, // 无 option，解不出来
        ],
      }),
    ];
    const msgs = mapBackendMessages(raw);
    expect(msgs[0].chartMessages).toEqual([{ title: '旧格式', option: CHART_OPTION }]);
  });

  it('恢复 metadata.a2ui', () => {
    const a2ui = [{ version: 'v0.9', createSurface: { surfaceId: 's1' } }];
    const msgs = mapBackendMessages([assistant({ a2ui })]);
    expect(msgs[0].a2uiMessages).toEqual(a2ui);
  });

  it('tool 消息合并进 assistant 的 toolCalls；system/tool 不单独出消息', () => {
    const raw: BackendMessage[] = [
      { role: 'system', content: 'You are helpful.' },
      { role: 'user', content: '画个图' },
      {
        role: 'assistant',
        content: '',
        tool_calls: [{ id: 'tc1', name: 'render_chart', arguments: { chart_type: 'bar' } }],
      },
      { role: 'tool', tool_call_id: 'tc1', content: '图表已生成' },
      assistant(undefined, { content: '柱状图已经出来了' }),
    ];
    const msgs = mapBackendMessages(raw);
    expect(msgs).toHaveLength(3);
    expect(msgs[0].role).toBe('user');
    expect(msgs[1].toolCalls).toEqual([
      { id: 'tc1', name: 'render_chart', status: 'success', arguments: { chart_type: 'bar' }, result: '图表已生成' },
    ]);
    expect(msgs[2].text).toBe('柱状图已经出来了');
  });

  it('无 metadata 时不出 chartMessages / a2uiMessages 字段', () => {
    const msgs = mapBackendMessages([assistant()]);
    expect(msgs[0].chartMessages).toBeUndefined();
    expect(msgs[0].a2uiMessages).toBeUndefined();
  });
});
