import React from 'react';
import { AnimatePresence, MotionValue } from 'motion/react';
import { Artifact } from '../../types';
import { ArtifactPanel } from './ArtifactPanel';
import { PptArtifactPanel } from '../ppt/PptArtifactPanel';
import { WebsiteArtifactPanel } from '../website/WebsiteArtifactPanel';
import { EmailArtifactPanel } from '../email/EmailArtifactPanel';

// Univer SDK gzip 后约 1.7MB。面板必须 lazy —— 其余三个面板是静态 import 的，
// 照抄那个写法会把整包拖进 Chat chunk，所有用户的首屏都变慢。
const SpreadsheetArtifactPanel = React.lazy(() =>
  import('../sheet/SpreadsheetArtifactPanel').then((module) => ({
    default: module.SpreadsheetArtifactPanel,
  })),
);

interface ChatArtifactAreaProps {
  artifact: Artifact | null;
  onClose: () => void;
  borderColor: MotionValue<string>;
  onPptThemeChange?: (newHtml: string, theme: string) => void;
  /** 切换历史版本时替换当前产物 */
  onSwitchArtifact?: (artifact: Artifact) => void;
  onEmailConfirm?: (approvalId: string) => void;
  onEmailCancel?: (approvalId: string) => void;
  sessionId?: string | null;
}

export const ChatArtifactArea = React.memo(({
  artifact,
  onClose,
  borderColor,
  onPptThemeChange,
  onEmailConfirm,
  onEmailCancel,
  sessionId,
  onSwitchArtifact,
}: ChatArtifactAreaProps) => (
  <AnimatePresence mode="wait">
    {artifact?.language === 'ppt' ? (

      <PptArtifactPanel
        key="ppt"
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
        onThemeChange={onPptThemeChange}
        onSwitchVersion={onSwitchArtifact}
      />
    ) : artifact?.language === 'website' ? (
      <WebsiteArtifactPanel
        key="website"
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
        sessionId={sessionId ?? undefined}
        onSwitchVersion={onSwitchArtifact}
      />
    ) : artifact?.language === 'spreadsheet' ? (
      <React.Suspense
        key="spreadsheet"
        fallback={
          <div className="flex h-full items-center justify-center text-sm text-[var(--muted-foreground)]">
            正在加载表格…
          </div>
        }
      >
        <SpreadsheetArtifactPanel
          artifact={artifact}
          onClose={onClose}
          borderColor={borderColor}
          sessionId={sessionId ?? undefined}
          onSwitchVersion={onSwitchArtifact}
        />
      </React.Suspense>
    ) : artifact?.language === 'email' ? (
      <EmailArtifactPanel
        key="email"
        artifact={artifact}
        onClose={onClose}
        onConfirm={onEmailConfirm || (() => {})}
        onCancel={onEmailCancel || (() => {})}
      />
    ) : artifact ? (
      <ArtifactPanel
        key="code"
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
      />
    ) : null}
  </AnimatePresence>
));
