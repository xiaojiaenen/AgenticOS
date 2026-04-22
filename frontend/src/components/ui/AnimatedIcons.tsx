import React from 'react';
import { motion } from 'motion/react';
import { cn } from '../../lib/utils';

export * from './MascotIcons';

export const AbstractLogoIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.rect x="4" y="4" width="10" height="10" rx="2" stroke="currentColor" strokeWidth="2.5"
      animate={{ x: [0, 2, 0], y: [0, 2, 0] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }} />
    <motion.rect x="10" y="10" width="10" height="10" rx="2" fill="currentColor"
      animate={{ x: [0, -2, 0], y: [0, -2, 0] }} transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }} />
  </motion.svg>
);

export const UserAvatarIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <motion.circle cx="12" cy="8" r="4" 
      animate={{ y: [-0.5, 0.5, -0.5] }}
      transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
    />
    <path d="M20 21C20 16.5817 16.4183 13 12 13C7.58172 13 4 16.5817 4 21" />
  </motion.svg>
);

export const SendIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={cn("transition-all duration-300", className)}>
    <path d="M12 19V5M5 12l7-7 7 7" />
  </svg>
);

export const PlusIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={cn("transition-all duration-300", className)}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const ChatBubbleIcon = ({ size = 24, className, active }: { size?: number; className?: string; active?: boolean }) => (
  <motion.svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}
    animate={active ? { y: [-1, 1, -1] } : {}}
    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
  >
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    {active && (
      <motion.circle cx="12" cy="10" r="1.5" fill="currentColor" stroke="none" animate={{ opacity: [0, 1, 0] }} transition={{ duration: 1.5, repeat: Infinity }} />
    )}
  </motion.svg>
);

export const TrashIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M3 6h18" className="group-hover:-translate-y-0.5 group-hover:rotate-[-10deg] transition-transform duration-300 origin-left" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
);

export const MenuIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn("transition-all duration-300", className)}>
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" className="group-hover:scale-105 transition-transform duration-300 origin-center" />
    <line x1="9" y1="3" x2="9" y2="21" />
  </svg>
);

export const CopyIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
  </svg>
);

export const CheckIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <polyline points="20 6 9 17 4 12"></polyline>
  </svg>
);

export const PaperclipIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
  </svg>
);

export const AlertCircleIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  </svg>
);

export const WrenchIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
  </svg>
);

export const ChevronDownIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <polyline points="6 9 12 15 18 9"></polyline>
  </svg>
);

export const DownloadIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);

export const RefreshIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M23 4v6h-6" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);

export const CodeIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <polyline points="16 18 22 12 16 6" />
    <polyline points="8 6 2 12 8 18" />
  </svg>
);

export const MascotSurprised = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ scale: [1, 1.1, 1] }} transition={{ duration: 0.5, repeat: Infinity, repeatDelay: 2 }}>
      {/* Cat Ears - Fixed Length */}
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
      {/* Cat Ears - Fixed Length */}
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
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* Star Eyes */}
      <motion.g animate={{ scale: [1, 1.2, 1], rotate: [0, 15, 0] }} transition={{ duration: 1.5, repeat: Infinity }}>
        <path d="M40 42 L42 46 L46 46 L43 49 L44 53 L40 50 L36 53 L37 49 L34 46 L38 46 Z" fill="#fbbf24" />
        <path d="M60 42 L62 46 L66 46 L63 49 L64 53 L60 50 L56 53 L57 49 L54 46 L58 46 Z" fill="#fbbf24" />
      </motion.g>
      
      {/* Open Mouth */}
      <ellipse cx="50" cy="62" rx="4" ry="6" fill="#0f172a" />
    </motion.g>
  </motion.svg>
);

