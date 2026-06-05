import React from 'react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export const Pagination = ({ currentPage, totalPages, onPageChange }: PaginationProps) => {
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
    <nav aria-label="分页导航" className="flex flex-col gap-3 border-t border-white/60 bg-[linear-gradient(135deg,rgba(255,255,255,0.42),rgba(248,250,252,0.32))] px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-sm font-semibold text-slate-500">
        第 <span className="font-bold text-slate-900">{currentPage}</span> 页，共{' '}
        <span className="font-bold text-slate-900">{totalPages}</span> 页
      </span>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          aria-label="上一页"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-500 shadow-sm transition-all hover:-translate-y-0.5 hover:text-slate-900 hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0 disabled:hover:shadow-sm"
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
              className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold transition-all duration-200 ${
                currentPage === page
                  ? 'border border-slate-900/80 bg-slate-900 text-white shadow-lg shadow-slate-900/15 hover:bg-slate-800'
                  : 'border border-slate-200 bg-white text-slate-600 shadow-sm hover:-translate-y-0.5 hover:text-slate-900 hover:shadow-md hover:border-sky-200 active:translate-y-0'
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
          aria-label="下一页"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-500 shadow-sm transition-all hover:-translate-y-0.5 hover:text-slate-900 hover:shadow-md active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0 disabled:hover:shadow-sm"
        >
          下一页
        </button>
      </div>
    </nav>
  );
};
