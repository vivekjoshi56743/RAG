import type { Citation } from "@/lib/types";

interface Props {
  citation: Citation;
  onClick?: () => void;
  inlineIndex?: number;
}

export function CitationBadge({ citation, onClick, inlineIndex }: Props) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 font-bold text-brand-700 transition-all hover:bg-brand-100 hover:scale-105 active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:bg-brand-500/10 dark:border-brand-500/20 dark:text-brand-300 dark:hover:bg-brand-500/20 ${
        inlineIndex !== undefined ? "px-1.5 py-0.5 text-[10px] leading-tight tracking-wider" : "px-3 py-1 text-[11px] uppercase tracking-wide"
      }`}
      type="button"
      title={inlineIndex !== undefined ? citation.doc_name : undefined}
    >
      {inlineIndex !== undefined ? (
        `[${inlineIndex}]`
      ) : (
        <span className="truncate max-w-[140px]">
          {citation.doc_name}{citation.page != null ? ` · P.${citation.page}` : ""}
        </span>
      )}
    </button>
  );
}
