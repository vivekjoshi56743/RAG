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
    <button onClick={onClick} className="w-full text-left rounded-lg border p-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-blue-600">{result.doc_name}</span>
        <span className="text-xs text-gray-400">p.{page} · relevance {score.toFixed(2)}</span>
      </div>
      <p className="mt-1 text-sm text-gray-700 line-clamp-3">{snippet}</p>
    </button>
  );
}
