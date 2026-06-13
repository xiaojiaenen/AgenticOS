import React from 'react';
import { motion } from 'motion/react';

export const MascotHappy = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '40px 48px' }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '60px 48px' }} />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotIcon = MascotHappy;

export const MascotCurious = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ rotate: [-5, 5, -5] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="5" ry="6" fill="#0f172a" animate={{ scaleY: [1, 0.2, 1] }} transition={{ duration: 3, repeat: Infinity, delay: 1 }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 0.2, 1] }} transition={{ duration: 3, repeat: Infinity, delay: 1 }} />
      <path d="M40 60 Q50 65 60 60" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotSleepy = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ scale: [1, 1.02, 1] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M35 48 L45 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M55 48 L65 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <circle cx="50" cy="58" r="2" fill="#0f172a"><animate attributeName="opacity" values="0.5;1;0.5" dur="2s" repeatCount="indefinite" /></circle>
    </motion.g>
  </motion.svg>
);

export const MascotSurprised = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 0.5, repeat: Infinity, repeatDelay: 2 }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <circle cx="40" cy="48" r="6" fill="#0f172a" />
      <circle cx="60" cy="48" r="6" fill="#0f172a" />
      <circle cx="50" cy="65" r="8" stroke="#0f172a" strokeWidth="3" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotCool = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ x: [-1, 1, -1] }} transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <rect x="30" y="45" width="15" height="6" fill="#0f172a" />
      <rect x="55" y="45" width="15" height="6" fill="#0f172a" />
      <path d="M40 60 Q50 55 60 60" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotThinking = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ rotate: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <circle cx="40" cy="48" r="4" fill="#0f172a" />
      <circle cx="60" cy="48" r="4" fill="#0f172a" />
      <path d="M45 65 Q50 60 55 65" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M30 60 L20 50" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
    </motion.g>
  </motion.svg>
);

export const MascotExcited = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ scale: [1, 1.05, 1] }} transition={{ duration: 0.3, repeat: Infinity, repeatDelay: 1 }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <circle cx="40" cy="45" r="5" fill="#0f172a" />
      <circle cx="60" cy="45" r="5" fill="#0f172a" />
      <rect x="40" y="55" width="20" height="10" rx="5" fill="#0f172a" />
    </motion.g>
  </motion.svg>
);

export const MascotLove = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M35 45 Q40 40 45 45 Q40 50 35 45 Z" fill="#f43f5e" />
      <path d="M55 45 Q60 40 65 45 Q60 50 55 45 Z" fill="#f43f5e" />
      <path d="M45 60 Q50 65 55 60" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotStarstruck = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.g animate={{ scale: [1, 1.2, 1], rotate: [0, 15, 0] }} transition={{ duration: 1.5, repeat: Infinity }}>
        <path d="M40 42 L42 46 L46 46 L43 49 L44 53 L40 50 L36 53 L37 49 L34 46 L38 46 Z" fill="#fbbf24" />
        <path d="M60 42 L62 46 L66 46 L63 49 L64 53 L60 50 L56 53 L57 49 L54 46 L58 46 Z" fill="#fbbf24" />
      </motion.g>
      <ellipse cx="50" cy="62" rx="4" ry="6" fill="#0f172a" />
    </motion.g>
  </motion.svg>
);

export const MascotSad = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [0, 2, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M35 45 Q40 42 45 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M55 45 Q60 42 65 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      <motion.g animate={{ y: [0, 10, 10], opacity: [1, 1, 0] }} transition={{ duration: 2, repeat: Infinity }}><circle cx="35" cy="52" r="2" fill="#94a3b8" /></motion.g>
      <motion.g animate={{ y: [0, 10, 10], opacity: [1, 1, 0] }} transition={{ duration: 2, repeat: Infinity, delay: 1 }}><circle cx="65" cy="52" r="2" fill="#94a3b8" /></motion.g>
      <path d="M45 62 Q50 58 55 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotWink = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ rotate: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" />
      <path d="M55 48 L65 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M45 58 Q50 62 55 58" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
      <motion.path d="M48 60 Q50 66 52 60 Z" fill="#f43f5e" animate={{ scaleY: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity }} style={{ transformOrigin: '50% 60%' }} />
    </motion.g>
  </motion.svg>
);

