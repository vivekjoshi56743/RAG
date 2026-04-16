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
            <a href={href} className="text-brand-600 dark:text-brand-400 font-semibold underline underline-offset-4 decoration-brand-500/30 hover:decoration-brand-500 transition-all" target="_blank" rel="noreferrer">
              {children}
            </a>
          );
        },
        h1: ({ children }) => <h1 className="mb-4 mt-6 text-2xl font-black tracking-tight text-slate-900 dark:text-slate-100">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-3 mt-5 text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-bold text-slate-900 dark:text-slate-100">{children}</h3>,
        p: ({ children }) => <p className="mb-4 whitespace-pre-wrap text-sm leading-relaxed text-slate-700 dark:text-slate-300 transition-colors uppercase-first-letter">{children}</p>,
        ul: ({ children }) => <ul className="mb-4 list-disc space-y-2 pl-5 text-sm text-slate-700 dark:text-slate-300">{children}</ul>,
        ol: ({ children }) => <ol className="mb-4 list-decimal space-y-2 pl-5 text-sm text-slate-700 dark:text-slate-300">{children}</ol>,
        li: ({ children }) => <li className="leading-relaxed">{children}</li>,
        strong: ({ children }) => <strong className="font-bold text-slate-900 dark:text-slate-100">{children}</strong>,
        em: ({ children }) => <em className="italic opacity-90">{children}</em>,
        blockquote: ({ children }) => (
          <blockquote className="my-4 border-l-4 border-brand-500/20 bg-brand-500/5 py-2 pl-4 text-sm italic text-slate-600 dark:text-slate-400">{children}</blockquote>
        ),
        code: ({ className, children, ...props }) => {
          const isBlock = (className || "").includes("language-");
          return isBlock ? (
            <code
              className="block overflow-x-auto rounded-xl bg-slate-100/50 dark:bg-slate-800/50 p-4 text-[13px] font-mono text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-800 my-4"
              {...props}
            >
              {children}
            </code>
          ) : (
            <code className="rounded-md bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[13px] font-mono font-semibold text-brand-700 dark:text-brand-400 border border-slate-200 dark:border-slate-700/50" {...props}>
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