export const MascotSad = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ y: [0, 2, 0] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* Sad Eyes */}
      <path d="M35 45 Q40 42 45 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M55 45 Q60 42 65 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      
      {/* Tears */}
      <motion.circle cx="35" cy="52" r="2" fill="#94a3b8" animate={{ y: [0, 10, 10], opacity: [1, 1, 0] }} transition={{ duration: 2, repeat: Infinity }} />
      <motion.circle cx="65" cy="52" r="2" fill="#94a3b8" animate={{ y: [0, 10, 10], opacity: [1, 1, 0] }} transition={{ duration: 2, repeat: Infinity, delay: 1 }} />
      
      {/* Sad Mouth */}
      <path d="M45 62 Q50 58 55 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotWink = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ rotate: [-2, 2, -2] }} transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* Wink Eyes */}
      <ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" />
      <path d="M55 48 L65 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      
      {/* Mouth with tongue */}
      <path d="M45 58 Q50 62 55 58" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
      <motion.path d="M48 60 Q50 66 52 60 Z" fill="#f43f5e" animate={{ scaleY: [1, 1.2, 1] }} transition={{ duration: 1, repeat: Infinity }} style={{ transformOrigin: '50px 60px' }} />
    </motion.g>
  </motion.svg>
);

export const MascotDizzy = ({ size = 24, className }: { size?: number; className?: string }) => (
  <motion.svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <motion.g animate={{ x: [-2, 2, -2], rotate: [-2, 2, -2] }} transition={{ duration: 0.5, repeat: Infinity, ease: "linear" }}>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* X Eyes */}
      <path d="M36 44 L44 52 M44 44 L36 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M56 44 L64 52 M64 44 L56 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      
      {/* Wavy Mouth */}
      <path d="M40 62 Q45 58 50 62 T60 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </motion.g>
  </motion.svg>
);

export const MascotStarstruckStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* Star Eyes */}
      <path d="M40 42 L42 46 L46 46 L43 49 L44 53 L40 50 L36 53 L37 49 L34 46 L38 46 Z" fill="#fbbf24" />
      <path d="M60 42 L62 46 L66 46 L63 49 L64 53 L60 50 L56 53 L57 49 L54 46 L58 46 Z" fill="#fbbf24" />
      
      {/* Open Mouth */}
      <ellipse cx="50" cy="62" rx="4" ry="6" fill="#0f172a" />
    </g>
  </svg>
);

export const MascotSadStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 15 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* Sad Eyes */}
      <path d="M35 45 Q40 42 45 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      <path d="M55 45 Q60 42 65 45" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" fill="none" />
      
      {/* Sad Mouth */}
      <path d="M45 62 Q50 58 55 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

export const MascotWinkStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* Wink Eyes */}
      <ellipse cx="40" cy="48" rx="4" ry="4" fill="#0f172a" />
      <path d="M55 48 L65 48" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      
      {/* Mouth with tongue */}
      <path d="M45 58 Q50 62 55 58" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
      <path d="M48 60 Q50 66 52 60 Z" fill="#f43f5e" />
    </g>
  </svg>
);

export const MascotDizzyStatic = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
    <g>
      {/* Cat Ears - Fixed Length */}
      <path d="M20 40 L30 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      <path d="M80 40 L70 10 L50 30 Z" fill="currentColor" stroke="currentColor" strokeWidth="4" strokeLinejoin="round" />
      
      <rect x="15" y="25" width="70" height="55" rx="25" fill="currentColor" />
      <rect x="25" y="35" width="50" height="35" rx="15" fill="white" />
      
      {/* X Eyes */}
      <path d="M36 44 L44 52 M44 44 L36 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      <path d="M56 44 L64 52 M64 44 L56 52" stroke="#0f172a" strokeWidth="3" strokeLinecap="round" />
      
      {/* Wavy Mouth */}
      <path d="M40 62 Q45 58 50 62 T60 62" stroke="#0f172a" strokeWidth="2" strokeLinecap="round" fill="none" />
    </g>
  </svg>
);

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
      {/* Cat Ears - Fixed Length */}
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

export const GlobeIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);

export const PresentationIcon = ({ size = 24, className }: { size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M2 3h20" /><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3" /><path d="m7 21 5-5 5 5" />
  </svg>
);
