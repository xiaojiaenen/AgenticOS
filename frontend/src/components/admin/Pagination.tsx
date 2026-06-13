import React from 'react';
import { cn } from '../../lib/utils';
import { useIsGlassTheme } from '../liquid-glass';

interface PaginationProps {
 currentPage: number;
 totalPages: number;
 onPageChange: (page: number) => void;
}

export const Pagination = ({ currentPage, totalPages, onPageChange }: PaginationProps) => {
 const isGlass = useIsGlassTheme();
 const getVisiblePages = () => {
  if (totalPages <= 5) return Array.from({ length: totalPages }, (_, index) => index + 1);
  if (currentPage <= 3) return [1, 2, 3, 4, 5];
  if (currentPage >= totalPages - 2) {
   return [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
  }
  return [currentPage - 2, currentPage - 1, currentPage, currentPage + 1, currentPage + 2];
 };

 if (totalPages <= 1) return null;

 const pages = getVisiblePages();

 return (
  <nav aria-label="分页导航" className={cn("flex flex-col gap-3 border-t px-6 py-4 sm:flex-row sm:items-center sm:justify-between",
   isGlass ? "border-white/10 bg-white/5" : "border-slate-200/80 bg-[linear-gradient(135deg,rgba(255,255,255,0.42),rgba(248,250,252,0.32))]")}>
   <span className={cn("text-sm font-semibold", isGlass ? "text-gray-400" : "text-slate-500")}>
    第 <span className={cn("font-medium", isGlass ? "text-white" : "text-slate-900")}>{currentPage}</span> 页，共{' '}
    <span className={cn("font-medium", isGlass ? "text-white" : "text-slate-900")}>{totalPages}</span> 页
   </span>

   <div className="flex items-center gap-2">
    <button
     type="button"
     onClick={() => onPageChange(Math.max(1, currentPage - 1))}
     disabled={currentPage === 1}
     aria-label="上一页"
     className={cn("rounded-lg border px-3 py-2 text-xs font-medium transition-all hover:shadow-md disabled:cursor-not-allowed disabled:opacity-40",
      isGlass
       ? "border-white/15 bg-white/10 text-gray-300 hover:text-white hover:bg-white/15 disabled:hover:bg-white/10"
       : "border-slate-200 bg-white text-slate-500 shadow-sm hover:text-slate-900 hover:shadow-md disabled:hover:translate-y-0 disabled:hover:shadow-sm")}
    >
     上一页
    </button>

    <div className="flex items-center gap-1.5">
     {pages.map((page) => (
      <button
       key={page}
       type="button"
       onClick={() => onPageChange(page)}
       aria-current={currentPage === page ? 'page' : undefined}
       className={cn("flex h-9 w-9 items-center justify-center rounded-lg text-sm font-medium transition-all duration-200",
        currentPage === page
         ? isGlass
           ? "bg-white/10 border border-white/20 text-white shadow-md"
           : "border border-slate-900/80 bg-slate-900 text-white shadow-md shadow-slate-900/15 hover:bg-slate-800"
         : isGlass
           ? "border border-white/15 bg-white/10 text-gray-300 shadow-sm hover:text-white hover:bg-white/15 hover:border-sky-400/50"
           : "border border-slate-200 bg-white text-slate-600 shadow-sm hover:text-slate-900 hover:shadow-md hover:border-sky-200")}
      >
       {page}
      </button>
     ))}
    </div>

    <button
     type="button"
     onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
     disabled={currentPage === totalPages}
     aria-label="下一页"
     className={cn("rounded-lg border px-3 py-2 text-xs font-medium transition-all hover:shadow-md disabled:cursor-not-allowed disabled:opacity-40",
      isGlass
       ? "border-white/15 bg-white/10 text-gray-300 hover:text-white hover:bg-white/15 disabled:hover:bg-white/10"
       : "border-slate-200 bg-white text-slate-500 shadow-sm hover:text-slate-900 hover:shadow-md disabled:hover:translate-y-0 disabled:hover:shadow-sm")}
    >
     下一页
    </button>
   </div>
  </nav>
 );
};
