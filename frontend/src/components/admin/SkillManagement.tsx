import React, { ChangeEvent, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import { AlertCircle, FileCode2, Loader2, Plus, Save, Trash2, Upload, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { formatApiDate } from '../../lib/datetime';
import { cn } from '../../lib/utils';
import { useIsGlassTheme } from '../liquid-glass';
import {
 createSkill,
 deleteSkill,
 getSkills,
 Skill,
 SkillPayload,
 updateSkill,
 uploadSkill,
} from '../../services/skillService';
import { useAdminModalBackdrop } from './useAdminModalBackdrop';

type Draft = SkillPayload & {
 id?: number;
 root_dir?: string;
 has_python_scripts?: boolean;
 script_paths?: string[];
 has_references?: boolean;
 reference_paths?: string[];
};

const emptyInstruction =
 '请说明这个 Skill 适合在什么场景下使用、如何使用，以及什么情况下允许调用 scripts。';

function makeDraft(skill: Skill | null): Draft {
 if (skill) {
  return {
   id: skill.id,
   name: skill.name,
   slug: skill.slug,
   description: skill.description,
   enabled: skill.enabled,
   instruction: skill.instruction,
   root_dir: skill.root_dir,
   has_python_scripts: skill.has_python_scripts,
   script_paths: skill.script_paths,
   has_references: skill.has_references,
   reference_paths: skill.reference_paths,
  };
 }

 return {
  name: '新 Skill',
  slug: '',
  description: '',
  enabled: true,
  instruction: emptyInstruction,
  root_dir: '',
  has_python_scripts: false,
  script_paths: [],
  has_references: false,
  reference_paths: [],
 };
}

function shortRootDir(rootDir: string): string {
 if (!rootDir) return '-';
 const segments = rootDir.split(/[\\/]/).filter(Boolean);
 return segments.slice(-2).join('/') || rootDir;
}

export const SkillManagement = () => {
 const isGlass = useIsGlassTheme();
 const [skills, setSkills] = useState<Skill[]>([]);
 const [draft, setDraft] = useState<Draft | null>(null);
 const [isModalOpen, setIsModalOpen] = useState(false);
 const [isLoading, setIsLoading] = useState(true);
 const [isSaving, setIsSaving] = useState(false);
 const [isUploading, setIsUploading] = useState(false);
 const [error, setError] = useState<string | null>(null);
 const [message, setMessage] = useState<string | null>(null);
 const [uploadFileValue, setUploadFileValue] = useState<File | null>(null);
 const [uploadSlug, setUploadSlug] = useState('');
 useAdminModalBackdrop(isModalOpen);

 const enabledCount = useMemo(() => skills.filter((skill) => skill.enabled).length, [skills]);
 const pythonSkillCount = useMemo(() => skills.filter((skill) => skill.has_python_scripts).length, [skills]);
 const referenceSkillCount = useMemo(() => skills.filter((skill) => skill.has_references).length, [skills]);

 const loadSkills = async () => {
  setIsLoading(true);
  setError(null);
  try {
   const response = await getSkills();
   setSkills(response.items);
  } catch (err) {
   setError(err instanceof Error ? err.message : 'Skill 列表加载失败');
  } finally {
   setIsLoading(false);
  }
 };

 useEffect(() => {
  loadSkills();
 }, []);

 const openCreateModal = () => {
  setDraft(makeDraft(null));
  setMessage(null);
  setError(null);
  setIsModalOpen(true);
 };

 const openEditModal = (skill: Skill) => {
  setDraft(makeDraft(skill));
  setMessage(null);
  setError(null);
  setIsModalOpen(true);
 };

 const closeModal = () => {
  if (isSaving || isUploading) return;
  setIsModalOpen(false);
  setDraft(null);
 };

 useEffect(() => {
  if (!isModalOpen) return;
  const handleKey = (e: KeyboardEvent) => {
   if (e.key === 'Escape') closeModal();
  };
  window.addEventListener('keydown', handleKey);
  return () => window.removeEventListener('keydown', handleKey);
 }, [isModalOpen, isSaving, isUploading]);

 const patchDraft = (patch: Partial<Draft>) => {
  setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
 };

 const saveDraft = async () => {
  if (!draft) return;
  setIsSaving(true);
  setError(null);
  setMessage(null);
  try {
   const payload: SkillPayload = {
    name: draft.name,
    slug: draft.slug || undefined,
    description: draft.description,
    enabled: draft.enabled,
    instruction: draft.instruction,
   };
   const saved = draft.id ? await updateSkill(draft.id, payload) : await createSkill(payload);
   setSkills((prev) => (draft.id ? prev.map((item) => (item.id === saved.id ? saved : item)) : [saved, ...prev]));
   setMessage('Skill 已保存');
   setIsModalOpen(false);
   setDraft(null);
  } catch (err) {
   setError(err instanceof Error ? err.message : 'Skill 保存失败');
  } finally {
   setIsSaving(false);
  }
 };

 const removeSkill = async (skill: Skill) => {
  const confirmed = window.confirm("确认删除 Skill“${skill.name}”吗？");
  if (!confirmed) return;
  setIsSaving(true);
  setError(null);
  try {
   await deleteSkill(skill.id);
   setSkills((prev) => prev.filter((item) => item.id !== skill.id));
   setMessage('Skill 已删除');
  } catch (err) {
   setError(err instanceof Error ? err.message : 'Skill 删除失败');
  } finally {
   setIsSaving(false);
  }
 };

 const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
  setUploadFileValue(event.target.files?.[0] ?? null);
 };

 const handleUpload = async () => {
  if (!uploadFileValue) return;
  setIsUploading(true);
  setError(null);
  setMessage(null);
  try {
   const saved = await uploadSkill(uploadFileValue, uploadSlug || undefined, true);
   if ('items' in saved) {
    // 多 skill 批量上传
    setSkills((prev) => [...saved.items, ...prev]);
    setUploadFileValue(null);
    setUploadSlug('');
    setMessage(`成功上传 ${saved.count} 个 Skill`);
   } else {
    // 单 skill 上传
    setSkills((prev) => [saved, ...prev]);
    setUploadFileValue(null);
    setUploadSlug('');
    setMessage('Skill 包上传成功');
   }
  } catch (err) {
   setError(err instanceof Error ? err.message : 'Skill 包上传失败');
  } finally {
   setIsUploading(false);
  }
 };

 return (
  <div className="admin-page-stage space-y-4">
   <section className="admin-page-header">
    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
     <div>
      <p className="admin-section-kicker">Skill 管理</p>
      <h2 className="mt-1.5 text-xl font-semibold tracking-tight text-slate-950">本地 Skill 目录</h2>
     </div>

     <div className="flex flex-wrap items-center gap-2">
      {message && (
       <div className="rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
        {message}
       </div>
      )}
      <div className="admin-kpi-pill">
       共 <span className="font-semibold text-slate-900">{skills.length}</span> 个
      </div>
      <div className="admin-kpi-pill">
       启用 <span className="font-semibold text-slate-900">{enabledCount}</span>
      </div>
      <div className="admin-kpi-pill">
       脚本 <span className="font-semibold text-slate-900">{pythonSkillCount}</span>
      </div>
      <div className="admin-kpi-pill">
       参考 <span className="font-semibold text-slate-900">{referenceSkillCount}</span>
      </div>
      <Button variant="secondary" onClick={loadSkills} disabled={isLoading || isSaving || isUploading} size="sm">
       {isLoading ? <Loader2 size={14} className="animate-spin" /> : '刷新'}
      </Button>
      <Button onClick={openCreateModal} disabled={isLoading || isSaving || isUploading} size="sm" className="gap-1.5">
       <Plus size={14} />
       新建
      </Button>
     </div>
    </div>
   </section>

   {error && (
    <div className="flex items-center gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs font-medium text-rose-700">
     <AlertCircle size={16} />
     {error}
    </div>
   )}

   <section className="admin-data-panel">
    <div className="grid grid-cols-1 gap-4 border-b border-slate-200/80 bg-[linear-gradient(135deg,rgba(255,255,255,0.45),rgba(248,250,252,0.32))] px-5 py-4 xl:grid-cols-[minmax(0,1fr)_200px_auto] xl:items-end">
     <div className="text-center xl:text-left">
      <p className="admin-section-kicker">上传入口</p>
      <h3 className="mt-1.5 text-base font-semibold tracking-tight text-slate-900">上传 Zip Skill 包</h3>
      <p className="mt-1.5 text-xs font-medium leading-5 text-slate-500">
       上传成功后自动写入本地目录并出现在列表中
      </p>
     </div>

     <label className="space-y-1.5">
      <span className="text-[11px] font-semibold tracking-[0.08em] text-slate-400">Slug 覆盖</span>
      <input
       value={uploadSlug}
       onChange={(event) => setUploadSlug(event.target.value)}
       placeholder="可选 slug"
       className="w-full rounded-lg border border-slate-200/80 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80 placeholder:text-slate-300"
      />
     </label>

     <div className="flex flex-col gap-2.5 sm:flex-row xl:justify-end">
      <label className="w-full rounded-lg border-2 border-dashed border-sky-200/70 bg-[linear-gradient(135deg,rgba(255,255,255,0.55),rgba(240,249,255,0.35))] px-3.5 py-2.5 text-sm font-semibold text-slate-500 transition-all hover:border-sky-300 hover:bg-sky-50/50 cursor-pointer sm:max-w-[260px]">
       <span className="truncate block">{uploadFileValue ? uploadFileValue.name : '选择 Zip...'}</span>
       <input
        type="file"
        accept=".zip"
        onChange={handleFileChange}
        className="hidden"
       />
      </label>
      <Button onClick={handleUpload} disabled={!uploadFileValue || isUploading} size="sm" className="gap-1.5">
       {isUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
       上传
      </Button>
     </div>
    </div>

    <div className="admin-table-head grid-cols-[minmax(240px,1.3fr)_100px_140px_160px_120px_170px]">
     <span>Skill</span>
     <span>脚本数</span>
     <span>目录</span>
     <span>更新时间</span>
     <span>状态</span>
     <span>操作</span>
    </div>

    {isLoading ? (
     <div className="flex h-80 items-center justify-center gap-3 text-sm font-medium text-slate-400">
      <Loader2 size={18} className="animate-spin" />
      正在加载 Skill
     </div>
    ) : skills.length > 0 ? (
     skills.map((skill, index) => (
      <motion.div
       key={skill.id}
       initial={{ opacity: 0, y: 8 }}
       animate={{ opacity: 1, y: 0 }}
       transition={{ duration: 0.22, delay: Math.min(index * 0.025, 0.16) }}
       whileHover={{ x: 2 }}
       className="admin-table-row grid grid-cols-1 gap-4 border-b border-slate-100/80 px-4 py-3 text-center xl:grid-cols-[minmax(240px,1.3fr)_100px_140px_160px_120px_170px] xl:items-center xl:gap-0"
      >
       <div className="min-w-0">
        <p className="truncate text-sm font-semibold text-slate-900">{skill.name}</p>
        <p className="mt-1 truncate text-xs font-semibold tracking-[0.08em] text-slate-400">{skill.slug}</p>
        <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-slate-500">{skill.description || '暂无描述'}</p>
       </div>

       <div className="text-sm font-semibold text-slate-900">{skill.script_paths.length}</div>
       <div className="text-sm font-medium text-slate-600">{shortRootDir(skill.root_dir)}</div>
       <div className="text-sm font-medium text-slate-600">{formatApiDate(skill.updated_at)}</div>

       <div className="flex flex-wrap justify-center gap-2">
        <span
         className={cn(
          'admin-status-pill',
          skill.enabled ? 'active' : 'inactive',
         )}
        >
         {skill.enabled ? '启用' : '停用'}
        </span>
        {skill.has_python_scripts && (
         <span className="admin-status-pill warning">
          Python
         </span>
        )}
        {skill.has_references && (
         <span className="admin-status-pill info">
          refs
         </span>
        )}
       </div>

       <div className="flex flex-wrap justify-center gap-2">
        <Button variant="secondary" onClick={() => openEditModal(skill)} className="gap-2 bg-white" size="sm">
         <FileCode2 size={15} />
         编辑
        </Button>
        <Button variant="danger" onClick={() => removeSkill(skill)} className="gap-2" size="sm">
         <Trash2 size={15} />
         删除
        </Button>
       </div>
      </motion.div>
     ))
    ) : (
     <div className="flex h-80 flex-col items-center justify-center text-center">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-slate-200/80 bg-white text-slate-400 shadow-sm">
       <FileCode2 size={20} />
      </div>
      <p className="text-sm font-semibold text-slate-600">还没有 Skill</p>
      <p className="mt-1 text-xs font-medium text-slate-400">你可以先创建一个本地 Skill，或者直接上传 Zip Skill 包。</p>
     </div>
    )}
   </section>

   {typeof document !== 'undefined' && createPortal(
    <AnimatePresence>
     {isModalOpen && draft && (
     <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="admin-modal-shell"
      onMouseDown={closeModal}
     >
      <motion.div
       initial={{ opacity: 0, y: 20, scale: 0.97 }}
       animate={{ opacity: 1, y: 0, scale: 1 }}
       exit={{ opacity: 0, y: 20, scale: 0.97 }}
       transition={{ duration: 0.22 }}
       onMouseDown={(event) => event.stopPropagation()}
       className="admin-solid-panel admin-modal-panel flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden"
      >
       <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
        <div>
         <p className="admin-section-kicker">{draft.id ? '编辑 Skill' : '新建 Skill'}</p>
         <h3 className="mt-1.5 text-xl font-semibold tracking-tight text-slate-900">{draft.name || '新 Skill'}</h3>
        </div>
        <button
         type="button"
         onClick={closeModal}
         className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600"
        >
         <X size={18} />
        </button>
       </div>

       <div className="grid flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="overflow-y-auto p-5">
         <div className="grid grid-cols-1 gap-3.5 lg:grid-cols-2">
          <label className="space-y-1.5">
           <span className="text-xs font-semibold tracking-[0.08em] text-slate-400">名称</span>
           <input
            value={draft.name}
            onChange={(event) => patchDraft({ name: event.target.value })}
            className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
           />
          </label>
          <label className="space-y-1.5">
           <span className="text-xs font-semibold tracking-[0.08em] text-slate-400">Slug</span>
           <input
            value={draft.slug || ''}
            onChange={(event) => patchDraft({ slug: event.target.value })}
            className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
           />
          </label>
          <label className="space-y-1.5 lg:col-span-2">
           <span className="text-xs font-semibold tracking-[0.08em] text-slate-400">描述</span>
           <input
            value={draft.description}
            onChange={(event) => patchDraft({ description: event.target.value })}
            className="w-full rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
           />
          </label>

          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 lg:col-span-2">
           <div>
            <p className="text-sm font-semibold text-slate-700">启用</p>
            {draft.root_dir && <p className="mt-1 text-xs font-medium text-slate-500">{draft.root_dir}</p>}
           </div>
           <button
            type="button"
            onClick={() => patchDraft({ enabled: !draft.enabled })}
            className={cn(
             'flex h-8 w-14 items-center rounded-full p-1 transition-all',
             draft.enabled ? 'justify-end bg-slate-900' : 'justify-start bg-slate-200',
            )}
           >
            <span className="h-6 w-6 rounded-full bg-white shadow-sm" />
           </button>
          </div>

          <label className="space-y-1.5 lg:col-span-2">
           <span className="text-xs font-semibold tracking-[0.08em] text-slate-400">SKILL.md 正文</span>
           <textarea
            value={draft.instruction}
            onChange={(event) => patchDraft({ instruction: event.target.value })}
            rows={16}
            className="w-full resize-y rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm font-medium leading-6 text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
           />
          </label>
         </div>
        </div>

        <div className="overflow-y-auto border-l border-slate-100 bg-[linear-gradient(135deg,rgba(255,255,255,0.55),rgba(248,250,252,0.42))] p-5 space-y-3.5">
         <div className="rounded-lg border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.88),rgba(248,250,252,0.72))] p-4 shadow-md">
          <div className="mb-3 flex items-center gap-2.5">
           <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-amber-50 text-amber-600 shadow-sm ring-1 ring-amber-100">
            <FileCode2 size={16} />
           </div>
           <h4 className="text-base font-semibold text-slate-900">脚本清单</h4>
          </div>
          {draft.script_paths && draft.script_paths.length > 0 ? (
           <div className="space-y-2">
            {draft.script_paths.map((scriptPath) => (
             <div
              key={scriptPath}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-mono font-medium text-slate-700 shadow-sm transition-all hover:bg-white hover:shadow-md"
             >
              {scriptPath}
             </div>
            ))}
           </div>
          ) : (
           <div className="rounded-lg border border-dashed border-slate-200/80 bg-white/80 px-4 py-5 text-sm font-medium text-slate-400">
            当前 Skill 的 scripts/ 目录下还没有发现 Python 脚本。
           </div>
          )}
         </div>

         <div className="rounded-lg border border-slate-200 bg-[linear-gradient(135deg,rgba(255,255,255,0.88),rgba(248,250,252,0.72))] p-4 shadow-md">
          <div className="mb-3 flex items-center gap-2.5">
           <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-sky-50 text-sky-600 shadow-sm ring-1 ring-sky-100">
            <FileCode2 size={16} />
           </div>
           <h4 className="text-base font-semibold text-slate-900">References</h4>
          </div>
          {draft.reference_paths && draft.reference_paths.length > 0 ? (
           <div className="space-y-2">
            {draft.reference_paths.map((referencePath) => (
             <div
              key={referencePath}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-mono font-medium text-slate-700 shadow-sm transition-all hover:bg-white hover:shadow-md"
             >
              {referencePath}
             </div>
            ))}
           </div>
          ) : (
           <div className="rounded-lg border border-dashed border-slate-200/80 bg-white/80 px-4 py-5 text-sm font-medium text-slate-400">
            当前 Skill 的 references/ 目录下还没有发现参考文件。
           </div>
          )}
         </div>
        </div>
       </div>

       <div className="flex flex-col gap-3 border-t border-slate-100 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-medium text-slate-500">保存后将更新当前 Skill 配置。</p>
        <div className="flex items-center gap-3">
         <Button type="button" variant="secondary" onClick={closeModal} disabled={isSaving}>
          取消
         </Button>
         <Button type="button" onClick={saveDraft} disabled={isSaving} className="gap-2">
          {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          保存 Skill
         </Button>
        </div>
       </div>
      </motion.div>
     </motion.div>
     )}
    </AnimatePresence>,
    document.body,
   )}
  </div>
 );
};
