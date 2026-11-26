/**
 * 创作画布 API：AI 生图/改图 + 本地图片处理。
 *
 * 端点带鉴权（require_perm），所以产物 URL 不能直接用 <img src>，
 * 需经 apiFetch 取成 blob 再转 objectURL（与 workspaceArtifacts 同理）。
 */
import { apiFetch } from './apiClient';

export type CanvasGenerateResult = {
  filename: string;
  url: string;
  size: number;
  model: string;
  mode: 'text_to_image' | 'image_to_image';
};

export type CanvasArtifact = {
  session_id: string;
  filename: string;
  url: string;
  size: number;
  created_at: number;
};

/** 列出当前用户所有真实图片产物（画布作品来源）。 */
export async function listCanvasArtifacts(): Promise<CanvasArtifact[]> {
  const res = await apiFetch<{ items: CanvasArtifact[]; total: number }>(
    '/api/v1/canvas/artifacts', {}, '加载画布作品失败',
  );
  return res.items ?? [];
}

export type CanvasProcessResult = {
  filename: string;
  url: string;
  format: string;
  width: number;
  height: number;
  size: number;
};

/** AI 生图 / 图生图（参考图可选）。 */
export async function canvasGenerate(params: {
  prompt: string;
  sessionId: string;
  size: 'square' | 'landscape' | 'portrait';
  reference?: File | null;
  strength?: number;
}): Promise<CanvasGenerateResult> {
  const form = new FormData();
  form.append('prompt', params.prompt);
  form.append('session_id', params.sessionId);
  form.append('size', params.size);
  if (params.reference) {
    form.append('reference', params.reference);
    form.append('strength', String(params.strength ?? 0.7));
  }
  return apiFetch<CanvasGenerateResult>('/api/v1/canvas/generate', {
    method: 'POST',
    body: form,
    timeoutMs: 200_000, // 生图最长 180s
  }, '生成图片失败');
}

/** 本地图片处理：crop / resize / compress / rotate / watermark / thumbnail。 */
export async function canvasProcess(params: {
  image: File;
  sessionId: string;
  operation: 'crop' | 'resize' | 'compress' | 'rotate' | 'watermark' | 'thumbnail';
  outputFormat?: string;
  quality?: number;
  crop?: { x: number; y: number; width: number; height: number };
  resize?: { width: number; height: number };
  thumbnail?: { width: number; height: number };
  degrees?: number;
  watermark?: string;
}): Promise<CanvasProcessResult> {
  const form = new FormData();
  form.append('image', params.image);
  form.append('session_id', params.sessionId);
  form.append('operation', params.operation);
  form.append('output_format', params.outputFormat ?? 'PNG');
  form.append('quality', String(params.quality ?? 85));
  if (params.crop) form.append('crop', JSON.stringify(params.crop));
  if (params.resize) form.append('resize', JSON.stringify(params.resize));
  if (params.thumbnail) form.append('thumbnail', JSON.stringify(params.thumbnail));
  if (params.degrees) form.append('degrees', String(params.degrees));
  if (params.watermark) form.append('watermark', params.watermark);
  return apiFetch<CanvasProcessResult>('/api/v1/canvas/process', {
    method: 'POST',
    body: form,
  }, '处理图片失败');
}

/** 带鉴权产物 URL → objectURL（供 <img src> 用）。调用方负责 revoke。 */
export async function canvasImageBlobUrl(url: string): Promise<string> {
  const blob = await apiFetch<Blob>(url, { responseType: 'blob' }, '加载图片失败');
  return URL.createObjectURL(blob);
}
