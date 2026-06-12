import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { AlertTriangle, Chrome, Droplets } from 'lucide-react';
import { cn } from '../../lib/utils';

function isChromiumBrowser(): boolean {
  const ua = navigator.userAgent;
  return /Chrome|Edg/.test(ua) && !/OPR/.test(ua);
}

interface ThemeConfirmModalProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ThemeConfirmModal: React.FC<ThemeConfirmModalProps> = ({
  open,
  onConfirm,
  onCancel,
}) => {
  const isChromium = isChromiumBrowser();

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="admin-modal-shell"
          role="dialog"
          aria-modal="true"
          aria-labelledby="glass-confirm-title"
          onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}
        >
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ duration: 0.22 }}
            className="admin-solid-panel admin-modal-panel w-full max-w-md p-6"
          >
            {/* Header */}
            <div className="mb-5 flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
                <Droplets size={22} />
              </div>
              <div>
                <p className="admin-section-kicker">实验性主题</p>
                <h3 id="glass-confirm-title" className="mt-1 text-xl font-bold tracking-tight text-slate-900">
                  启用液态玻璃主题
                </h3>
              </div>
            </div>

            {/* Warnings */}
            <div className="space-y-3">
              {/* Performance warning */}
              <div className="flex gap-3 rounded-xl border border-warning-200 bg-warning-50 p-3.5">
                <AlertTriangle size={18} className="mt-0.5 flex-shrink-0 text-warning-600" />
                <div>
                  <p className="text-sm font-semibold text-warning-800">性能影响</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-warning-700">
                    液态玻璃使用实时物理折射渲染（SVG 位移贴图 + Snell 定律计算），需要 GPU 加速。
                    低端设备或集成显卡可能出现帧率下降、发热增加等情况。
                  </p>
                </div>
              </div>

              {/* Browser compatibility warning */}
              <div className="flex gap-3 rounded-xl border border-info-200 bg-info-50 p-3.5">
                <Chrome size={18} className="mt-0.5 flex-shrink-0 text-info-600" />
                <div>
                  <p className="text-sm font-semibold text-info-800">浏览器兼容</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-info-700">
                    完整折射效果仅在 <strong>Chrome / Edge</strong> 中生效。
                    Safari 和 Firefox 将自动降级为毛玻璃模糊效果。
                  </p>
                </div>
              </div>

              {/* Non-chromium extra warning */}
              {!isChromium && (
                <div className="flex gap-3 rounded-xl border border-error-200 bg-error-50 p-3.5">
                  <AlertTriangle size={18} className="mt-0.5 flex-shrink-0 text-error-600" />
                  <div>
                    <p className="text-sm font-semibold text-error-800">当前浏览器不受支持</p>
                    <p className="mt-0.5 text-xs leading-relaxed text-error-700">
                      您当前使用的浏览器不在完整支持列表中，将显示降级的毛玻璃效果。
                      建议使用 Chrome 或 Edge 以获得最佳体验。
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={onCancel}
                className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-all hover:bg-slate-50 hover:border-slate-300 active:scale-[0.98]"
              >
                取消
              </button>
              <button
                type="button"
                onClick={onConfirm}
                className={cn(
                  'rounded-xl px-4 py-2.5 text-sm font-semibold text-white transition-all active:scale-[0.98]',
                  isChromium
                    ? 'bg-brand-500 hover:bg-brand-600 shadow-button'
                    : 'bg-slate-600 hover:bg-slate-700'
                )}
              >
                知道了，启用
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
