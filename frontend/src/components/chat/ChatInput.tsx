import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Square, Wand2, Undo2 } from 'lucide-react';
import { toast } from 'sonner';
import { AgentProfile } from '../../services/agentProfileService';
import { cn } from '../../lib/utils';
import { AgentSelector } from '../ui/AgentSelector';
import { PaperclipIcon, SendIcon } from '../ui/AnimatedIcons';
import { useInputSuggest } from '../../hooks/useInputSuggest';
import { ApprovalModeSelector } from './ApprovalModeSelector';
import { PlanModeToggle } from './PlanModeToggle';
import { polishPrompt } from '../../services/agentService';

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: (text: string, files?: File[]) => void;
  onStop?: () => void;
  isLoading: boolean;
  className?: string;
  placeholder?: string;
  chatMode: 'general' | 'ppt' | 'website' | 'email' | 'bigdata';
  setChatMode: (mode: 'general' | 'ppt' | 'website' | 'email' | 'bigdata') => void;
  agentProfiles?: AgentProfile[];
  selectedAgentProfileId?: number | null;
  onAgentProfileChange?: (profile: AgentProfile | null) => void;
  isModeLocked?: boolean;
  /** 会话级审批模式 */
  approvalMode?: 'ask' | 'auto' | 'full';
  onApprovalModeChange?: (mode: 'ask' | 'auto' | 'full') => void;
  planMode?: boolean;
  onPlanModeChange?: (on: boolean) => void;
  isAdmin?: boolean;
}

export interface ChatInputHandle {
  addFiles: (newFiles: File[]) => void;
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(({
  value,
  onChange,
  onSend,
  onStop,
  isLoading,
  className,
  placeholder = '输入你想聊的内容...',
  chatMode,
  setChatMode,
  agentProfiles = [],
  selectedAgentProfileId,
  onAgentProfileChange,
  isModeLocked = false,
  approvalMode = 'ask',
  onApprovalModeChange,
  planMode = false,
  onPlanModeChange,
  isAdmin = false,
}, ref) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const { suggestion, onChange: suggestOnChange, accept, dismiss } = useInputSuggest();  useImperativeHandle(ref, () => ({
    addFiles: (newFiles: File[]) => setFiles((prev) => [...prev, ...newFiles]),
  }));

  useEffect(() => {
    if (!textareaRef.current) return;
    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
  }, [value]);

  useEffect(() => {
    const nextPreviews = files.map((file) => (file.type.startsWith('image/') ? URL.createObjectURL(file) : ''));
    setPreviews(nextPreviews);
    return () => nextPreviews.forEach((url) => { if (url) URL.revokeObjectURL(url); });
  }, [files]);

  const handleInternalSend = React.useCallback(() => {
    if ((!value.trim() && files.length === 0) || isLoading) return;
    onSend(value, files);
    setFiles([]);
  }, [files, isLoading, onSend, value]);

  // ── 提示词润色 ──
  // idle：显示「润色」；loading：转圈（点击=取消）；polished：显示「取消润色」还原原文
  const [polishState, setPolishState] = useState<'idle' | 'loading' | 'polished'>('idle');
  const polishOriginalRef = useRef<string>('');
  const polishedRef = useRef<string>('');
  const polishAbortRef = useRef<AbortController | null>(null);

  // 文本被手动改动后不再处于「已润色」状态，避免取消按钮还原到过期原文
  useEffect(() => {
    if (polishState === 'polished' && value !== polishedRef.current) {
      setPolishState('idle');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  useEffect(() => () => polishAbortRef.current?.abort(), []);

  const handlePolish = React.useCallback(async () => {
    const raw = value.trim();
    if (!raw || isLoading) return;

    // 二次点击 = 取消润色
    if (polishState === 'loading') {
      polishAbortRef.current?.abort();
      return;
    }
    if (polishState === 'polished') {
      onChange(polishOriginalRef.current);
      setPolishState('idle');
      return;
    }

    polishOriginalRef.current = raw;
    const controller = new AbortController();
    polishAbortRef.current = controller;
    setPolishState('loading');
    try {
      const result = await polishPrompt(raw, controller.signal);
      if (controller.signal.aborted) return;
      if (!result.polished || !result.changed) {
        toast('提示词已经足够清晰，无需润色');
        setPolishState('idle');
        return;
      }
      polishedRef.current = result.polished;
      onChange(result.polished);
      setPolishState('polished');
      toast('已润色，可点「取消润色」还原');
    } catch (error) {
      if (controller.signal.aborted) return;
      console.error('polish prompt failed:', error);
      toast.error('润色失败，已保留原文');
      setPolishState('idle');
    } finally {
      if (polishAbortRef.current === controller) polishAbortRef.current = null;
    }
  }, [isLoading, onChange, polishState, value]);

  const handleChange = React.useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    onChange(val);
    suggestOnChange(val);
  }, [onChange, suggestOnChange]);

  const handleKeyDown = React.useCallback((e: React.KeyboardEvent) => {
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (nativeEvent.isComposing || e.key === 'Process') return;

    // Tab 接受补全建议
    if (e.key === 'Tab') {
      const currentSuggestion = suggestion;
      if (currentSuggestion) {
        e.preventDefault();
        e.stopPropagation();
        const accepted = accept();
        onChange(accepted);
        return;
      }
    }

    // Esc 关闭建议
    if (e.key === 'Escape' && suggestion) {
      e.preventDefault();
      dismiss();
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleInternalSend();
    }
  }, [handleInternalSend, suggestion, accept, dismiss, onChange]);

  const handleFileChange = React.useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    // 重置 input value，否则同一文件再次选择不会触发 onChange
    e.target.value = '';
  }, []);

