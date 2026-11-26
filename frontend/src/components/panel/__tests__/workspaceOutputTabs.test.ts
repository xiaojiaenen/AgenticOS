/**
 * 会话工作区产物（html / csv / 图片…）进入侧栏产物链路的纯函数回归。
 *
 * 用户诉求：模型用 write_text_file("index.html") 写出的网页不在对话下方
 * 展示，只在文件面板里。这里锁定「什么算产物」「怎么收集成侧栏 tab」
 * 「计数口径」三件事，确保 A（footer 入口）与 B（侧栏自动展示）共用同一口径。
 */
import { describe, expect, it } from 'vitest';
import {
  collectDisplayableOutputs,
  countAllArtifacts,
  countMessageArtifacts,
  isDisplayableOutput,
  outputDownloadUrl,
  outputKind,
  type WorkspaceEntry,
} from '../../../lib/workspaceArtifacts';
import { collectMessageTabs, collectOutputTabs, collectTabs, panelTab } from '../tabs';
import type { Message } from '../../../types';

const file = (name: string, path = name, size = 100): WorkspaceEntry => ({
  name, path, type: 'file', size,
});
const dir = (name: string): WorkspaceEntry => ({ name, path: name, type: 'dir', size: null });

describe('workspaceArtifacts', () => {
  it('识别 html / csv / xlsx / json / txt / md / 图片，排除目录与其它文件', () => {
    expect(isDisplayableOutput(file('index.html'))).toBe(true);
    expect(isDisplayableOutput(file('report.xlsx', 'outputs/report.xlsx'))).toBe(true);
    expect(isDisplayableOutput(file('data.csv'))).toBe(true);
    expect(isDisplayableOutput(file('notes.md'))).toBe(true);
    expect(isDisplayableOutput(file('chart.png'))).toBe(true);
    expect(isDisplayableOutput(file('archive.zip'))).toBe(false);
    expect(isDisplayableOutput(dir('outputs'))).toBe(false);
    expect(isDisplayableOutput(file('.hidden.html'))).toBe(false);
  });

  it('输出类型口径：html / image / data', () => {
    expect(outputKind(file('index.html'))).toBe('html');
    expect(outputKind(file('a.htm'))).toBe('html');
    expect(outputKind(file('a.PNG'))).toBe('image');
    expect(outputKind(file('data.csv'))).toBe('data');
    expect(outputKind(file('book.xlsx'))).toBe('data');
  });

  it('collectDisplayableOutputs 去重（同一 path 只留一条）', () => {
    const entries = [
      file('index.html'),
      file('index.html'),
      file('data.csv', 'outputs/data.csv'),
      dir('outputs'),
    ];
    expect(collectDisplayableOutputs(entries).map((e) => e.path)).toEqual([
      'index.html',
      'outputs/data.csv',
    ]);
  });

  it('下载 URL 用带鉴权端点，路径片段做 URL 编码', () => {
    expect(outputDownloadUrl('s1', file('report', 'outputs/我的 报告.csv'))).toBe(
      '/api/v1/agent/sessions/s1/outputs/%E6%88%91%E7%9A%84%20%E6%8A%A5%E5%91%8A.csv',
    );
  });

  it('计数：消息产物 + 工作区产物，html 网页算一个产物', () => {
    const messages: Message[] = [{
      id: 'm1', role: 'model', text: '好了',
      pptArtifact: { status: 'ready', artifactId: 'ppt1' },
    }];
    expect(countMessageArtifacts(messages)).toBe(1);
    const outputs = [file('index.html'), file('data.csv'), dir('outputs')];
    expect(countAllArtifacts(messages, outputs)).toBe(3);
  });

  it('只统计 ready 的产物，跳过 generating 占位', () => {
    const messages: Message[] = [{
      id: 'm1', role: 'model', text: '',
      pptArtifact: { status: 'generating' },
      websiteArtifact: { status: 'ready' },
    }];
    expect(countMessageArtifacts(messages)).toBe(1);
  });
});

describe('sidebar tabs', () => {
  it('工作区 html / 图片 / 数据文件都变成 output tab，带稳定 id', () => {
    const outputs = [
      file('index.html'),
      file('a.png', 'outputs/a.png'),
      file('data.csv', 'outputs/data.csv'),
      file('ignored.zip'),
    ];
    const tabs = collectOutputTabs(outputs, 's1');
    expect(tabs.map((t) => t.id)).toEqual([
      'output:index.html', 'output:outputs/a.png', 'output:outputs/data.csv',
    ]);
    expect(tabs[0]).toMatchObject({
      kind: 'output', title: 'index.html', outputKind: 'html',
      url: '/api/v1/agent/sessions/s1/outputs/index.html',
    });
    expect(tabs[1].outputKind).toBe('image');
    expect(tabs[2].outputKind).toBe('data');
  });

  it('collectTabs 把消息产物与工作区产物合到一起，且按消息产物在前', () => {
    const messages: Message[] = [{
      id: 'm1', role: 'model', text: '',
      pptArtifact: { status: 'ready', artifactId: 'ppt1', title: 'PPT' },
    }];
    const tabs = collectTabs(messages, 's1', [file('index.html')]);
    expect(tabs.map((t) => t.kind)).toEqual(['ppt', 'output']);
  });

  it('collectMessageTabs 保持原有四类产物 + 图片附件口径', () => {
    const messages: Message[] = [{
      id: 'm1', role: 'model', text: '',
      pptArtifact: { status: 'ready', artifactId: 'ppt1' },
      websiteArtifact: { status: 'ready', artifactId: 'web1' },
      documentArtifact: { status: 'ready', artifactId: 'doc1' },
      sheetArtifact: { status: 'ready', artifactId: 'sheet1' },
      attachments: [{ name: 'a.png', type: 'image/png', url: 'data:...' }],
    }];
    expect(collectMessageTabs(messages, 's1').map((t) => t.kind)).toEqual([
      'ppt', 'website', 'document', 'sheet', 'image',
    ]);
  });

  it('panelTab 的产物库 id 稳定（自动打开侧栏用）', () => {
    expect(panelTab('artifacts')).toEqual({
      id: 'panel:artifacts', kind: 'artifacts', title: '会话产物',
    });
  });
});
