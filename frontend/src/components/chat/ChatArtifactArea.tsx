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
}

export const ChatArtifactArea = React.memo(({ artifact, onClose, borderColor }: ChatArtifactAreaProps) => (
  <AnimatePresence>
    {artifact?.language === 'ppt' ? (
      <PptArtifactPanel
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
      />
    ) : artifact?.language === 'website' ? (
      <WebsiteArtifactPanel
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
      />
    ) : (
      <ArtifactPanel
        artifact={artifact}
        onClose={onClose}
        borderColor={borderColor}
      />
    )}
  </AnimatePresence>
));
