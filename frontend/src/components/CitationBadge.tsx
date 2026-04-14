import type { Citation } from "@/lib/types";

interface Props {
  citation: Citation;
  onClick?: () => void;
}

export function CitationBadge({ citation, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700 hover:bg-blue-200"
    >
      {citation.doc_name} · p.{citation.page}
    </button>
  );
}
