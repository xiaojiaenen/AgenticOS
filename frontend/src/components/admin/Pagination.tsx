import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const Pagination = ({ currentPage, totalPages, onPageChange }: PaginationProps) => {
  // Generate page numbers to show (simple logic for now, showing all or a subset if too many)
  const getVisiblePages = () => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1);
    
    if (currentPage <= 3) return [1, 2, 3, 4, 5];
    if (currentPage >= totalPages - 2) return [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    
    return [currentPage - 2, currentPage - 1, currentPage, currentPage + 1, currentPage + 2];
  };

  const pages = getVisiblePages();

  if (totalPages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100/50 bg-slate-50/50 rounded-b-2xl">
      <span className="text-sm text-slate-500 font-medium">
        第 <span className="font-bold text-slate-700">{currentPage}</span> 页，共 <span className="font-bold text-slate-700">{totalPages}</span> 页
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="p-2 rounded-xl border border-slate-200 bg-white text-slate-500 hover:text-zinc-900 hover:border-zinc-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
        >
          <ChevronLeft size={16} />
        </button>
        <div className="flex items-center gap-1.5">
          {pages.map(page => (
            <button
              key={page}
              onClick={() => onPageChange(page)}
              className={`w-8 h-8 rounded-xl text-sm font-bold transition-all shadow-sm flex items-center justify-center ${
                currentPage === page
                  ? 'bg-zinc-900 text-white border-transparent shadow-zinc-900/20'
                  : 'bg-white border border-slate-200 text-slate-600 hover:border-zinc-300 hover:text-zinc-900'
              }`}
            >
              {page}
            </button>
          ))}
        </div>
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className="p-2 rounded-xl border border-slate-200 bg-white text-slate-500 hover:text-zinc-900 hover:border-zinc-300 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};
