import { apiFetch } from './apiClient';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const UPLOAD_ENDPOINT = `${API_BASE_URL}/api/v1/files/upload`;
const PROBE_ENDPOINT = `${API_BASE_URL}/api/v1/files/probe`;

export type UploadedFile = {
  filename: string;
  size: number;
  mime_type: string;
  file_path: string;
};

export async function uploadFile(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch<UploadedFile>(
    UPLOAD_ENDPOINT,
    {
      method: 'POST',
      body: formData,
      timeoutMs: 120_000, // 大文件上传放宽超时
    },
    '文件上传失败',
  );
}

export async function uploadFiles(files: File[]): Promise<UploadedFile[]> {
  return Promise.all(files.map(uploadFile));
}

// ---------------------------------------------------------------------------
// 透明加密诊断
// ---------------------------------------------------------------------------

export type ProbeVerdict = {
  filename: string;
  size: number;
  /** plain = 明文（链路正常）；cipher = 密文（客户端读不到明文）；empty = 空文件 */
  kind: 'plain' | 'cipher' | 'empty';
  detail: string;
  /** 前 16 字节 hex，便于人工核对 */
  head: string;
  advice: string;
};

/**
 * 上传前诊断：判断客户端（浏览器）读到的是明文还是密文。
 *
 * 透明加密环境下，若浏览器在白名单内，读到的就是明文，服务端也会收到明文。
 * 若返回 cipher，说明浏览器不在白名单，普通 Web 上传拿不到明文。
 *
 * 不落盘，只在内存里看文件头，开销极小。可在首次上传时调一次。
 */
export async function probeEncryption(file: File): Promise<ProbeVerdict> {
  const formData = new FormData();
  formData.append('file', file);

  return apiFetch<ProbeVerdict>(
    PROBE_ENDPOINT,
    {
      method: 'POST',
      body: formData,
      timeoutMs: 30_000,
    },
    '加密诊断失败',
  );
}

/** 文件头魔数判定（纯前端版本，不发网络请求，用于即时反馈） */
const PLAIN_MAGIC: { bytes: number[]; label: string }[] = [
  { bytes: [0x50, 0x4b, 0x03, 0x04], label: 'OOXML 明文（xlsx / docx / pptx）' },
  { bytes: [0xd0, 0xcf, 0x11, 0xe0], label: 'OLE2 明文（xls / doc / ppt）' },
  { bytes: [0x25, 0x50, 0x44, 0x46], label: 'PDF 明文' },
  { bytes: [0x50, 0x4b, 0x05, 0x06], label: 'zip 空归档' },
];

/**
 * 本地判定浏览器读到的字节是不是明文，不发任何请求。
 * 用于拖入文件时立刻给出提示，避免用户白等一次上传。
 */
export async function probeLocally(file: File): Promise<{
  kind: 'plain' | 'cipher' | 'empty';
  detail: string;
  head: string;
}> {
  if (file.size === 0) {
    return { kind: 'empty', detail: '空文件', head: '' };
  }
  const buf = await file.slice(0, 16).arrayBuffer();
  const head = Array.from(new Uint8Array(buf));

  for (const m of PLAIN_MAGIC) {
    if (m.bytes.every((b, i) => head[i] === b)) {
      return {
        kind: 'plain',
        detail: m.label,
        head: head.map((b) => b.toString(16).toUpperCase().padStart(2, '0')).join(' '),
      };
    }
  }
  return {
    kind: 'cipher',
    detail: '未知魔数（可能是密文）',
    head: head.map((b) => b.toString(16).toUpperCase().padStart(2, '0')).join(' '),
  };
}
