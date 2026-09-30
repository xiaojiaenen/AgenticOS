import { apiFetch } from './apiClient';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const UPLOAD_ENDPOINT = `${API_BASE_URL}/api/v1/files/upload`;

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
