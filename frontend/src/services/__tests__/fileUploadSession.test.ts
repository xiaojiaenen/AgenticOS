/**
 * 上传必须携带 session_id 的运行时回归。
 *
 * 历史故障：uploadFile() 只 append('file', file)，后端因此把文件落到 legacy
 * 目录并返回 rel_path=null。orchestrator 把 file_path（绝对路径）交给模型，
 * 文档工具 file_to_md 只接受会话工作区内路径，必然报
 * 「路径必须位于 workspace 内」。图片还能看只是因为图片走直读盘绕过工具。
 *
 * 这里直接断言 FormData 的字段（fetch/XHR 的 body），比静态文本断言更可靠：
 * 覆盖 fetch（无 onProgress）与 XHR（有 onProgress，上传岛进度）两条路径，
 * 以及 uploadFiles 的透传与「无 sessionId 时兼容旧调用」。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { uploadFile, uploadFiles } from '../fileService';

const SUCCESS_BODY = JSON.stringify({
  filename: '报告.docx',
  size: 12,
  mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  file_path: '/app/data/workspaces/u1/sSession-1/uploads/abc123_报告.docx',
  rel_path: 'uploads/abc123_报告.docx',
});

function makeFile(): File {
  return new File(['dummy'], '报告.docx', {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  });
}

/** 录下 fetch 收到的 body（FormData），返回可重放的读取器。 */
function recordFetch() {
  const bodies: FormData[] = [];
  const fetchMock = vi.fn((_url: string, init: RequestInit) => {
    bodies.push(init.body as FormData);
    return Promise.resolve(
      new Response(SUCCESS_BODY, { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
  });
  vi.stubGlobal('fetch', fetchMock);
  return bodies;
}

/** 录下 XHR.send 收到的 body，并立即触发 onload 成功回调。 */
function recordXhr() {
  const bodies: FormData[] = [];
  class FakeXhr {
    timeout = 0;
    upload = { onprogress: null as ((e: { lengthComputable: boolean; total: number; loaded: number }) => void) | null };
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    ontimeout: (() => void) | null = null;
    responseText = SUCCESS_BODY;
    status = 200;
    open() {}
    setRequestHeader() {}
    send(body: FormData) {
      bodies.push(body);
      this.onload?.();
    }
  }
  vi.stubGlobal('XMLHttpRequest', FakeXhr);
  return bodies;
}

describe('uploadFile / uploadFiles 携带 session_id', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('fetch 路径（无 onProgress）：带 sessionId 时 FormData 含 session_id', async () => {
    const bodies = recordFetch();
    await uploadFile(makeFile(), undefined, 's-target-123');
    expect(bodies).toHaveLength(1);
    expect(bodies[0].get('file')).toBeInstanceOf(File);
    expect(bodies[0].get('session_id')).toBe('s-target-123');
  });

  it('XHR 路径（有 onProgress）：同样把 session_id 放进 FormData', async () => {
    const bodies = recordXhr();
    await uploadFile(makeFile(), () => {}, 's-target-456');
    expect(bodies).toHaveLength(1);
    expect(bodies[0].get('session_id')).toBe('s-target-456');
  });

  it('uploadFiles 把 sessionId 透传给每个文件', async () => {
    const bodies = recordFetch();
    await uploadFiles([makeFile(), makeFile()], undefined, 's-shared-session');
    expect(bodies).toHaveLength(2);
    for (const body of bodies) {
      expect(body.get('session_id')).toBe('s-shared-session');
    }
  });

  it('不传 sessionId 时保持旧调用兼容（不追加 session_id 字段）', async () => {
    const bodies = recordFetch();
    await uploadFile(makeFile());
    expect(bodies).toHaveLength(1);
    expect(bodies[0].has('session_id')).toBe(false);
  });

  it('空字符串 sessionId 视为无值，不追加字段', async () => {
    const bodies = recordFetch();
    await uploadFile(makeFile(), undefined, '');
    expect(bodies[0].has('session_id')).toBe(false);
  });
});
