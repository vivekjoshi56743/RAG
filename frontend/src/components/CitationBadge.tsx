import type { Citation } from "@/lib/types";

interface Props {
  citation: Citation;
  onClick?: () => void;
}

export function CitationBadge({ citation, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 transition hover:bg-brand-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
      type="button"
    >
      {citation.doc_name}{citation.page != null && citation.page !== "-" ? ` · p.${citation.page}` : ""}
    </button>
  );
}
