import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const Pagination = ({ currentPage, totalPages, onPageChange }: PaginationProps) => {
  const getVisiblePages = () => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1);
    if (currentPage <= 3) return [1, 2, 3, 4, 5];
    if (currentPage >= totalPages - 2) return [totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    return [currentPage - 2, currentPage - 1, currentPage, currentPage + 1, currentPage + 2];
  };

  const pages = getVisiblePages();

  if (totalPages <= 1) return null;

  return (
    <div className="flex flex-col gap-3 border-t border-white/60 bg-white/40 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-sm font-semibold text-slate-500">
        第 <span className="font-black text-slate-900">{currentPage}</span> 页，共{' '}
        <span className="font-black text-slate-900">{totalPages}</span> 页
      </span>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="rounded-2xl border border-white/80 bg-white/80 p-2 text-slate-500 shadow-[0_8px_20px_rgba(15,23,42,0.06)] transition-all hover:-translate-y-0.5 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ChevronLeft size={16} />
        </button>

        <div className="flex items-center gap-1.5">
          {pages.map((page) => (
            <button
              key={page}
              type="button"
              onClick={() => onPageChange(page)}
              className={`flex h-9 w-9 items-center justify-center rounded-2xl text-sm font-black transition-all ${
                currentPage === page
                  ? 'border border-slate-900/80 bg-slate-900 text-white shadow-[0_14px_30px_rgba(15,23,42,0.2)]'
                  : 'border border-white/80 bg-white/80 text-slate-600 shadow-[0_8px_20px_rgba(15,23,42,0.06)] hover:-translate-y-0.5 hover:text-slate-900'
              }`}
            >
              {page}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className="rounded-2xl border border-white/80 bg-white/80 p-2 text-slate-500 shadow-[0_8px_20px_rgba(15,23,42,0.06)] transition-all hover:-translate-y-0.5 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};