export const MascotDizzy = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ x: [-2, 2, -2], rotate: [-2, 2, -2] }} transition={{ duration: 0.5, repeat: Infinity, ease: "linear" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M36 44 L44 52 M44 44 L36 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M56 44 L64 52 M64 44 L56 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M40 62 Q45 58 50 62 T60 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

// Static Mascots
export const MascotHappyStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" />
      <ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

export const MascotCuriousStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <ellipse cx="40" cy="48" rx="5" ry="6" fill="#0f172a" />
      <ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" />
      <path d="M40 60 Q50 65 60 60" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

export const MascotSleepyStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M35 48 L45 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M55 48 L65 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <circle cx="50" cy="58" r="2" fill="#0f172a" />
    </g>
  </svg>
);

export const MascotSurprisedStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <circle cx="40" cy="48" r="6" fill="#0f172a" />
      <circle cx="60" cy="48" r="6" fill="#0f172a" />
      <circle cx="50" cy="65" r="8" stroke="#0f172a" strokeWidth="3" fill="none" />
    </g>
  </svg>
);

export const MascotCoolStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <rect x="30" y="45" width="15" height="6" fill="#0f172a" />
      <rect x="55" y="45" width="15" height="6" fill="#0f172a" />
      <path d="M40 60 Q50 55 60 60" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

export const MascotThinkingStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <circle cx="40" cy="48" r="4" fill="#0f172a" />
      <circle cx="60" cy="48" r="4" fill="#0f172a" />
      <path d="M45 65 Q50 60 55 65" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M30 60 L20 50" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
    </g>
  </svg>
);

export const MascotExcitedStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <circle cx="40" cy="45" r="5" fill="#0f172a" />
      <circle cx="60" cy="45" r="5" fill="#0f172a" />
      <rect x="40" y="55" width="20" height="10" rx="5" fill="#0f172a" />
    </g>
  </svg>
);

export const MascotStarstruckStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M40 42 L42 46 L46 46 L43 49 L44 53 L40 50 L36 53 L37 49 L34 46 L38 46 Z" fill="#fbbf24" />
      <path d="M60 42 L62 46 L66 46 L63 49 L64 53 L60 50 L56 53 L57 49 L54 46 L58 46 Z" fill="#fbbf24" />
      <ellipse cx="50" cy="62" rx="4" ry="6" fill="#0f172a" />
    </g>
  </svg>
);

export const MascotSadStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M35 45 Q40 42 45 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M55 45 Q60 42 65 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M45 62 Q50 58 55 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

export const MascotWinkStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" />
      <path d="M55 48 L65 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M45 58 Q50 62 55 58" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M48 60 Q50 66 52 60 Z" fill="#f43f5e" />
    </g>
  </svg>
);

export const MascotDizzyStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M36 44 L44 52 M44 44 L36 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M56 44 L64 52 M64 44 L56 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M40 62 Q45 58 50 62 T60 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

export const MascotLoveStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <path d="M35 45 Q40 40 45 45 Q40 50 35 45 Z" fill="#f43f5e" />
      <path d="M55 45 Q60 40 65 45 Q60 50 55 45 Z" fill="#f43f5e" />
      <path d="M45 60 Q50 65 55 60" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

// ── Mode-specific mascots: 小精灵 + 模式标识 ──────────────────────────────
// viewBox 0 0 140 100 — 右侧给大尺寸标识留空间
// 小精灵占左侧 ~85px，标识占右侧，大小 ~45px，与小精灵身体差不多大

/** 通用模式：小精灵举着聊天气泡 */
export const MascotGeneral = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 140 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '40px 48px' }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '60px 48px' }} />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
    {/* 聊天气泡 — 大尺寸，与小精灵身体差不多大 */}
    <g transform="translate(88, 28)">
      <rect x="0" y="0" width="44" height="34" rx="10" fill="#38bdf8" />
      <path d="M8 34 L14 27 L20 34" fill="#38bdf8" />
      <circle cx="13" cy="17" r="3.5" fill="white" />
      <circle cx="22" cy="17" r="3.5" fill="white" />
      <circle cx="31" cy="17" r="3.5" fill="white" />
    </g>
  </motion.svg>
);

