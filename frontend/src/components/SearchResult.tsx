import type { SearchResult } from "@/lib/types";

interface Props {
  result: SearchResult;
  onClick?: () => void;
}

export function SearchResultItem({ result, onClick }: Props) {
  const page = result.page ?? result.page_number ?? "-";
  const score = result.score ?? result.final_score ?? 0;
  const snippet = result.snippet ?? result.content ?? "";
  return (
    <button
      onClick={onClick}
      className="w-full rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-brand-200 hover:bg-brand-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      type="button"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-brand-700">{result.doc_name}</span>
        <span className="text-xs text-slate-500">p.{page} · relevance {score.toFixed(2)}</span>
      </div>
      <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-700">{snippet}</p>
    </button>
  );
}
