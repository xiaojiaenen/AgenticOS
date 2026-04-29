import React, { ChangeEvent, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import { AlertCircle, FileCode2, Loader2, Plus, Save, Trash2, Upload, X } from 'lucide-react';
import { Button } from '../ui/Button';
import { formatApiDate } from '../../lib/datetime';
import { cn } from '../../lib/utils';
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
  };
}

function shortRootDir(rootDir: string): string {
  if (!rootDir) return '-';
  const segments = rootDir.split(/[\\/]/).filter(Boolean);
  return segments.slice(-2).join('/') || rootDir;
}

export const SkillManagement = () => {
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
    const confirmed = window.confirm(`确认删除 Skill“${skill.name}”吗？`);
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
      setSkills((prev) => [saved, ...prev]);
      setUploadFileValue(null);
      setUploadSlug('');
      setMessage('Skill 包上传成功');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Skill 包上传失败');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="admin-page-stage space-y-5">
      <section className="admin-page-header">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="admin-section-kicker">Skill 管理</p>
            <h2 className="mt-2 text-2xl font-black tracking-tight text-slate-950">本地 Skill 目录</h2>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {message && (
              <div className="rounded-[22px] border border-emerald-100 bg-emerald-50 px-4 py-2 text-sm font-bold text-emerald-700">
                {message}
              </div>
            )}
            <div className="admin-kpi-pill">
              共 <span className="font-black text-slate-900">{skills.length}</span> 个 Skill
            </div>
            <div className="admin-kpi-pill">
              已启用 <span className="font-black text-slate-900">{enabledCount}</span>
            </div>
            <div className="admin-kpi-pill">
              含脚本 <span className="font-black text-slate-900">{pythonSkillCount}</span>
            </div>
            <Button variant="secondary" onClick={loadSkills} disabled={isLoading || isSaving || isUploading}>
              {isLoading ? <Loader2 size={16} className="animate-spin" /> : '重新加载'}
            </Button>
            <Button onClick={openCreateModal} disabled={isLoading || isSaving || isUploading} className="gap-2">
              <Plus size={16} />
              新建 Skill
            </Button>
          </div>
        </div>
      </section>

      {error && (
        <div className="flex items-center gap-2 rounded-[24px] border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-700">
          <AlertCircle size={18} />
          {error}
        </div>
      )}

      <section className="admin-data-panel">
        <div className="grid grid-cols-1 gap-4 border-b border-white/75 bg-white/44 px-6 py-5 xl:grid-cols-[minmax(0,1fr)_260px_auto] xl:items-end">
          <div className="text-center xl:text-left">
            <p className="admin-section-kicker">上传入口</p>
            <h3 className="mt-2 text-lg font-black tracking-tight text-slate-900">支持上传 Zip Skill 包</h3>
            <p className="mt-2 text-sm font-medium leading-6 text-slate-500">
              上传成功后会自动写入本地 Skill 目录，并出现在当前列表中。
            </p>
          </div>

          <label className="space-y-2">
            <span className="text-xs font-black tracking-[0.18em] text-slate-400">Slug 覆盖</span>
            <input
              value={uploadSlug}
              onChange={(event) => setUploadSlug(event.target.value)}
              placeholder="可选 slug"
              className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
            />
          </label>

          <div className="flex flex-col gap-3 sm:flex-row xl:justify-end">
            <input
              type="file"
              accept=".zip"
              onChange={handleFileChange}
              className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-700 outline-none sm:max-w-[300px]"
            />
            <Button onClick={handleUpload} disabled={!uploadFileValue || isUploading} className="gap-2">
              {isUploading ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}
              上传 Skill 包
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
          <div className="flex h-80 items-center justify-center gap-3 text-sm font-bold text-slate-400">
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
              className="admin-table-row grid grid-cols-1 gap-4 border-b border-slate-100/80 px-5 py-4 text-center xl:grid-cols-[minmax(240px,1.3fr)_100px_140px_160px_120px_170px] xl:items-center xl:gap-0"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-black text-slate-900">{skill.name}</p>
                <p className="mt-1 truncate text-xs font-black tracking-[0.14em] text-slate-400">{skill.slug}</p>
                <p className="mt-2 line-clamp-2 text-sm font-medium leading-6 text-slate-500">{skill.description || '暂无描述'}</p>
              </div>

              <div className="text-sm font-black text-slate-900">{skill.script_paths.length}</div>
              <div className="text-sm font-bold text-slate-600">{shortRootDir(skill.root_dir)}</div>
              <div className="text-sm font-bold text-slate-600">{formatApiDate(skill.updated_at)}</div>

              <div className="flex flex-wrap justify-center gap-2">
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1 text-[10px] font-black',
                    skill.enabled ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500',
                  )}
                >
                  {skill.enabled ? '启用' : '停用'}
                </span>
                {skill.has_python_scripts && (
                  <span className="rounded-full bg-amber-50 px-2.5 py-1 text-[10px] font-black text-amber-700">
                    Python
                  </span>
                )}
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="secondary" onClick={() => openEditModal(skill)} className="gap-2 bg-white/85" size="sm">
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
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-white/70 bg-white/70 text-slate-400 shadow-sm">
              <FileCode2 size={24} />
            </div>
            <p className="text-sm font-black text-slate-600">还没有 Skill</p>
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
              <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
                <div>
                  <p className="admin-section-kicker">{draft.id ? '编辑 Skill' : '新建 Skill'}</p>
                  <h3 className="mt-2 text-2xl font-black tracking-tight text-slate-900">{draft.name || '新 Skill'}</h3>
                </div>
                <button
                  type="button"
                  onClick={closeModal}
                  className="flex h-10 w-10 items-center justify-center rounded-2xl text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                >
                  <X size={18} />
                </button>
              </div>

              <div className="grid flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1fr)_340px]">
                <div className="overflow-y-auto p-6">
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <label className="space-y-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">名称</span>
                      <input
                        value={draft.name}
                        onChange={(event) => patchDraft({ name: event.target.value })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>
                    <label className="space-y-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">Slug</span>
                      <input
                        value={draft.slug || ''}
                        onChange={(event) => patchDraft({ slug: event.target.value })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>
                    <label className="space-y-2 lg:col-span-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">描述</span>
                      <input
                        value={draft.description}
                        onChange={(event) => patchDraft({ description: event.target.value })}
                        className="w-full rounded-[22px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>

                    <div className="flex items-center justify-between rounded-[24px] border border-white/80 bg-white/72 px-4 py-3 lg:col-span-2">
                      <div>
                        <p className="text-sm font-black text-slate-700">启用</p>
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

                    <label className="space-y-2 lg:col-span-2">
                      <span className="text-xs font-black tracking-[0.18em] text-slate-400">SKILL.md 正文</span>
                      <textarea
                        value={draft.instruction}
                        onChange={(event) => patchDraft({ instruction: event.target.value })}
                        rows={16}
                        className="w-full resize-y rounded-[24px] border border-white/75 bg-white/72 px-4 py-3 text-sm font-medium leading-6 text-slate-800 outline-none transition focus:border-sky-200 focus:bg-white focus:ring-4 focus:ring-sky-100/80"
                      />
                    </label>
                  </div>
                </div>

                <div className="overflow-y-auto border-l border-slate-100 bg-white/50 p-6">
                  <div className="rounded-[28px] border border-white/80 bg-white/82 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                    <div className="mb-4 flex items-center gap-2">
                      <FileCode2 size={18} className="text-slate-500" />
                      <h4 className="text-lg font-black text-slate-900">脚本清单</h4>
                    </div>
                    {draft.script_paths && draft.script_paths.length > 0 ? (
                      <div className="space-y-2">
                        {draft.script_paths.map((scriptPath) => (
                          <div
                            key={scriptPath}
                            className="rounded-[20px] border border-white/80 bg-white/75 px-3 py-2 text-sm font-bold text-slate-700"
                          >
                            {scriptPath}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="rounded-[22px] border border-dashed border-slate-200 bg-white/60 px-4 py-5 text-sm font-medium text-slate-500">
                        当前 Skill 的 `scripts/` 目录下还没有发现 Python 脚本。
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex flex-col gap-3 border-t border-slate-100 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
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
