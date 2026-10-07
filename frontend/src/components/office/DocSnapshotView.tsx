import React from 'react';
import { cn } from '../../lib/utils';

/**
 * 浏览器不支持 Univer 时的文档只读降级视图。
 *
 * 与表格的降级同构：内容照常展示（可滚动、可复制），并明确告知升级路径。
 * 注意快照字段名：IDocumentData 的正文在 body.dataStream，段落以 \r 分隔，
 * 标题层级在 body.paragraphs[].paragraphStyle.headingLevel —— 这里曾经
 * 因为字段名想当然渲染成空白页。
 */

type Snapshot = Record<string, unknown>;

type Paragraph = {
  startIndex: number;
  paragraphStyle?: { headingLevel?: number };
};

function readDocument(snapshot: Snapshot): { title: string; lines: { level: number; text: string }[] } {
  const body = (snapshot.body ?? {}) as {
    dataStream?: string;
    paragraphs?: Paragraph[];
  };
  const title = String(snapshot.title ?? '未命名文档');
  const stream = body.dataStream ?? '';
  const paragraphs = body.paragraphs ?? [];

  // dataStream 是 \r 分隔的整段文本，每个段落块记录自己在流里的起点
  const lines = paragraphs.map((para) => {
    const start = para.startIndex ?? 0;
    const end = stream.indexOf('\r', start);
    const text = stream.slice(start, end === -1 ? undefined : end);
    return { level: para.paragraphStyle?.headingLevel ?? 0, text };
  });

  if (lines.length === 0 && stream) {
    // 没有段落元数据时退化为整段拆行
    for (const text of stream.split('\r')) {
      if (text.trim()) lines.push({ level: 0, text });
    }
  }

  return { title, lines: lines.filter((line) => line.text.trim().length > 0) };
}

export const DocSnapshotView: React.FC<{
  snapshot: Snapshot;
  reason: string;
  browserHint: string;
}> = ({ snapshot, reason, browserHint }) => {
  const doc = React.useMemo(() => readDocument(snapshot), [snapshot]);

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-[var(--border-subtle)] bg-amber-50 px-5 py-3 text-sm text-amber-800">
        <p className="font-semibold">当前浏览器无法显示可编辑文档</p>
        <p className="mt-1 text-amber-700">
          {reason}。请升级到 {browserHint} 后重新打开，即可直接编辑。
          以下为只读内容，数据没有丢失。
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-8 py-6">
        <div className="mx-auto max-w-[46rem]">
          {doc.lines.map((line, index) => {
            if (line.level >= 4) {
              return (
                <h4 key={index} className="mt-4 text-sm font-semibold text-[var(--foreground)]">
                  {line.text}
                </h4>
              );
            }
            if (line.level === 3) {
              return (
                <h3 key={index} className="mt-5 text-base font-semibold text-[var(--foreground)]">
                  {line.text}
                </h3>
              );
            }
            if (line.level === 2) {
              return (
                <h2 key={index} className="mt-6 text-lg font-semibold tracking-tight text-[var(--foreground)]">
                  {line.text}
                </h2>
              );
            }
            if (line.level === 1) {
              return (
                <h1
                  key={index}
                  className={cn(
                    'mt-2 text-2xl font-semibold tracking-tight text-[var(--foreground)]',
                    index > 0 && 'mt-8',
                  )}
                >
                  {line.text}
                </h1>
              );
            }
            return (
              <p key={index} className="mt-3 text-sm leading-relaxed text-zinc-700">
                {line.text}
              </p>
            );
          })}
          {doc.lines.length === 0 && (
            <p className="text-sm text-[var(--muted-foreground)]">文档内容为空。</p>
          )}
        </div>
      </div>
    </div>
  );
};
