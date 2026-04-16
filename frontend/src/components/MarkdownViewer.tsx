import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationBadge } from "./CitationBadge";
import type { Citation } from "@/lib/types";

interface Props {
  content: string;
  citations?: Citation[];
  onCitationClick?: (citation: Citation) => void;
}

export function MarkdownViewer({ content, citations, onCitationClick }: Props) {
  const processedContent = content.replace(/\[Source\s+(\d+)\]/gi, (match, sourceIdx) => {
    return `[Source ${sourceIdx}](#citation-${sourceIdx})`;
  });
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => {
          if (href?.startsWith("#citation-")) {
            const sourceIdx = parseInt(href.replace("#citation-", ""), 10);
            const citation = citations?.find((c) => c.source === sourceIdx);
            if (citation) {
              return (
                <span className="inline-block align-baseline mx-0.5">
                  <CitationBadge
                    citation={citation}
                    onClick={onCitationClick ? () => onCitationClick(citation) : undefined}
                    inlineIndex={sourceIdx}
                  />
                </span>
              );
            }
          }
          return (
            <a href={href} className="text-brand-600 underline hover:text-brand-700" target="_blank" rel="noreferrer">
              {children}
            </a>
          );
        },
        h1: ({ children }) => <h1 className="mb-2 mt-3 text-lg font-semibold text-slate-900">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-2 mt-3 text-base font-semibold text-slate-900">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-semibold text-slate-900">{children}</h3>,
        p: ({ children }) => <p className="mb-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">{children}</p>,
        ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 text-sm text-slate-800">{children}</ul>,
        ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 text-sm text-slate-800">{children}</ol>,
        li: ({ children }) => <li className="leading-6">{children}</li>,
        strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
        blockquote: ({ children }) => (
          <blockquote className="my-2 border-l-4 border-slate-200 pl-3 text-sm text-slate-700">{children}</blockquote>
        ),
        code: ({ className, children, ...props }) => {
          const isBlock = (className || "").includes("language-");
          return isBlock ? (
            <code
              className="block overflow-x-auto rounded-xl bg-slate-100 p-3 text-xs text-slate-800"
              {...props}
            >
              {children}
            </code>
          ) : (
            <code className="rounded bg-slate-100 px-1 py-0.5 text-xs text-slate-800" {...props}>
              {children}
            </code>
          );
        },
      }}
    >
      {processedContent}
    </ReactMarkdown>
  );
}
