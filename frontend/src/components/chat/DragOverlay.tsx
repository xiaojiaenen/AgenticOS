import React from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';
import { DownloadIcon } from '../ui/AnimatedIcons';

interface DragOverlayProps {
  isDragging: boolean;
}

// portal 到 body：Chat 根节点是 motion.div（带 exit transform）+ overflow-hidden，
// `fixed inset-0` 的包含块会变成它 —— 拖拽投放提示只剩聊天区大小、圆角被裁。
export const DragOverlay: React.FC<DragOverlayProps> = ({ isDragging }) => {
  return createPortal(
    <AnimatePresence>
      {isDragging && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] bg-sky-500/10 backdrop-blur-md flex items-center justify-center p-10 pointer-events-none"
        >
          <motion.div 
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="w-full h-full border-4 border-sky-400 border-dashed rounded-[2rem] flex flex-col items-center justify-center gap-6 bg-white/20"
          >
            <div className="w-24 h-24 bg-[var(--surface-1)] rounded-full flex items-center justify-center shadow-2xl shadow-sky-200">
              <DownloadIcon size={48} className="text-sky-500" />
            </div>
            <div className="text-center">
              <h3 className="text-3xl font-semibold text-sky-900 tracking-tighter">投放到这里上传</h3>
              <p className="text-sky-700 font-medium mt-2">支持图片、PDF、文档和代码文件</p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
};