  const handleDragOver = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  }, []);

  const removeFile = React.useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const selectableAgents = agentProfiles.filter((agent) => agent.listed !== false);

  return (
    <div
      className={cn('relative flex flex-col gap-2 p-2', isDragging && 'rounded-3xl bg-[var(--surface-2)] ring-2 ring-slate-300 ring-dashed', className)}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <AnimatePresence>
        {files.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="mb-1 flex flex-wrap gap-3 px-2">
            {files.map((file, idx) => (
              <motion.div layout key={`${file.name}-${idx}`} className={cn(
                "group relative h-16 w-16 overflow-hidden rounded-xl border shadow-sm",
                "border-[var(--border-subtle)] bg-[var(--surface-1)] border shadow-sm"
              )}>
                {previews[idx] ? (
                  <img src={previews[idx]} alt="preview" loading="lazy" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center bg-[var(--surface-2)] p-1 text-center text-[8px]">
                    <PaperclipIcon size={12} className="mb-1 text-[var(--muted-foreground)]" />
                    <span className="w-full truncate">{file.name.split('.').pop()?.toUpperCase()}</span>
                  </div>
                )}
                <button
                  onClick={() => removeFile(idx)}
                  className="absolute -right-1 -top-1 scale-75 rounded-full bg-rose-500 p-1 text-white opacity-0 shadow-sm transition-opacity hover:bg-rose-600 group-hover:opacity-100"
                  aria-label="移除文件"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M18 6L6 18M6 6l12 12" /></svg>
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <input type="file" multiple ref={fileInputRef} onChange={handleFileChange} className="hidden" accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.txt,.md,.py,.js,.ts,.tsx,.jsx,.json,.yaml,.yml,.xml,.html,.css,.svg,.java,.c,.cpp,.h,.rs,.go,.rb,.php,.sql,.sh,.bat,.ps1,.zip,.epub,.rtf,.odt,.ods,.odp,image/*" />

            <div className="@container relative flex items-end rounded-[2rem] border border-[var(--border-medium)] bg-[var(--surface-2)] p-2 px-3 shadow-lg shadow-brand-500/10 backdrop-blur-2xl transition-all duration-300 focus-within:border-brand-200 focus-within:bg-white/90 focus-within:shadow-glow">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          className="mb-0.5 flex-shrink-0 rounded-full p-3 text-[var(--muted-foreground)] transition-colors hover:bg-slate-100 hover:text-slate-700 active:scale-90"
          title="上传文件"
          aria-label="上传文件"
        >
          <PaperclipIcon size={20} />
        </button>

        <div className="relative mb-0.5 ml-1">
          <AgentSelector
            agents={selectableAgents}
            selectedId={selectedAgentProfileId ?? null}
            onSelect={(agent) => {
              onAgentProfileChange?.(agent);
              setChatMode(agent.response_mode as 'general' | 'ppt' | 'website' | 'email' | 'bigdata');
            }}
            variant="compact"
            disabled={isModeLocked}
          />
        </div>

        {/* 计划模式 + 审批档（计划模式下审批档无意义，置灰） */}
        {onPlanModeChange && (
          <div className="mb-0.5 ml-1">
            <PlanModeToggle enabled={planMode} onChange={onPlanModeChange} disabled={isLoading} />
          </div>
        )}
        {onApprovalModeChange && (
          <div className="mb-0.5 ml-1">
            <ApprovalModeSelector
              mode={approvalMode}
              onChange={onApprovalModeChange}
              isAdmin={isAdmin}
              disabled={isLoading || planMode}
            />
          </div>
        )}

        <div className="relative min-w-0 flex-auto max-h-[200px]">
          {suggestion && value && (
            <div
              className="pointer-events-none absolute inset-0 p-3 leading-relaxed tracking-tight whitespace-pre-wrap overflow-hidden"
              aria-hidden="true"
            >
              <span className="text-transparent">{value}</span>
              <span className="text-slate-300">{suggestion.slice(value.length)}</span>
            </div>
          )}
          <textarea
            aria-label="输入消息"
            ref={textareaRef}
            value={value}
            onChange={handleChange}
            onKeyDown={handleKeyDown}
            placeholder={isDragging ? '把文件拖到这里...' : placeholder}
            className="max-h-[200px] w-full resize-none bg-transparent p-3 leading-relaxed tracking-tight text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
            rows={1}
          />
        </div>
        {/* 润色按钮：发送按钮左侧；润色中点击=取消，已润色时点击=还原原文 */}
        {!isLoading && (
          <button
            type="button"
            onClick={handlePolish}
            disabled={!value.trim()}
            className={cn(
              'group mb-1 ml-1 flex h-10 flex-shrink-0 items-center gap-1.5 rounded-full px-2.5 @[24rem]:px-3 text-[11px] font-semibold transition-all duration-300 active:scale-95',
              polishState === 'polished'
                ? 'bg-amber-100 text-amber-800 hover:bg-amber-200 dark:bg-amber-500/20 dark:text-amber-200'
                : value.trim()
                  ? 'bg-[var(--surface-2)] text-[var(--muted-foreground)] hover:bg-brand-50 hover:text-[var(--foreground)]'
                  : 'cursor-not-allowed bg-[var(--surface-2)] text-[var(--muted-foreground)] opacity-40',
            )}
            title={polishState === 'polished' ? '取消润色并还原原文' : polishState === 'loading' ? '正在润色，点击可取消' : '润色提示词（分析意图并优化表达）'}
            aria-label={polishState === 'polished' ? '取消润色' : polishState === 'loading' ? '取消润色' : '润色提示词'}
          >
            {polishState === 'loading' ? (
              <svg width="15" height="15" viewBox="0 0 24 24" className="animate-spin" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
            ) : polishState === 'polished' ? (
              <Undo2 size={15} />
            ) : (
              <Wand2 size={15} className="transition-transform group-hover:rotate-12" />
            )}
            <span className="hidden @[24rem]:inline">
              {polishState === 'loading' ? '润色中' : polishState === 'polished' ? '取消润色' : '润色'}
            </span>
          </button>
        )}
        {isLoading ? (
          <button
            type="button"
            onClick={onStop}
            className="group mb-1 ml-1 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-zinc-900 text-white shadow-md transition-all duration-300 hover:scale-105 hover:bg-zinc-700 active:scale-95"
            title="停止当前回复"
            aria-label="停止当前回复"
          >
            <Square size={15} strokeWidth={2.8} fill="currentColor" className="transition-transform group-hover:scale-110" />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleInternalSend}
            disabled={!value.trim() && files.length === 0}
            className={cn(
              'group mb-1 ml-1 flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full transition-all duration-300',
              value.trim() || files.length > 0
                ? 'bg-[var(--accent-send)] text-white shadow-md hover:scale-105 hover:bg-[var(--accent-send-hover)] active:scale-95'
                : 'bg-slate-100/50 text-slate-300',
            )}
            title="发送"
            aria-label="发送"
          >
            <SendIcon size={18} className="transition-transform group-hover:-translate-y-0.5 group-hover:scale-110" />
          </button>
        )}
      </div>
    </div>
  );
});