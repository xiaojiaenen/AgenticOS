/**
 * 文件上传任务的状态容器（zustand）。
 *
 * 与 exportStore / deployStore 同构：上传由 `useChatStream.prepareUploadedFiles`
 * 发起（在 Chat 页深处的发送链路里），岛挂在 App 根。这里只存「正在上传哪些
 * 文件、各上传到多少字节」这一组事实。
 *
 * 多文件并行上传（uploadFiles 内部 Promise.all），岛显示的是聚合进度：
 * 总字节 / 总大小 —— 用户关心的是"还要等多久"，不是单个文件。
 */
import { create } from 'zustand';

export interface UploadFileJob {
  /** 原始文件名（展开视图显示）。 */
  name: string;
  /** 文件总字节数。 */
  total: number;
  /** 已上传字节数（XHR upload.onprogress 的真实值）。 */
  loaded: number;
}

interface FileUploadState {
  files: UploadFileJob[] | null;
  begin: (files: { name: string; total: number }[]) => void;
  /** 第 index 个文件的进度更新（0..1）。 */
  setProgress: (index: number, fraction: number) => void;
  finish: () => void;
}

export const useFileUploadStore = create<FileUploadState>((set) => ({
  files: null,
  begin: (files) =>
    set({
      files: files.map((f) => ({ name: f.name, total: Math.max(1, f.total), loaded: 0 })),
    }),
  setProgress: (index, fraction) =>
    set((s) => {
      if (!s.files || index >= s.files.length) return s;
      const files = [...s.files];
      files[index] = { ...files[index], loaded: Math.round(files[index].total * fraction) };
      return { files };
    }),
  finish: () => set({ files: null }),
}));
