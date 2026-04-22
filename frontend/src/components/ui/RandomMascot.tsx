import React, { useMemo } from 'react';
import { 
  MascotHappy, MascotCurious, MascotSleepy, MascotSurprised, 
  MascotCool, MascotThinking, MascotExcited, MascotLove,
  MascotStarstruck, MascotSad, MascotWink, MascotDizzy
} from './AnimatedIcons';

const mascots = [
  MascotHappy, MascotCurious, MascotSleepy, MascotSurprised, 
  MascotCool, MascotThinking, MascotExcited, MascotLove,
  MascotStarstruck, MascotSad, MascotWink, MascotDizzy
];

export const RandomMascot = ({ size = 24, className }: { size?: number; className?: string }) => {
  const [SelectedMascot] = React.useState(() => mascots[Math.floor(Math.random() * mascots.length)]);
  return <SelectedMascot size={size} className={className} />;
};