/** PPT 模式：小精灵举着图表 */
export const MascotPPT = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 140 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '40px 48px' }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '60px 48px' }} />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
    {/* 柱状图 — 大尺寸 */}
    <g transform="translate(88, 22)">
      <rect x="0" y="30" width="12" height="40" rx="2" fill="#8b5cf6" />
      <rect x="16" y="10" width="12" height="60" rx="2" fill="#a78bfa" />
      <rect x="32" y="20" width="12" height="50" rx="2" fill="#c4b5fd" />
    </g>
  </motion.svg>
);

/** 网站模式：小精灵举着地球仪 */
export const MascotWebsite = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 140 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '40px 48px' }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '60px 48px' }} />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
    {/* 地球仪 — 大尺寸 */}
    <g transform="translate(86, 18)">
      <circle cx="22" cy="22" r="22" fill="#10b981" stroke="#059669" strokeWidth="1.5" />
      <ellipse cx="22" cy="22" rx="10" ry="22" fill="none" stroke="white" strokeWidth="1.5" opacity="0.6" />
      <line x1="0" y1="22" x2="44" y2="22" stroke="white" strokeWidth="1.5" opacity="0.6" />
      <line x1="22" y1="0" x2="22" y2="44" stroke="white" strokeWidth="1.2" opacity="0.4" />
      <ellipse cx="22" cy="12" rx="18" ry="4" fill="none" stroke="white" strokeWidth="0.8" opacity="0.4" />
      <ellipse cx="22" cy="32" rx="18" ry="4" fill="none" stroke="white" strokeWidth="0.8" opacity="0.4" />
    </g>
  </motion.svg>
);

/** 大数据模式：小精灵举着齿轮 */
export const MascotBigData = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 140 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '40px 48px' }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '60px 48px' }} />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
    {/* 齿轮 — 大尺寸，旋转动画 */}
    <g transform="translate(86, 18)">
      <motion.g animate={{ rotate: [0, 360] }} transition={{ duration: 10, repeat: Infinity, ease: "linear" }} style={{ transformOrigin: '22px 22px' }}>
        <circle cx="22" cy="22" r="14" fill="#f97316" />
        <circle cx="22" cy="22" r="6" fill="white" />
        {/* 8 个齿 */}
        <rect x="19" y="0" width="6" height="10" rx="2" fill="#f97316" />
        <rect x="19" y="34" width="6" height="10" rx="2" fill="#f97316" />
        <rect x="0" y="19" width="10" height="6" rx="2" fill="#f97316" />
        <rect x="34" y="19" width="10" height="6" rx="2" fill="#f97316" />
        <rect x="4" y="4" width="7" height="7" rx="2" fill="#f97316" transform="rotate(45 7.5 7.5)" />
        <rect x="33" y="4" width="7" height="7" rx="2" fill="#f97316" transform="rotate(45 36.5 7.5)" />
        <rect x="4" y="33" width="7" height="7" rx="2" fill="#f97316" transform="rotate(45 7.5 36.5)" />
        <rect x="33" y="33" width="7" height="7" rx="2" fill="#f97316" transform="rotate(45 36.5 36.5)" />
      </motion.g>
    </g>
  </motion.svg>
);

/** 视频模式：小精灵举着播放按钮 */
export const MascotVideo = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 140 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      <motion.ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '40px 48px' }} />
      <motion.ellipse cx="60" cy="48" rx="4" ry="4" fill="#0f172a" animate={{ scaleY: [1, 1, 0.15, 1, 1] }} transition={{ duration: 4, repeat: Infinity, times: [0, 0.45, 0.5, 0.55, 1] }} style={{ transformOrigin: '60px 48px' }} />
      <circle cx="32" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <circle cx="68" cy="54" r="3" fill="#e2e8f0" opacity="0.8" />
      <path d="M46 54 Q50 58 54 54" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
    {/* 播放按钮 — 脉冲动画 */}
    <g transform="translate(82, 14)">
      <motion.g animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }} style={{ transformOrigin: '28px 28px' }}>
        <circle cx="28" cy="28" r="24" fill="#8b5cf6" />
        <motion.path d="M22 16 L40 28 L22 40 Z" fill="white" animate={{ x: [0, 2, 0] }} transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }} />
      </motion.g>
    </g>
  </motion.svg>
);
