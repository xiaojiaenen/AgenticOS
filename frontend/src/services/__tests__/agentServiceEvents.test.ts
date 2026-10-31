/**
 * SSE 分发层回归：chart 事件必须解包 {version, chart} 包裹。
 *
 * 线上事故：后端 chart 事件的消息是 {version, chart:{title, option}}，
 * 分发层直接把它断言成 {title, option} 存进 chartMessages ——
 * ChartMessage 读到的 title/option 全是 undefined，实时渲染出一张
 * 空白边框卡片（恢复路径做过解包，于是"实时空白、刷新后正常"）。
 */
import { describe, expect, it, vi } from 'vitest';
import { applyAgentEvent } from '../agentService';

type StreamState = Parameters<typeof applyAgentEvent>[3];

function makeState(): StreamState {
  return { sessionId: '', text: '', reasoningText: '', toolCalls: [], finishReason: null };
}

const OPTS = { sessionId: 's1' };

const CHART_OPTION = {
  title: { text: '任务量' },
  xAxis: { type: 'category', data: ['A', 'B'] },
  series: [{ type: 'bar', data: [3, 5] }],
};

describe('applyAgentEvent: chart 通道', () => {
  it('解包 {version, chart} 包裹格式，回调拿到 {title, option}', () => {
    const onChartMessages = vi.fn();
    const state = makeState();
    applyAgentEvent(
      'chart',
      {
        session_id: 's1',
        messages: [{ version: 'v0.9', chart: { title: '任务量', option: CHART_OPTION } }],
      },
      { ...OPTS, onChartMessages },
      state,
    );
    expect(onChartMessages).toHaveBeenCalledTimes(1);
    expect(state.chartMessages).toEqual([{ title: '任务量', option: CHART_OPTION }]);
  });

  it('多条图表累积、非法项剔除、扁平旧格式兼容', () => {
    const state = makeState();
    const opts = { ...OPTS, onChartMessages: vi.fn() };
    applyAgentEvent(
      'chart',
      {
        session_id: 's1',
        messages: [
          { version: 'v0.9', chart: { title: 'A', option: CHART_OPTION } },
          'garbage',
          { title: '扁平旧格式', option: CHART_OPTION },
          { version: 'v0.9' },
        ],
      },
      opts,
      state,
    );
    applyAgentEvent(
      'chart',
      { session_id: 's1', messages: [{ version: 'v0.9', chart: { title: 'B', option: CHART_OPTION } }] },
      opts,
      state,
    );
    expect(state.chartMessages).toEqual([
      { title: 'A', option: CHART_OPTION },
      { title: '扁平旧格式', option: CHART_OPTION },
      { title: 'B', option: CHART_OPTION },
    ]);
  });

  it('a2ui 事件保持累积、不做解包', () => {
    const state = makeState();
    const first = [{ version: 'v0.9', createSurface: { surfaceId: 's1' } }];
    const second = [{ version: 'v0.9', updateComponents: { surfaceId: 's1', components: [] } }];
    applyAgentEvent('a2ui', { session_id: 's1', messages: first }, OPTS, state);
    applyAgentEvent('a2ui', { session_id: 's1', messages: second }, OPTS, state);
    expect(state.a2uiMessages).toEqual([...first, ...second]);
  });
});
