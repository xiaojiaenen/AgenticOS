import { authHeaders } from './authService';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const UPLOAD_ENDPOINT = `${API_BASE_URL}/api/v1/files/upload`;

export type UploadedFile = {
  filename: string;
  size: number;
  mime_type: string;
  text_content: string;
  text_truncated: boolean;
  text_length: number;
};

export async function uploadFile(file: File): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(UPLOAD_ENDPOINT, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || '文件上传失败。');
  }

  return response.json();
}

export async function uploadFiles(files: File[]): Promise<UploadedFile[]> {
  return Promise.all(files.map(uploadFile));
}
