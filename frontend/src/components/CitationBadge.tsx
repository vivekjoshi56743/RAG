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
      className={`inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 font-medium text-brand-700 transition hover:bg-brand-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 ${
        inlineIndex !== undefined ? "px-1.5 py-0.5 text-[0.65rem] leading-none tracking-wide" : "px-2.5 py-1 text-xs"
      }`}
      type="button"
      title={inlineIndex !== undefined ? citation.doc_name : undefined}
    >
      {inlineIndex !== undefined ? (
        `[${inlineIndex}]`
      ) : (
        <>{citation.doc_name}{citation.page != null && citation.page !== "-" ? ` · p.${citation.page}` : ""}</>
      )}
    </button>
  );
}
