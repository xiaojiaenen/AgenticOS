import React from 'react';
import { AnimatePresence, MotionValue } from 'motion/react';
import { Artifact } from '../../types';
import { ArtifactPanel } from './ArtifactPanel';
import { PptArtifactPanel } from '../ppt/PptArtifactPanel';
import { WebsiteArtifactPanel } from '../website/WebsiteArtifactPanel';

interface ChatArtifactAreaProps {
  artifact: Artifact | null;
  onClose: () => void;
  borderColor: MotionValue<string>;
  onPptThemeChange?: (newHtml: string, theme: string) => void;
}

export const ChatArtifactArea = React.memo(({ artifact, onClose, borderColor, onPptThemeChange }: ChatArtifactAreaProps) => (
  <AnimatePresence mode="wait">
    {artifact?.language === 'ppt' ? (
      <PptArtifactPanel
        key="ppt"
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
        onThemeChange={onPptThemeChange}
      />
    ) : artifact?.language === 'website' ? (
      <WebsiteArtifactPanel
        key="website"
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
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
