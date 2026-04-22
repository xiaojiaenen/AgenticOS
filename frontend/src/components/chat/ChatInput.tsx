import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { SendIcon, PaperclipIcon, GlobeIcon, PresentationIcon, MascotHappy } from '../ui/AnimatedIcons';
import { cn } from '../../lib/utils';

interface ChatInputProps {
  value: string;
  onChange: (val: string) => void;
  onSend: (text: string, files?: File[]) => void;
  isLoading: boolean;
  className?: string;
  placeholder?: string;
  chatMode: 'general' | 'ppt' | 'website';
  setChatMode: (mode: 'general' | 'ppt' | 'website') => void;
  isModeLocked?: boolean;
}

export interface ChatInputHandle {
  addFiles: (newFiles: File[]) => void;
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(({ 
  value, 
  onChange, 
  onSend, 
  isLoading, 
  className, 
  placeholder = "输入你想聊的内容...",
  chatMode,
  setChatMode,
  isModeLocked = false
}, ref) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [showModeMenu, setShowModeMenu] = useState(false);
  const modeMenuRef = useRef<HTMLDivElement>(null);

  useImperativeHandle(ref, () => ({
    addFiles: (newFiles: File[]) => {
      setFiles(prev => [...prev, ...newFiles]);
    }
  }));

  // Handle click outside to close menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (modeMenuRef.current && !modeMenuRef.current.contains(event.target as Node)) {
        setShowModeMenu(false);
      }
    };
    if (showModeMenu) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showModeMenu]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [value]);

  // Handle files
  useEffect(() => {
    const newPreviews = files.map(file => {
      if (file.type.startsWith('image/')) {
        return URL.createObjectURL(file);
      }
      return '';
    });
    setPreviews(newPreviews);
    return () => newPreviews.forEach(url => { if(url) URL.revokeObjectURL(url); });
  }, [files]);

  const handleInternalSend = React.useCallback(() => {
    console.log('handleInternalSend triggered', { hasValue: !!value.trim(), filesCount: files.length, isLoading });
    if ((!value.trim() && files.length === 0) || isLoading) return;
    onSend(value, files);
    setFiles([]);
  }, [value, files, isLoading, onSend]);

  const handleKeyDown = React.useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleInternalSend();
    }
  }, [handleInternalSend]);

  const handleFileChange = React.useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(prev => [...prev, ...Array.from(e.target.files!)]);
    }
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
      setFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  }, []);

  const removeFile = React.useCallback((index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  }, []);

  return (
    <div 
      className={cn("relative flex flex-col gap-2 p-2", isDragging && "bg-sky-50/50 rounded-3xl ring-2 ring-sky-300 ring-dashed", className)}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* File Thumbnails */}
      <AnimatePresence>
        {files.length > 0 && (
          <motion.div 
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="flex flex-wrap gap-3 px-2 mb-1"
          >
            {files.map((file, idx) => (
              <motion.div 
                layout
                key={`${file.name}-${idx}`} 
                className="relative group h-16 w-16 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden"
              >
                {previews[idx] ? (
                  <img src={previews[idx]} alt="preview" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center bg-slate-50 text-[8px] p-1 text-center">
                    <PaperclipIcon size={12} className="text-slate-400 mb-1" />
                    <span className="truncate w-full">{file.name.split('.').pop()?.toUpperCase()}</span>
                  </div>
                )}
                <button 
                  onClick={() => removeFile(idx)}
                  className="absolute -top-1 -right-1 bg-rose-500 text-white rounded-full p-1 opacity-0 group-hover:opacity-100 transition-opacity shadow-sm hover:bg-rose-600 scale-75"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M18 6L6 18M6 6l12 12"/></svg>
                </button>
              </motion.div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <input 
        type="file" 
        multiple 
        ref={fileInputRef} 
        onChange={handleFileChange} 
        className="hidden" 
        accept="image/*,.pdf,.txt,.doc,.docx"
      />

      {/* Floating Input Island */}
      <div 
        className="relative bg-white/60 backdrop-blur-2xl rounded-[2rem] shadow-[0_8px_30px_rgba(50,150,250,0.1)] border border-white/60 focus-within:border-cyan-400 focus-within:shadow-[0_12px_40px_rgba(34,211,238,0.3)] focus-within:bg-white/90 transition-all duration-300 flex items-end p-2 px-3"
      >
        <button 
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          className="p-3 text-slate-400 hover:text-sky-600 transition-colors flex-shrink-0 mb-0.5 rounded-full hover:bg-sky-50 active:scale-90"
          title="上传文件"
        >
          <PaperclipIcon size={20} />
        </button>

        <div className="relative mb-0.5 ml-1" ref={modeMenuRef}>
          <button 
            onClick={() => !isModeLocked && setShowModeMenu(!showModeMenu)}
            className={cn(
              "p-2.5 text-slate-400 hover:text-sky-600 transition-all rounded-full flex items-center justify-center",
              isModeLocked ? "cursor-not-allowed opacity-60" : "hover:bg-sky-50 active:scale-95 border border-transparent hover:border-sky-100"
            )}
            title={isModeLocked ? "对话已开始，无法更改模式" : "切换模式"}
          >
            <div className={cn("w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold border-2", 
              chatMode === 'general' ? "border-slate-300 text-slate-400" : "border-sky-500 text-sky-600 shadow-[0_0_8px_rgba(14,165,233,0.3)] bg-sky-50")}>
              {chatMode === 'general' ? <MascotHappy size={12} /> : chatMode === 'ppt' ? <PresentationIcon size={12} /> : <GlobeIcon size={12} />}
            </div>
          </button>

          <AnimatePresence>
            {showModeMenu && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: -20 }}
                animate={{ opacity: 1, scale: 1, y: -10 }}
                exit={{ opacity: 0, scale: 0.95, y: -20 }}
                className="absolute bottom-full left-0 mb-4 w-44 bg-white/95 backdrop-blur-2xl border border-slate-200/50 rounded-3xl shadow-2xl z-40 p-2 ring-1 ring-black/5"
              >
                  {[
                    { id: 'general', label: '普通聊天', icon: <MascotHappy size={20} />, desc: '日常问答' },
                    { id: 'ppt', label: 'PPT 模式', icon: <PresentationIcon size={20} />, desc: '演示文稿' },
                    { id: 'website', label: '网站模式', icon: <GlobeIcon size={20} />, desc: '生成网页' }
                  ].map((mode) => (
                    <button
                      key={mode.id}
                      onClick={() => {
                        setChatMode(mode.id as any);
                        setShowModeMenu(false);
                      }}
                      className={cn(
                        "w-full flex items-center gap-3 p-2.5 rounded-2xl transition-all hover:bg-slate-50 text-left group mb-1 last:mb-0",
                        chatMode === mode.id ? "bg-sky-50/50 ring-1 ring-sky-100" : ""
                      )}
                    >
                      <span className={cn("w-8 h-8 rounded-xl flex items-center justify-center text-sm shadow-sm transition-transform group-hover:scale-110", 
                        chatMode === mode.id ? "bg-sky-500 text-white" : "bg-slate-100 text-slate-400")}>
                        {mode.icon}
                      </span>
                      <div className="flex flex-col">
                        <span className={cn("text-xs font-bold transition-colors", chatMode === mode.id ? "text-sky-700" : "text-slate-700")}>{mode.label}</span>
                        <span className="text-[9px] text-slate-400 font-medium">{mode.desc}</span>
                      </div>
                    </button>
                  ))}
                </motion.div>
            )}
          </AnimatePresence>
        </div>

        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isDragging ? "把文件投在这里..." : placeholder}
          className="w-full max-h-[200px] bg-transparent resize-none outline-none text-slate-800 placeholder:text-slate-400 p-3 leading-relaxed tracking-tight"
          rows={1}
        />
        <button
          type="button"
          onClick={handleInternalSend}
          disabled={(!value.trim() && files.length === 0) || isLoading}
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 flex-shrink-0 mb-1 ml-1 group",
            (value.trim() || files.length > 0) && !isLoading
              ? "bg-zinc-900 hover:bg-zinc-700 text-white shadow-md hover:scale-105 active:scale-95"
              : "bg-slate-100/50 text-slate-300"
          )}
        >
          <SendIcon size={18} className="group-hover:-translate-y-0.5 group-hover:scale-110 transition-transform" />
        </button>
      </div>
    </div>
  );
});
