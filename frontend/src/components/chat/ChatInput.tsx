import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Square } from 'lucide-react';
import { AgentProfile } from '../../services/agentProfileService';
import { cn } from '../../lib/utils';
import { AgentSelector } from '../ui/AgentSelector';
import { PaperclipIcon, SendIcon } from '../ui/AnimatedIcons';

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: (text: string, files?: File[]) => void;
  onStop?: () => void;
  isLoading: boolean;
  className?: string;
  placeholder?: string;
  chatMode: 'general' | 'ppt' | 'website';
  setChatMode: (mode: 'general' | 'ppt' | 'website') => void;
  agentProfiles?: AgentProfile[];
  selectedAgentProfileId?: number | null;
  onAgentProfileChange?: (profile: AgentProfile | null) => void;
  isModeLocked?: boolean;
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
}, ref) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);

  useImperativeHandle(ref, () => ({
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

  const handleKeyDown = React.useCallback((e: React.KeyboardEvent) => {
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (nativeEvent.isComposing || e.key === 'Process') return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleInternalSend();
    }
  }, [handleInternalSend]);

  const handleFileChange = React.useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
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
      className={cn('relative flex flex-col gap-2 p-2', isDragging && 'rounded-3xl bg-sky-50/50 ring-2 ring-sky-300 ring-dashed', className)}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <AnimatePresence>
        {files.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }} className="mb-1 flex flex-wrap gap-3 px-2">
            {files.map((file, idx) => (
              <motion.div layout key={`${file.name}-${idx}`} className="group relative h-16 w-16 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                {previews[idx] ? (
                  <img src={previews[idx]} alt="preview" className="h-full w-full object-cover" />
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-center bg-slate-50 p-1 text-center text-[8px]">
                    <PaperclipIcon size={12} className="mb-1 text-slate-400" />
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

      <div className="relative flex items-end rounded-[2rem] border border-white/60 bg-white/60 p-2 px-3 shadow-lg shadow-brand-500/10 backdrop-blur-2xl transition-all duration-300 focus-within:border-brand-200 focus-within:bg-white/90 focus-within:shadow-glow">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          className="mb-0.5 flex-shrink-0 rounded-full p-3 text-slate-400 transition-colors hover:bg-sky-50 hover:text-sky-600 active:scale-90"
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
              setChatMode(agent.response_mode as 'general' | 'ppt' | 'website');
            }}
            variant="compact"
            disabled={isModeLocked}
          />
        </div>

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isDragging ? '把文件拖到这里...' : placeholder}
          className="max-h-[200px] w-full resize-none bg-transparent p-3 leading-relaxed tracking-tight text-slate-800 outline-none placeholder:text-slate-400"
          rows={1}
        />
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
                ? 'bg-zinc-900 text-white shadow-md hover:scale-105 hover:bg-zinc-700 active:scale-95'
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
