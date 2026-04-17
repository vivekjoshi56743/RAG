import type { SearchResult } from "@/lib/types";

interface Props {
  result: SearchResult;
  onClick?: () => void;
}

export function SearchResultItem({ result, onClick }: Props) {
  const page = result.page ?? result.page_number;
  const snippet = result.snippet ?? result.content ?? "";
  return (
    <button
      onClick={onClick}
      className="w-full rounded-2xl border border-slate-200 bg-white/50 p-4 text-left transition-all duration-300 hover:border-brand-200 hover:bg-white hover:shadow-lg hover:shadow-brand-500/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:bg-slate-900/40 dark:border-slate-800 dark:hover:bg-slate-900/60 dark:hover:border-brand-500/30 dark:hover:shadow-none animate-in-fade"
      type="button"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-wider text-brand-600 dark:text-brand-400">{result.doc_name}</span>
        <div className="flex items-center gap-2">
          {page != null && (
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold text-slate-500 dark:bg-slate-800 dark:text-slate-400">
              P.{page}
            </span>
          )}

        </div>
      </div>
      <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400 transition-colors group-hover:text-slate-900 dark:group-hover:text-slate-200">{snippet}</p>
    </button>
  );
}
