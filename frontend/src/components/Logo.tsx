import React from 'react';
import { motion } from 'motion/react';
import { cn } from '../lib/utils';
import { MascotHappy } from './ui/AnimatedIcons';

export const Logo = ({ className, iconSize = 28, showText = true }: { className?: string; iconSize?: number; showText?: boolean }) => {
  return (
    <div className={cn("flex items-center gap-3 select-none group cursor-pointer", className)}>
      <div className="relative">
        <motion.div
          animate={{ 
            scale: [1, 1.2, 1],
            opacity: [0.1, 0.3, 0.1]
          }}
          transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
          className="absolute inset-0 bg-sky-400 blur-xl rounded-full"
        />
        <div className="relative z-10 transition-transform group-hover:scale-110 group-active:scale-95 duration-500">
          <MascotHappy size={iconSize} className="text-zinc-900" />
        </div>
      </div>
      
      {showText && (
        <div className="flex flex-col">
          <div className="relative overflow-hidden">
            <motion.span 
              className="text-xl font-black tracking-tighter leading-none flex"
            >
              {"Agentic".split("").map((char, i) => (
                <motion.span
                  key={i}
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: i * 0.05, type: "spring", stiffness: 200 }}
                  className="text-zinc-900"
                >
                  {char}
                </motion.span>
              ))}
              {"OS".split("").map((char, i) => (
                <motion.span
                  key={i + 7}
                  initial={{ y: 20, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: (i + 7) * 0.05, type: "spring", stiffness: 200 }}
                  className="bg-gradient-to-r from-sky-500 to-cyan-400 bg-clip-text text-transparent"
                >
                  {char}
                </motion.span>
              ))}
            </motion.span>
          </div>
        </div>
      )}
    </div>
  );
};
