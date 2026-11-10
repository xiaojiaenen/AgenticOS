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
        // 5.5：带 tool_calls 的过渡 assistant 落库时通常带思考内容，
        // 这里的 tool 信息附着在有 reasoning 的泡上而不是独立空泡
        reasoning_content: '选柱状图对比任务量',
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
    expect(msgs[1].reasoningText).toBe('选柱状图对比任务量');
    expect(msgs[2].text).toBe('柱状图已经出来了');
  });

  it('透传 reasoning_content 到 reasoningText', () => {
    const msgs = mapBackendMessages([assistant(undefined, { reasoning_content: '先想一下步骤' })]);
    expect(msgs[0].reasoningText).toBe('先想一下步骤');
  });

  it('5.5 空 assistant：无文本但有 reasoning/tool_calls 时保留（思考即可见内容）', () => {
    // "停止"打断的轮次：content 只有 '\n\n'，但 reasoning 落了库 ——
    // 气泡应显示思考+工具，而不是变空泡
    const raw: BackendMessage[] = [
      { role: 'user', content: '构建网站' },
      {
        role: 'assistant',
        content: '\n\n',
        tool_calls: [{ id: 'tc1', name: 'build_website', arguments: {} }],
        reasoning_content: '先复制模板再构建…',
      },
      { role: 'tool', tool_call_id: 'tc1', content: '构建完成' },
    ];
    const msgs = mapBackendMessages(raw);
    expect(msgs).toHaveLength(2);
    expect(msgs[1].reasoningText).toBe('先复制模板再构建…');
    expect(msgs[1].toolCalls).toHaveLength(1);
  });

  it('5.5 空 assistant：无文本/产物/思考的纯工具过渡泡被跳过', () => {
    const raw: BackendMessage[] = [
      { role: 'user', content: 'hi' },
      {
        role: 'assistant',
        content: '',
        tool_calls: [{ id: 'tc1', name: 'calc', arguments: {} }],
      },
      { role: 'tool', tool_call_id: 'tc1', content: '2' },
      assistant(undefined, { content: '答案是 2' }),
    ];
    const msgs = mapBackendMessages(raw);
    expect(msgs).toHaveLength(2);
    expect(msgs[1].text).toBe('答案是 2');
  });

  it('无 metadata 时不出 chartMessages / a2uiMessages 字段', () => {
    const msgs = mapBackendMessages([assistant()]);
    expect(msgs[0].chartMessages).toBeUndefined();
    expect(msgs[0].a2uiMessages).toBeUndefined();
  });
});
